"""
スーパーエージェント（多形式生成・Genspark型）。

プロンプト1つで、コードを書いて実際に実行・検証しながらアプリ／資料／スプレッドシート等の
成果物を作る。Anthropic Managed Agents (beta) を使い、ツール実行はAnthropic側のサンドボックス
コンテナで行う（本サーバーはイベントを中継するだけ）。

- Agent / Environment は使い回す永続リソース。名前をユニークキーとして起動時に
  「無ければ作成・あれば既存を再利用」する（Renderの再起動でも同じものを使い続ける）。
- ストリームの最初の1行に `[[SESSION_ID:...]]` を差し込み、フロント側でセッションIDを
  取り出せるようにしている（続きの会話や生成物一覧の取得に使う）。

必要な環境変数: ANTHROPIC_API_KEY（backend/api/main.pyと共通）
"""
from __future__ import annotations

from typing import Iterator

import anthropic
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .security import auth_or_401

router = APIRouter(prefix="/v1/superagent", tags=["superagent"])

client = anthropic.Anthropic()

_AGENT_NAME = "TASK AGENTS スーパーエージェント"
_ENV_NAME = "task-agents-superagent-env"

_SYSTEM_PROMPT = (
    "あなたはTASK AGENTS内の「スーパーエージェント」です。"
    "ユーザーの依頼に応じて、Webアプリ・資料・スプレッドシート・コードなど必要な形式を"
    "自律的に判断し、実際にコードを書いて実行・検証したうえで成果物を作ります。"
    "作業の節目では日本語で短く進捗を報告してください。"
    "最終的な成果物ファイルは必ず /mnt/session/outputs/ 配下に書き出してください。"
)

_STREAM_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
_FILES_BETA = ["managed-agents-2026-04-01"]

_agent_id: str | None = None
_env_id: str | None = None


def _get_or_create_agent() -> str:
    global _agent_id
    if _agent_id:
        return _agent_id
    try:
        agent = client.beta.agents.create(
            name=_AGENT_NAME,
            model="claude-opus-4-8",
            system=_SYSTEM_PROMPT,
            tools=[{"type": "agent_toolset_20260401"}],
        )
        _agent_id = agent.id
    except anthropic.APIStatusError as e:
        if e.status_code != 409:
            raise
        for a in client.beta.agents.list():
            if a.name == _AGENT_NAME:
                _agent_id = a.id
                break
        if not _agent_id:
            raise
    return _agent_id


def _get_or_create_env() -> str:
    global _env_id
    if _env_id:
        return _env_id
    try:
        env = client.beta.environments.create(
            name=_ENV_NAME,
            config={"type": "cloud", "networking": {"type": "unrestricted"}},
        )
        _env_id = env.id
    except anthropic.APIStatusError as e:
        if e.status_code != 409:
            raise
        for env in client.beta.environments.list():
            if env.name == _ENV_NAME:
                _env_id = env.id
                break
        if not _env_id:
            raise
    return _env_id


class StartRequest(BaseModel):
    prompt: str
    context: str = ""


class MessageRequest(BaseModel):
    prompt: str


def _format_event(ev) -> str | None:
    t = ev.type
    if t == "agent.message":
        text = "".join(b.text for b in ev.content if b.type == "text")
        return text or None
    if t == "agent.tool_use":
        return f"\n🔧 {getattr(ev, 'name', 'ツール')} を実行中...\n"
    if t == "agent.mcp_tool_use":
        return f"\n🔌 {getattr(ev, 'name', 'MCPツール')} を実行中...\n"
    if t == "session.status_idle":
        return "\n\n✅ ここまで完了しました\n"
    if t == "session.error":
        return f"\n⚠️ エラー: {getattr(ev, 'message', '不明なエラー')}\n"
    return None


def _stream_turn(session_id: str, prompt: str) -> Iterator[str]:
    yield f"[[SESSION_ID:{session_id}]]\n"
    with client.beta.sessions.events.stream(session_id=session_id) as stream:
        client.beta.sessions.events.send(
            session_id=session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
        )
        for ev in stream:
            text = _format_event(ev)
            if text:
                yield text
            if ev.type in ("session.status_idle", "session.status_terminated"):
                break


def _compose_prompt(prompt: str, context: str) -> str:
    if not context:
        return prompt
    return f"{prompt}\n\n【依頼者の会社・事業について】\n{context}"


@router.post("/sessions/start")
def start_session(req: StartRequest, x_api_key: str | None = Header(default=None)):
    auth_or_401(x_api_key)
    agent_id = _get_or_create_agent()
    env_id = _get_or_create_env()
    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=env_id,
        title=(req.prompt or "無題")[:60],
    )
    prompt = _compose_prompt(req.prompt, req.context)
    return StreamingResponse(_stream_turn(session.id, prompt), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.post("/sessions/{session_id}/messages")
def continue_session(session_id: str, req: MessageRequest, x_api_key: str | None = Header(default=None)):
    auth_or_401(x_api_key)
    return StreamingResponse(_stream_turn(session_id, req.prompt), media_type="text/event-stream", headers=_STREAM_HEADERS)


@router.get("/sessions/{session_id}/files")
def list_files(session_id: str, x_api_key: str | None = Header(default=None)):
    auth_or_401(x_api_key)
    files = client.beta.files.list(scope_id=session_id, betas=_FILES_BETA)
    return {"files": [{"id": f.id, "filename": f.filename, "size_bytes": f.size_bytes} for f in files.data]}


@router.get("/files/{file_id}")
def download_file(file_id: str, x_api_key: str | None = Header(default=None)):
    auth_or_401(x_api_key)
    try:
        meta = client.beta.files.retrieve_metadata(file_id)
    except anthropic.NotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    content = client.beta.files.download(file_id)
    data = content.read()
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{meta.filename}"'},
    )
