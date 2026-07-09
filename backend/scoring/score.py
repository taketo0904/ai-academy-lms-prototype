"""
スコアリング → AI学習ループ — リファレンス実装。

アウトプットの反応（表示 impression / クリック click / 使用 use / DL download）を集計して
スコア化し、①並び順・新着選定 ②弱いエージェントの改善対象特定 に使う。
スコア算出は純Python（依存なし・検証可能）。改善提案の文章生成のみ任意でClaudeを使う。

品質の最終判定はAIではなく人間（直氏・小林氏）が担う前提（会議強調）。
"""
from __future__ import annotations

from collections import defaultdict

# イベント例: {"item_id": "t1", "type": "impression|click|use|download"}
Event = dict


def score(events: list[Event]) -> dict[str, dict]:
    """item_id ごとに CTR・使用率・DL率とスコアを算出。"""
    agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {"impression": 0, "click": 0, "use": 0, "download": 0}
    )
    for e in events:
        t = e.get("type")
        if t in ("impression", "click", "use", "download"):
            agg[e["item_id"]][t] += 1

    result: dict[str, dict] = {}
    for item_id, c in agg.items():
        imp = max(c["impression"], 1)
        ctr = c["click"] / imp
        use_rate = c["use"] / imp
        dl_rate = c["download"] / imp
        # 重み: クリック0.2 / 使用0.5 / DL0.3（使われる・持ち帰られるほど高評価）
        s = round(ctr * 0.2 + use_rate * 0.5 + dl_rate * 0.3, 4)
        result[item_id] = {
            **c, "ctr": round(ctr, 3), "use_rate": round(use_rate, 3),
            "dl_rate": round(dl_rate, 3), "score": s,
        }
    return result


def ranked(scores: dict[str, dict]) -> list[str]:
    """スコア降順の item_id 一覧（並び順・新着選定に使う）。"""
    return [i for i, _ in sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)]


def improvement_targets(scores: dict[str, dict], min_impressions: int = 20) -> list[str]:
    """十分露出されているのにスコアが低い＝改善対象のエージェント。"""
    return [
        i for i, s in scores.items()
        if s["impression"] >= min_impressions and s["score"] < 0.15
    ]


def suggest_prompt_fix(agent_name: str, stats: dict) -> str:
    """改善対象エージェントのプロンプト改善案を生成（任意・Claude使用）。"""
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        system="あなたはプロンプト改善の専門家。低スコアのAIエージェントについて、"
               "出力が使われるようにする具体的な改善案を3点、簡潔に提案する。",
        messages=[{"role": "user",
                   "content": f"エージェント: {agent_name}\n指標: {stats}\n改善案を3点。"}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


if __name__ == "__main__":
    demo = (
        [{"item_id": "t1", "type": "impression"}] * 50
        + [{"item_id": "t1", "type": "click"}] * 30
        + [{"item_id": "t1", "type": "use"}] * 20
        + [{"item_id": "t1", "type": "download"}] * 12
        + [{"item_id": "t8", "type": "impression"}] * 40
        + [{"item_id": "t8", "type": "click"}] * 3
    )
    s = score(demo)
    print("scores:", s)
    print("ranked:", ranked(s))
    print("improve:", improvement_targets(s))
