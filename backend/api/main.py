"""
サービス側API（プラットフォーム内完結エージェント実行）— リファレンス実装。

会議決定: ユーザーは自分のClaude契約なしで、サービス側APIでエージェントを実行して成果物を得る。
- 単体エージェント実行:   POST /v1/agents/{id}/run
- 連携ワークフロー実行:   POST /v1/workflows/{id}/run   （特化型を直列連携）
- 認証: APIキー（本番は電話番号認証＋プラン判定を前段に）

前提: `pip install fastapi uvicorn "anthropic>=0.40"` / 環境変数 ANTHROPIC_API_KEY。
起動: `uvicorn backend.api.main:app --reload`
※ このリポジトリでは未実行のリファレンス。デプロイ環境で動かす。
"""
from __future__ import annotations

import os
from typing import Iterator

import anthropic
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY を環境から解決
app = FastAPI(title="Task Agents API", version="0.1")

# --- モデルの出し分け（原価管理）: 定型=Haiku、企画/レビュー=Opus ---
CHEAP = "claude-haiku-4-5"
SMART = "claude-opus-4-8"

# --- エージェント定義（フロントの辞書と対応。入力→出力＋実行プロンプト）---
AGENTS: dict[str, dict] = {
    "t1": {
        "name": "リストアップ・スキル",
        "model": CHEAP,
        "system": "あなたは営業リスト作成の専門エージェント。入力の検索条件と既存台帳から、"
                  "重複・営業済みを除いた新規リードだけを、会社名・担当・連絡先の表形式で出力する。",
    },
    "t3": {
        "name": "提案書ドラフト生成",
        "model": SMART,
        "system": "あなたは提案書作成の専門エージェント。ヒアリング内容から、課題→打ち手→"
                  "見積骨子の順で、そのまま使える提案書ドラフトを出力する。",
    },
    # ... 辞書の全タスク分をここに定義（本番はDB/設定ファイルから読み込む）
}

# --- 連携ワークフロー（特化型エージェントを直列連携）---
WORKFLOWS: dict[str, dict] = {
    "wf2": {
        "name": "新規リード獲得→受注フォロー",
        "steps": ["t1", "t3"],  # 実際は 5 ステップ。前段の出力を次段の入力へ渡す
    },
}


class RunRequest(BaseModel):
    input: str


def _check_key(api_key: str | None) -> None:
    # 本番: DBでキー検証＋プラン判定＋利用上限チェック＋電話番号認証
    if not api_key:
        raise HTTPException(status_code=401, detail="missing api key")


def _run_agent(agent: dict, user_input: str) -> Iterator[str]:
    """1エージェントを実行し、テキストをストリーミングで返す。"""
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=agent["system"],
        messages=[{"role": "user", "content": user_input}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def _run_agent_collect(agent: dict, user_input: str) -> str:
    """1エージェントを実行し、完成テキストを返す（ワークフローの中間段で使用）。"""
    with client.messages.stream(
        model=agent["model"],
        max_tokens=4096,
        system=agent["system"],
        messages=[{"role": "user", "content": user_input}],
    ) as stream:
        msg = stream.get_final_message()
    return "".join(b.text for b in msg.content if b.type == "text")


@app.post("/v1/agents/{agent_id}/run")
def run_agent(agent_id: str, req: RunRequest, x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    agent = AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    return StreamingResponse(_run_agent(agent, req.input), media_type="text/plain")


@app.post("/v1/workflows/{wf_id}/run")
def run_workflow(wf_id: str, req: RunRequest, x_api_key: str | None = Header(default=None)):
    _check_key(x_api_key)
    wf = WORKFLOWS.get(wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")

    def gen() -> Iterator[str]:
        payload = req.input
        for step_id in wf["steps"]:
            agent = AGENTS[step_id]
            yield f"\n\n=== {agent['name']} ===\n"
            out = _run_agent_collect(agent, payload)
            yield out
            payload = out  # 前段の出力を次段の入力へ（直列連携）

    return StreamingResponse(gen(), media_type="text/plain")


@app.get("/healthz")
def healthz():
    return {"ok": True, "agents": len(AGENTS), "workflows": len(WORKFLOWS)}
