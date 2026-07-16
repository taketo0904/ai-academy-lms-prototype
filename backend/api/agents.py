"""
エージェント定義（フロント辞書と対応）とワークフロー。
各エージェントの system プロンプトは name / in / out からテンプレートで生成する。
model は原価管理のため出し分け（定型=Haiku、企画/レビュー系=Opus）。
"""
CHEAP = "claude-haiku-4-5"
SMART = "claude-opus-4-8"

# id -> {name, in, out, model}
AGENTS = {
    "t1":  {"name": "リストアップ・スキル",   "in": "検索条件・ターゲット像・既存顧客台帳", "out": "重複・営業済みを除いた新規リード一覧（会社・担当・連絡先）", "model": CHEAP},
    "t2":  {"name": "議事録エージェント",     "in": "商談の音声またはメモ",           "out": "要約・決定事項・担当/期日つきタスク", "model": CHEAP},
    "t3":  {"name": "提案書ドラフト生成",     "in": "ヒアリング内容・要件",           "out": "課題〜打ち手〜見積骨子入りの提案書ドラフト", "model": SMART},
    "t4":  {"name": "見積書アシスタント",     "in": "項目・数量・単価・取引先",       "out": "体裁の整った見積書", "model": CHEAP},
    "t5":  {"name": "メール返信ドラフト",     "in": "顧客の状況・前回のやり取り",     "out": "トーンを合わせたフォロー文（複数案）", "model": CHEAP},
    "t6":  {"name": "受注データ整形",         "in": "受注メール・伝票",               "out": "整形済みの受注データ・集計表", "model": CHEAP},
    "t7":  {"name": "請求書アシスタント",     "in": "案件・金額・取引先",             "out": "請求書＋送付状況の管理表", "model": CHEAP},
    "t8":  {"name": "経費チェック",           "in": "領収書・申請データ・規程",       "out": "規程違反・不備の指摘リスト", "model": CHEAP},
    "t9":  {"name": "採用スクリーニングAI",   "in": "募集要件・応募書類",             "out": "通過候補と評価根拠", "model": SMART},
    "t10": {"name": "求人票ジェネレーター",   "in": "職務内容・条件",                 "out": "媒体別の求人票", "model": CHEAP},
    "t11": {"name": "契約レビューAI",         "in": "契約書（NDA・委託等）",          "out": "不利な条項・欠落の指摘と修正案", "model": SMART},
    "t12": {"name": "社内FAQボット",         "in": "社内規程・問い合わせ内容",       "out": "根拠つきの回答文", "model": CHEAP},
    "t13": {"name": "勤怠集計",               "in": "打刻データ",                     "out": "月次の勤怠集計・アラート", "model": CHEAP},
    "t14": {"name": "SNS投稿ジェネレーター",  "in": "テーマ・媒体・トーン",           "out": "媒体別の投稿文＋ハッシュタグ", "model": CHEAP},
    "t15": {"name": "広告コピーAI",           "in": "ターゲット・訴求軸",             "out": "広告コピー複数案", "model": CHEAP},
    "t16": {"name": "LPライターAI",           "in": "商品・オファー情報",             "out": "LPの構成・見出し・本文", "model": SMART},
    "t17": {"name": "競合調査AI",             "in": "競合URL・名称",                  "out": "訴求・ブランド要素の抽出と比較表", "model": SMART},
    "t18": {"name": "キャンペーン企画",       "in": "目的・予算・期間",               "out": "キャンペーン企画案・スケジュール", "model": SMART},
    "t19": {"name": "メルマガ作成",           "in": "配信テーマ・訴求",               "out": "メルマガ本文（件名・本文・CTA）", "model": CHEAP},
    "t20": {"name": "データ整形AI",           "in": "生データ（CSV等）",              "out": "欠損・表記ゆれ・型を整えた分析用データ", "model": CHEAP},
    "t21": {"name": "データ可視化AI",         "in": "表データ・見たい指標",           "out": "グラフ・ダッシュボードの構成と説明", "model": CHEAP},
    "t22": {"name": "分析レポート",           "in": "分析済みデータ",                 "out": "要点・示唆をまとめたレポート", "model": SMART},
    "t23": {"name": "テキスト分類AI",         "in": "自由記述コメント",               "out": "論点別の分類＋代表意見の要約", "model": CHEAP},
    "t24": {"name": "WBSビルダー",           "in": "ゴール・制約",                   "out": "担当・期日つきのWBS", "model": CHEAP},
    "t25": {"name": "進捗レポートAI",         "in": "進捗状況・課題",                 "out": "進捗報告書（状況/課題/次アクション）", "model": CHEAP},
    "t26": {"name": "タスク抽出AI",           "in": "議事録",                         "out": "担当・期日つきタスク一覧", "model": CHEAP},
    "t27": {"name": "リスク一覧",             "in": "プロジェクト概要",               "out": "リスク一覧（影響・対策）", "model": CHEAP},
    "t28": {"name": "問い合わせ分類AI",       "in": "問い合わせログ",                 "out": "種別・緊急度別の分類と振り分け", "model": CHEAP},
    "t29": {"name": "手順書ジェネレーター",   "in": "操作フロー",                     "out": "運用手順書・チェックリスト", "model": CHEAP},
    "t30": {"name": "障害一次切り分け",       "in": "ログ・アラート",                 "out": "原因候補・一次対応の提示", "model": SMART},
}

# 連携ワークフロー（前段の出力→次段の入力）。未整備ステップは含めない。
WORKFLOWS = {
    "wf2": {"name": "新規リード獲得→受注フォロー", "steps": ["t1", "t3", "t2", "t26", "t5"]},
    "wf3": {"name": "採用オペレーション",           "steps": ["t10", "t9"]},
}


def system_for(a: dict) -> str:
    """エージェント定義から system プロンプトを組み立てる。"""
    return (
        f"あなたは「{a['name']}」という業務特化のAIエージェントです。"
        f"入力として「{a['in']}」を受け取り、「{a['out']}」を生成します。"
        "余計な前置きや説明は書かず、そのまま使える成果物だけを日本語で出力してください。"
        "情報が不足している場合は、妥当な前提を置いて成果物を作り、末尾に確認事項を簡潔に添えてください。"
    )


if __name__ == "__main__":
    # ワークフローのステップ解決を確認
    for wid, wf in WORKFLOWS.items():
        assert all(sid in AGENTS for sid in wf["steps"]), f"unknown step in {wid}"
    print(f"agents={len(AGENTS)} workflows={len(WORKFLOWS)}")
    print("sample system:", system_for(AGENTS["t1"])[:60], "...")
