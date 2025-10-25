import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from core.economy import update_balance

class Loan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="loan_offer", description="Tạo đề nghị cho người chơi khác vay tiền")
    async def loan_offer(self, interaction: discord.Interaction, borrower: discord.User, amount: int, repay: int, hours: int):
        lender_id = interaction.user.id
        borrower_id = borrower.id

        if repay <= amount:
            await interaction.response.send_message("❌ Số tiền trả phải lớn hơn tiền vay.")
            return

        due_time = now_vn() + timedelta(hours=hours)
        table = get_table("peer_loans")
        table.insert({
            "lender_id": lender_id,
            "borrower_id": borrower_id,
            "amount": amount,
            "repay_total": repay,
            "due_time": due_time.isoformat(),
            "created_at": now_vn().isoformat()
        }).execute()

        embed = discord.Embed(
            title="💸 Đề nghị cho vay",
            description=f"{interaction.user.mention} cho {borrower.mention} vay {fmt_money(amount)}.\n"
                        f"Người vay cần trả: {fmt_money(repay)} trong {hours}h.",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Người vay có thể chấp nhận bằng /loan_accept <loan_id>")
        await interaction.response.send_message(embed=embed)
        log_info(f"{lender_id} cho {borrower_id} vay {amount} -> {repay} trong {hours}h")

    @app_commands.command(name="loan_accept", description="Chấp nhận khoản vay từ người khác")
    async def loan_accept(self, interaction: discord.Interaction, loan_id: int):
        user_id = interaction.user.id
        table = get_table("peer_loans")
        prof = get_table("profiles")

        res = table.select("*").eq("id", loan_id).execute()
        if not res.data:
            await interaction.response.send_message("❌ Không tìm thấy khoản vay này.")
            return

        loan = res.data[0]
        if loan["borrower_id"] != user_id:
            await interaction.response.send_message("❌ Khoản vay này không dành cho bạn.")
            return

        lender = prof.select("balance").eq("user_id", loan["lender_id"]).execute().data
        if not lender or lender[0]["balance"] < loan["amount"]:
            await interaction.response.send_message("⚠️ Người cho vay không đủ tiền.")
            return

        # Chuyển tiền
        prof.update({"balance": lender[0]["balance"] - loan["amount"]}).eq("user_id", loan["lender_id"]).execute()
        borrower_data = prof.select("balance").eq("user_id", user_id).execute().data
        borrower_balance = borrower_data[0]["balance"] if borrower_data else 0
        prof.update({"balance": borrower_balance + loan["amount"]}).eq("user_id", user_id).execute()

        await interaction.response.send_message(f"✅ Bạn đã nhận {fmt_money(loan['amount'])} từ {loan['lender_id']}.")
        log_info(f"{user_id} nhận vay {loan['amount']} từ {loan['lender_id']}.")

    @app_commands.command(name="loan_status", description="Xem các khoản vay đang hoạt động")
    async def loan_status(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        table = get_table("peer_loans")
        res = table.select("*").or_(f"lender_id.eq.{user_id},borrower_id.eq.{user_id}").execute()

        if not res.data:
            await interaction.response.send_message("Không có khoản vay nào đang hoạt động.")
            return

        desc = ""
        for l in res.data:
            due = datetime.fromisoformat(l["due_time"])
            remain = (due - now_vn()).total_seconds() / 3600
            desc += f"💸 {l['lender_id']} ➜ {l['borrower_id']} {fmt_money(l['amount'])} ➜ {fmt_money(l['repay_total'])} ({remain:.1f}h còn lại)\n"

        embed = discord.Embed(title="📜 Khoản vay đang hoạt động", description=desc, color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Loan(bot))
