"""
Obsidian 知識構造化 — 連携ワークフロー(スキル図)を Mermaid フローチャートとして自動生成。

ワークフロー定義（入力→出力の連鎖）から Mermaid を組み立て、Obsidian Vault のノートに書き出す。
フロントの「スキル図」と同じ構造を Vault と共有し、知識を可視化・蓄積する。

※ 依存なし（標準ライブラリのみ）。Vault パスは環境に合わせて変更。
"""
from __future__ import annotations

from pathlib import Path

VAULT = Path("OS_Vault/ワークフロー")  # Google Drive 上の OS_Vault に合わせて変更


def to_mermaid(workflow: dict) -> str:
    """steps=[{agent,in,out}] から Mermaid flowchart を生成。"""
    nodes = []
    edges = []
    prev = None
    for i, s in enumerate(workflow["steps"]):
        nid = chr(ord("A") + i)
        label = s["agent"].replace('"', "'")
        nodes.append(f'  {nid}["{label}"]')
        if prev is not None:
            # エッジのラベルに「出力→入力」を載せる
            edges.append(f'  {prev} -->|{workflow["steps"][i-1]["out"]}| {nid}')
        prev = nid
    return "flowchart LR\n" + "\n".join(nodes + edges)


def write_note(workflow: dict) -> Path:
    """ワークフローを 1 枚の Obsidian ノート（Mermaid 埋め込み）として書き出す。"""
    VAULT.mkdir(parents=True, exist_ok=True)
    path = VAULT / f'{workflow["name"]}.md'
    body = [
        f'# {workflow["name"]}',
        "",
        workflow.get("desc", ""),
        "",
        "```mermaid",
        to_mermaid(workflow),
        "```",
        "",
        "## 各工程の入出力",
        "",
        "| # | エージェント | 入力 | 出力 |",
        "|---|---|---|---|",
    ]
    for i, s in enumerate(workflow["steps"], 1):
        body.append(f'| {i} | {s["agent"]} | {s["in"]} | {s["out"]} |')
    path.write_text("\n".join(body), encoding="utf-8")
    return path


if __name__ == "__main__":
    demo = {
        "name": "新規リード獲得→受注フォロー",
        "desc": "営業の前後工程を特化エージェントで直列連携。",
        "steps": [
            {"agent": "リストアップ・スキル", "in": "検索条件", "out": "新規リード"},
            {"agent": "提案書ドラフト生成", "in": "ヒアリング", "out": "提案書ドラフト"},
            {"agent": "議事録エージェント", "in": "商談メモ", "out": "議事録＋タスク"},
            {"agent": "タスク抽出AI", "in": "議事録", "out": "担当/期日タスク"},
            {"agent": "メール返信ドラフト", "in": "顧客状況", "out": "フォロー文"},
        ],
    }
    print(write_note(demo))
