from core.supabase_client import get_table
from core.utils import now_vn, log_info, log_warn, fmt_money

# ==============================
# Cập nhật số dư người chơi
# ==============================
async def update_balance(user_id: int, amount: int, reason: str):
    table = get_table("profiles")
    trans_table = get_table("transactions")

    # Lấy số dư hiện tại
    current = table.select("balance").eq("user_id", user_id).execute()
    if not current.data:
        table.insert({"user_id": user_id, "balance": 0}).execute()
        current_balance = 0
    else:
        current_balance = current.data[0]["balance"]

    new_balance = max(0, current_balance + amount)
    table.update({"balance": new_balance}).eq("user_id", user_id).execute()

    # Lưu lịch sử giao dịch
    trans_table.insert({
        "user_id": user_id,
        "amount": amount,
        "reason": reason,
        "created_at": now_vn().isoformat()
    }).execute()

    log_info(f"Cập nhật số dư {user_id}: {fmt_money(current_balance)} ➜ {fmt_money(new_balance)} ({reason})")
    return new_balance

# ==============================
# Thuế nhà cái
# ==============================
async def casino_tax(user_id: int, win_amount: int, tax_rate: float = 0.03):
    tax = int(win_amount * tax_rate)
    net = win_amount - tax
    await update_balance(user_id, net, f"Thắng game (sau thuế {tax_rate*100:.0f}%)")
    fund = get_table("casino_fund")
    fund.insert({"source": user_id, "tax": tax, "created_at": now_vn().isoformat()}).execute()
    log_info(f"Thuế nhà cái: {fmt_money(tax)} từ người chơi {user_id}")
    return net
