"""
サービス側API（プラットフォーム内完結エージェント実行）。

- 単体エージェント:   POST /v1/agents/{id}/run     body {"input": "...", "context": "..."}  → ストリーミング(text/plain)
- 連携ワークフロー:   POST /v1/workflows/{id}/run  body {"input": "...", "context": "..."}  → 各ステップを直列連携
  ※ context はユーザーの会社・事業に関する自由記述（パーソナライズ設定）。system プロンプトに含めて成果物の質を上げる。
- ニュース投稿:       POST /v1/news/ingest         body {"items": [...]}  → cronジョブ専用（要 x-api-key = CRON_KEY）
- ニュース取得:       GET  /v1/news/latest         → フロントの時事ニュースが参照
- ヘルス:             GET  /healthz

必要な環境変数:
  ANTHROPIC_API_KEY   … 必須（Anthropic のキー）
  API_ACCESS_KEY      … 任意。設定するとエージェント/ワークフローの実行に x-api-key 必須（未設定なら誰でも叩ける＝まず動かす用）
  CRON_KEY            … 必須（/v1/news/ingest 用）。未設定だとニュース投稿は常に拒否される
  ALLOW_ORIGINS       … 任意。CORS 許可オリジン（カンマ区切り）。既定は "*"

注意: ニュースは現状インメモリ保存。無料インスタンスはスリープ復帰時にリセットされるため、
次回のcron実行までは空/直近分のみになる（実運用でDB化する場合はここを差し替え）。

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
_CRON_KEY = os.getenv("CRON_KEY", "")

_NEWS_MAX = 50
_news_store: list[dict] = []


class RunRequest(BaseModel):
    input: str = ""
    context: str = ""  # 依頼者の会社・事業について（自由記述、任意）
    messages: list[dict] = []  # 会話履歴 [{role:"user"|"assistant", content:"..."}]。指定時は input より優先（マイライブラリの会話継続用）


class NewsItem(BaseModel):
    title: str = ""
    summary: str = ""
    tasks: list[str] = []
    source: str = ""
    link: str = ""
    published: str | None = None


class NewsIngestRequest(BaseModel):
    items: list[NewsItem]


def _auth(x_api_key: str | None) -> None:
    # API_ACCESS_KEY を設定したときだけ認証を要求（未設定なら誰でも可＝まず動かす用）
    if _ACCESS_KEY and x_api_key != _ACCESS_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")


def _auth_cron(x_api_key: str | None) -> None:
    # ニュース投稿は常に CRON_KEY 必須（誰でも書き込めるのを防ぐ）
    if not _CRON_KEY or x_api_key != _CRON_KEY:
        raise HTTPException(status_code=401, detail="invalid cron key")


def _run(agent: dict, user_input: str, biz_context: str = "") -> Iterator[str]:
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=system_for(agent, biz_context),
        messages=[{"role": "user", "content": user_input or "（入力なし）サンプルを1つ生成してください。"}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _run_collect(agent: dict, user_input: str, biz_context: str = "") -> str:
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=system_for(agent, biz_context),
        messages=[{"role": "user", "content": user_input}],
    ) as stream:
        msg = stream.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text")


def _run_chat(agent: dict, messages: list[dict], biz_context: str = "") -> Iterator[str]:
    """複数ターンの会話履歴をそのままClaudeに渡す（マイライブラリの会話継続用）。"""
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=system_for(agent, biz_context),
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


# Render の手前に Cloudflare が入っており、圧縮のためレスポンス全体をバッファしてしまうと
# ストリーミングが効かず「実行中…」のまま固まって見える。no-transform でCDN側の変換（圧縮）を止め、
# X-Accel-Buffering: no でプロキシのバッファリングを止める（両方指定しないと片方だけでは効かないことがある）。
_STREAM_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


@app.post("/v1/agents/{agent_id}/run")
def run_agent(agent_id: str, req: RunRequest, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    agent = AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    if req.messages:
        msgs = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in req.messages if m.get("content")]
        return StreamingResponse(_run_chat(agent, msgs, req.context), media_type="text/plain; charset=utf-8", headers=_STREAM_HEADERS)
    return StreamingResponse(_run(agent, req.input, req.context), media_type="text/plain; charset=utf-8", headers=_STREAM_HEADERS)


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
            out = _run_collect(agent, payload, req.context)
            yield out + "\n"
            payload = out  # 前段の出力を次段の入力へ
        yield "\n＝ 最終成果物は上記の最終ステップ出力です ＝\n"

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8", headers=_STREAM_HEADERS)


@app.post("/v1/news/ingest")
def ingest_news(req: NewsIngestRequest, x_api_key: str | None = Header(default=None)):
    """毎日のcronジョブ（backend/pipeline/cron_ingest.py）から新着ニュースを受け取る。"""
    _auth_cron(x_api_key)
    for item in req.items:
        _news_store.insert(0, item.model_dump())
    del _news_store[_NEWS_MAX:]
    return {"ok": True, "stored": len(req.items), "total": len(_news_store)}


@app.get("/v1/news/latest")
def latest_news():
    return {"items": _news_store}


@app.get("/healthz")
def healthz():
    return {"ok": True, "agents": len(AGENTS), "workflows": len(WORKFLOWS)}
