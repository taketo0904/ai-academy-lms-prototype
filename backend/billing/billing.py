"""
課金・エンタイトルメント — リファレンス実装（④ アカウント・課金・不正対策）。

無料 / 標準 / プレミアム の3プラン。プラットフォーム内完結（サービス側でAPIコスト負担）前提。
- プラン判定・利用回数メータリング・残数計算（純ロジック・依存なし・実行確認可）
- 決済（Stripe を想定）・電話番号認証（SMS OTP を想定）は外部呼び出しのためスタブ

想定エンドポイント（FastAPI で api/ に組み込む）:
  GET  /v1/me/entitlement            現在プラン・残数
  POST /v1/billing/checkout          Stripe Checkout セッション作成 → URL 返却
  POST /v1/billing/webhook           Stripe Webhook（支払い完了→有効化、解約→無料化）
  POST /v1/auth/otp/send             SMS OTP 送信（無料乱用・不正防止）
  POST /v1/auth/otp/verify           OTP 検証
※ このリポジトリでは決済/SMS部分は未実行（要 Stripe / Twilio キーとデプロイ）。
"""
from __future__ import annotations

# --- プラン定義（フロントの料金プランと一致） ---
PLANS = {
    "free":     {"label": "無料",       "price_jpy": 0,    "monthly_runs": 1,    "downloads": 0},
    "standard": {"label": "標準",       "price_jpy": 4980, "monthly_runs": 5,    "downloads": 20},
    "premium":  {"label": "プレミアム", "price_jpy": 9800, "monthly_runs": None, "downloads": None},  # None = 無制限
}


def entitlement(plan: str) -> dict:
    return PLANS.get(plan, PLANS["free"])


def can_run(plan: str, used_this_month: int) -> bool:
    """今月あと実行できるか（None=無制限）。"""
    lim = entitlement(plan)["monthly_runs"]
    return lim is None or used_this_month < lim


def remaining(plan: str, used_this_month: int):
    """残り実行回数。無制限は None。"""
    lim = entitlement(plan)["monthly_runs"]
    return None if lim is None else max(0, lim - used_this_month)


# --- 利用メータリング（本番はDB＋月次リセット。ここはインメモリ参考実装） ---
class UsageStore:
    def __init__(self) -> None:
        self._d: dict[str, int] = {}

    def incr(self, user_id: str) -> int:
        self._d[user_id] = self._d.get(user_id, 0) + 1
        return self._d[user_id]

    def get(self, user_id: str) -> int:
        return self._d.get(user_id, 0)

    def reset_month(self) -> None:
        self._d.clear()


# --- 決済（Stripe 想定・スタブ） ---
def create_checkout_session(user_id: str, plan: str) -> dict:
    """本番: stripe.checkout.Session.create(mode='subscription', ...) を呼ぶ。"""
    price = entitlement(plan)["price_jpy"]
    return {
        "checkout_url": f"https://checkout.example/stub?user={user_id}&plan={plan}&jpy={price}",
        "plan": plan,
    }


def handle_webhook(event: dict) -> dict:
    """Stripe Webhook を受けて、有効化 / 無料化 の指示を返す（署名検証は本番で必須）。"""
    typ = event.get("type")
    data = event.get("data", {})
    if typ == "checkout.session.completed":
        return {"action": "activate", "user_id": data.get("client_reference_id"),
                "plan": (data.get("metadata") or {}).get("plan", "standard")}
    if typ == "customer.subscription.deleted":
        return {"action": "downgrade_free", "user_id": data.get("client_reference_id")}
    return {"action": "ignore"}


# --- 電話番号認証（SMS OTP・無料乱用/不正防止・スタブ） ---
def send_otp(phone: str) -> dict:
    """本番: Twilio Verify などで OTP を送信。"""
    return {"sent": True, "phone": phone}  # TODO: SMS 送信


def verify_otp(phone: str, code: str) -> bool:
    """本番: Twilio Verify で検証。"""
    return bool(code)  # TODO: 実検証


if __name__ == "__main__":
    # 純ロジックの実行確認
    assert can_run("free", 0) and not can_run("free", 1)
    assert can_run("standard", 4) and not can_run("standard", 5)
    assert can_run("premium", 99999)
    assert remaining("free", 0) == 1 and remaining("free", 1) == 0
    assert remaining("standard", 2) == 3
    assert remaining("premium", 100) is None
    u = UsageStore()
    assert u.incr("u1") == 1 and u.incr("u1") == 2 and u.get("u1") == 2
    print("billing logic OK:",
          {p: (entitlement(p)["price_jpy"], entitlement(p)["monthly_runs"]) for p in PLANS})
