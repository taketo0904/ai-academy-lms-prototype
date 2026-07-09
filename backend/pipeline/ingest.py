"""
情報源の取り込みパイプライン — リファレンス実装。

海外の最新記事/事例・書籍PDF(+OCR)・PR TIMES 過去プレスを取得し、Claudeで要約・構造化して、
「過去に出した情報と重複しない」ものだけを保存し、辞書/時事ニュースへ供給する。

取得元:
  - 記事/事例 … Web検索API(Tavily)や RSS      -> fetch_articles()
  - 書籍PDF   … PDF化 -> OCR でテキスト化       -> ocr_pdf()
  - PR TIMES  … 過去プレスをスクレイピング       -> scrape_prtimes()
※ 取得部は環境依存のためスタブ。実運用で各API/スクレイパを実装する。

前提: `pip install "anthropic>=0.40"` / ANTHROPIC_API_KEY。
※ このリポジトリでは未実行のリファレンス。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import anthropic

client = anthropic.Anthropic()
SEEN_PATH = Path("backend/pipeline/_seen.json")  # 既出コンテンツの指紋（本番はDB）


def _load_seen() -> set[str]:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text()))
    return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_PATH.write_text(json.dumps(sorted(seen), ensure_ascii=False))


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


# --- 取得（スタブ: 実運用で実装） ---
def fetch_articles(query: str) -> list[str]:
    """Web検索API(Tavily)/RSS で最新記事本文を返す。"""
    return []  # TODO: Tavily / RSS 連携


def ocr_pdf(pdf_path: str) -> str:
    """書籍PDFをOCRしてテキスト化。"""
    return ""  # TODO: OCR (例: pytesseract / クラウドOCR)


def scrape_prtimes(keyword: str) -> list[str]:
    """PR TIMES の過去プレスを取得（規約・レート制御順守）。"""
    return []  # TODO: スクレイパ


# --- 要約・構造化（重複しない制約つき） ---
def summarize(raw_text: str) -> dict:
    """記事本文を、業務に効く時事ニュース項目へ要約・構造化する。"""
    msg = client.messages.create(
        model="claude-haiku-4-5",  # 大量処理のため安価モデル
        max_tokens=1024,
        system=(
            "あなたはAI・業務ニュースの編集エージェント。入力記事を、業務担当者に役立つ形で "
            "JSONに要約する。キー: title(30字前後), summary(120字前後), tasks(関連業務タスク名の配列)。"
            "誇張せず事実ベースで。"
        ),
        messages=[{"role": "user", "content": raw_text[:12000]}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"title": text[:30], "summary": text[:120], "tasks": []}


def ingest(query: str) -> list[dict]:
    """取得→要約→重複除去→保存。重複しない新規項目だけを返す。"""
    seen = _load_seen()
    fresh: list[dict] = []
    for raw in fetch_articles(query) + scrape_prtimes(query):
        fp = _fingerprint(raw)
        if fp in seen:
            continue  # 「過去情報と重複しない」制約
        item = summarize(raw)
        # タイトル重複もはじく（表現違いの重複防止）
        if _fingerprint(item.get("title", "")) in seen:
            continue
        seen.add(fp)
        seen.add(_fingerprint(item.get("title", "")))
        fresh.append(item)
    _save_seen(seen)
    return fresh  # -> DBへ保存し /v1/news で配信


if __name__ == "__main__":
    for it in ingest("生成AI 業務 最新"):
        print(it)
