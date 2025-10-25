import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from core.supabase_client import get_table
from core.utils import now_vn, fmt_money, log_info, log_warn

MAX_LOAN = 5_000_000
INTEREST_PER_HOUR = 0.05  # 5% mỗi giờ

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bank_loan", description="Vay tiền từ ngân hàng trung tâm")
    async def bank_loan(self, interaction: discord.Interaction, amount: int):
        user_id = interaction.user.id
        if amount <= 0 or amount > MAX_LOAN:
            await interaction.response.send_message("❌ Số tiền vay không hợp lệ (tối đa 5.000.000 🪙).")
            return

        table = get_table("bank_loans")
        prof = get_table("profiles")
        active = table.select("*").eq("user_id", user_id).execute()

        if active.data:
            await interaction.response.send_message("⚠️ Bạn đang có khoản vay chưa trả.")
            return

        due_time = now_vn() + timedelta(hours=24)
        table.insert({
            "user_id": user_id,
            "amount": amount,
            "interest": INTEREST_PER_HOUR,
            "borrowed_at": now_vn().isoformat(),
            "due_at": due_time.isoformat()
        }).execute()

        data = prof.select("balance").eq("user_id", user_id).execute()
        bal = data.data[0]["balance"] if data.data else 0
        prof.update({"balance": bal + amount}).eq("user_id", user_id).execute()

        await interaction.response.send_message(f"🏦 Bạn đã vay {fmt_money(amount)}. Lãi 5%/giờ. Hạn trả: 24h.")
        log_info(f"{user_id} vay {amount} từ ngân hàng.")

    @app_commands.command(name="bank_status", description="Xem khoản vay ngân hàng của bạn")
    async def bank_status(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        table = get_table("bank_loans")
        res = table.select("*").eq("user_id", user_id).execute()

        if not res.data:
            await interaction.response.send_message("✅ Bạn không có khoản vay nào đang hoạt động.")
            return

        loan = res.data[0]
        borrowed = datetime.fromisoformat(loan["borrowed_at"])
        now = now_vn()
        hours_passed = (now - borrowed).total_seconds() / 3600
        interest = int(loan["amount"] * loan["interest"] * hours_passed)
        total = loan["amount"] + interest

        embed = discord.Embed(
            title="💰 Khoản vay ngân hàng",
            description=f"Gốc: {fmt_money(loan['amount'])}\nLãi tạm tính: {fmt_money(interest)}\nTổng phải trả: {fmt_money(total)}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bank_repay", description="Trả khoản vay ngân hàng")
    async def bank_repay(self, interaction: discord.Interaction, amount: int):
        user_id = interaction.user.id
        loan_table = get_table("bank_loans")
        prof = get_table("profiles")

        res = loan_table.select("*").eq("user_id", user_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ Bạn không có khoản vay nào.")
            return

        loan = res.data[0]
        balance_data = prof.select("balance").eq("user_id", user_id).execute()
        balance = balance_data.data[0]["balance"]

        borrowed = datetime.fromisoformat(loan["borrowed_at"])
        hours_passed = (now_vn() - borrowed).total_seconds() / 3600
        total_due = loan["amount"] + int(loan["amount"] * loan["interest"] * hours_passed)

        if amount > balance:
            await interaction.response.send_message("❌ Bạn không đủ tiền để trả khoản này.")
            return

        if amount >= total_due:
            prof.update({"balance": balance - total_due}).eq("user_id", user_id).execute()
            loan_table.delete().eq("user_id", user_id).execute()
            await interaction.response.send_message("✅ Bạn đã trả hết khoản vay ngân hàng.")
            log_info(f"{user_id} đã tất toán khoản vay.")
        else:
            prof.update({"balance": balance - amount}).eq("user_id", user_id).execute()
            new_amount = total_due - amount
            loan_table.update({"amount": new_amount}).eq("user_id", user_id).execute()
            await interaction.response.send_message(f"💰 Bạn đã trả {fmt_money(amount)}. Còn lại {fmt_money(new_amount)} cần thanh toán.")

async def setup(bot):
    await bot.add_cog(Bank(bot))
