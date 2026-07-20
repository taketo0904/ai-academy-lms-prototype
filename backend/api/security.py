"""共通の簡易認証。main.py と superagent.py の両方から使う。"""
from __future__ import annotations

import os

from fastapi import HTTPException

ACCESS_KEY = os.getenv("API_ACCESS_KEY", "")


def auth_or_401(x_api_key: str | None) -> None:
    # API_ACCESS_KEY を設定したときだけ認証を要求（未設定なら誰でも可＝まず動かす用）
    if ACCESS_KEY and x_api_key != ACCESS_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
