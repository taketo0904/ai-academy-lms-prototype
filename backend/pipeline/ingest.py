"""
情報源の取り込みパイプライン。

業務に効くAI関連ニュースをRSSから取得し、Claudeで要約・構造化して、
「過去に出した情報と重複しない」ものだけを保存し、辞書/時事ニュースへ供給する。

取得元:
  - AI専門メディアのRSS（ITmedia AI+、AINOW）        -> fetch_articles()
  - PR TIMES（"AI"等の業務関連キーワードのみ抽出）    -> scrape_prtimes()

前提: `pip install "anthropic>=0.40" feedparser`, ANTHROPIC_API_KEY。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import mktime

import anthropic
import feedparser

from api.agents import AGENTS

client = anthropic.Anthropic()
_TASK_NAMES = "、".join(a["name"] for a in AGENTS.values())
SEEN_PATH = Path("backend/pipeline/_seen.json")  # 既出コンテンツの指紋（本番はDB）

RSS_FEEDS = [
    ("ITmedia AI+", "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml"),
    ("AINOW", "https://ainow.ai/feed/"),
]
PRTIMES_FEED = ("PR TIMES", "https://prtimes.jp/index.rdf")
PRTIMES_KEYWORDS = ["AI", "生成AI", "DX", "業務効率化", "自動化"]


def _load_seen() -> set[str]:
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text()))
    return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_PATH.write_text(json.dumps(sorted(seen), ensure_ascii=False))


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def _published_iso(entry) -> str | None:
    """RSSエントリの公開日時をISO8601に変換（取得できなければNone＝捏造しない）。"""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc).isoformat()
    except (OverflowError, ValueError):
        return None


# --- 取得 ---
def fetch_articles(query: str) -> list[dict]:
    """AI専門メディアのRSSから最新記事を返す（本文・出典・リンク・公開日時つき）。"""
    articles: list[dict] = []
    for source, feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            continue
        for entry in feed.entries[:8]:
            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            if not title:
                continue
            articles.append({
                "raw": f"{title}\n{summary}",
                "source": source,
                "link": entry.get("link", ""),
                "published": _published_iso(entry),
            })
    return articles


def ocr_pdf(pdf_path: str) -> str:
    """書籍PDFをOCRしてテキスト化。"""
    return ""  # TODO: OCR (例: pytesseract / クラウドOCR)


def scrape_prtimes(keyword: str) -> list[dict]:
    """PR TIMES の新着プレスから業務関連キーワードに合致するものだけ抽出。"""
    source, feed_url = PRTIMES_FEED
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        return []
    items: list[dict] = []
    for entry in feed.entries[:30]:
        title = entry.get("title", "")
        if any(kw in title for kw in PRTIMES_KEYWORDS):
            summary = entry.get("summary", "") or entry.get("description", "")
            items.append({
                "raw": f"{title}\n{summary}",
                "source": source,
                "link": entry.get("link", ""),
                "published": _published_iso(entry),
            })
    return items


# --- 要約・構造化（重複しない制約つき） ---
def summarize(raw_text: str) -> dict:
    """記事本文を、業務に効く時事ニュース項目へ要約・構造化する。"""
    msg = client.messages.create(
        model="claude-haiku-4-5",  # 大量処理のため安価モデル
        max_tokens=1024,
        system=(
            "あなたはAI・業務ニュースの編集エージェント。入力記事を、業務担当者に役立つ形で "
            "JSONに要約する。キー: title(30字前後), summary(120字前後), "
            f"tasks(関連するものだけを次の一覧から厳密に選ぶ配列。一致がなければ空配列: {_TASK_NAMES})。"
            "誇張せず事実ベースで。"
        ),
        messages=[{"role": "user", "content": raw_text[:12000]}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"title": text[:30], "summary": text[:120], "tasks": []}


def ingest(query: str, max_items: int = 8) -> list[dict]:
    """取得→要約→重複除去→保存。重複しない新規項目だけを、上限件数まで返す（Claude呼び出し数の抑制）。"""
    seen = _load_seen()
    fresh: list[dict] = []
    for raw_item in fetch_articles(query) + scrape_prtimes(query):
        if len(fresh) >= max_items:
            break
        fp = _fingerprint(raw_item["raw"])
        if fp in seen:
            continue  # 「過去情報と重複しない」制約
        item = summarize(raw_item["raw"])
        # タイトル重複もはじく（表現違いの重複防止）
        if _fingerprint(item.get("title", "")) in seen:
            continue
        seen.add(fp)
        seen.add(_fingerprint(item.get("title", "")))
        item["source"] = raw_item["source"]
        item["link"] = raw_item["link"]
        item["published"] = raw_item["published"]  # 取得できなければ None（フロント側で「収集日時」にフォールバック）
        fresh.append(item)
    _save_seen(seen)
    return fresh  # -> /v1/news/ingest 経由でAPIへ配信


if __name__ == "__main__":
    for it in ingest("生成AI 業務 最新"):
        print(it)
