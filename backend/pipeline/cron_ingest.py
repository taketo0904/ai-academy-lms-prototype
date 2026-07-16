"""
毎日実行: 記事取得→要約→重複除去→稼働中のAPIへ配信登録。

Render の Cron Job（rootDir: backend）から `python -m pipeline.cron_ingest` で起動する想定。

必要な環境変数:
  ANTHROPIC_API_KEY … 必須（ingest() の要約で使用）
  NEWS_API_BASE      … 必須。配信先APIのベースURL（例: https://task-agents-api.onrender.com）
  CRON_KEY           … 必須。APIの /v1/news/ingest 認証キー（Web側の CRON_KEY と同じ値）
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
import json

from .ingest import ingest


def main() -> None:
    api_base = os.environ["NEWS_API_BASE"].rstrip("/")
    cron_key = os.environ["CRON_KEY"]

    items = ingest("生成AI 業務 活用", max_items=8)
    if not items:
        print("no fresh items")
        return

    body = json.dumps({"items": items}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/v1/news/ingest",
        data=body,
        method="POST",
        headers={"content-type": "application/json", "x-api-key": cron_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            print(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"ingest failed: HTTP {e.code} {e.read().decode('utf-8', 'ignore')}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
