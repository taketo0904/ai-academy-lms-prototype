"""
サービス側API（プラットフォーム内完結エージェント実行）。

- 単体エージェント:   POST /v1/agents/{id}/run     body {"input": "..."}  → ストリーミング(text/plain)
- 連携ワークフロー:   POST /v1/workflows/{id}/run  body {"input": "..."}  → 各ステップを直列連携
- ヘルス:             GET  /healthz

必要な環境変数:
  ANTHROPIC_API_KEY   … 必須（Anthropic のキー）
  API_ACCESS_KEY      … 任意。設定するとリクエストに x-api-key 必須（未設定なら誰でも叩ける＝まず動かす用）
  ALLOW_ORIGINS       … 任意。CORS 許可オリジン（カンマ区切り）。既定は "*"

起動: uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
"""
from __future__ import annotations

import os
from typing import Iterator

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agents import AGENTS, WORKFLOWS, system_for

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境から解決
app = FastAPI(title="Task Agents API", version="1.0")

# CORS: フロント（GitHub Pages 等）からの呼び出しを許可
_origins = [o.strip() for o in os.getenv("ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ACCESS_KEY = os.getenv("API_ACCESS_KEY", "")


class RunRequest(BaseModel):
    input: str = ""


def _auth(x_api_key: str | None) -> None:
    # API_ACCESS_KEY を設定したときだけ認証を要求（未設定なら誰でも可＝まず動かす用）
    if _ACCESS_KEY and x_api_key != _ACCESS_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


def _run(agent: dict, user_input: str) -> Iterator[str]:
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=system_for(agent),
        messages=[{"role": "user", "content": user_input or "（入力なし）サンプルを1つ生成してください。"}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _run_collect(agent: dict, user_input: str) -> str:
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=system_for(agent),
        messages=[{"role": "user", "content": user_input}],
    ) as stream:
        msg = stream.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text")


@app.post("/v1/agents/{agent_id}/run")
def run_agent(agent_id: str, req: RunRequest, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    agent = AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    return StreamingResponse(_run(agent, req.input), media_type="text/plain; charset=utf-8")


@app.post("/v1/workflows/{wf_id}/run")
def run_workflow(wf_id: str, req: RunRequest, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    wf = WORKFLOWS.get(wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")

    def gen() -> Iterator[str]:
        payload = req.input
        yield f"【ワークフロー: {wf['name']}】\n"
        for i, sid in enumerate(wf["steps"], 1):
            agent = AGENTS[sid]
            yield f"\n▼ STEP {i} {agent['name']}\n"
            out = _run_collect(agent, payload)
            yield out + "\n"
            payload = out  # 前段の出力を次段の入力へ
        yield "\n＝ 最終成果物は上記の最終ステップ出力です ＝\n"

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@app.get("/healthz")
def healthz():
    return {"ok": True, "agents": len(AGENTS), "workflows": len(WORKFLOWS)}
