import discord
from discord import app_commands
from discord.ext import commands
from core.supabase_client import get_table
from core.utils import fmt_money, log_info

SUPER_ADMIN = 1121380060897742850

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def admin_check(self, user_id):
        table = get_table("admins")
        res = table.select("*").eq("user_id", user_id).execute()
        return bool(res.data or user_id == SUPER_ADMIN)

    @app_commands.command(name="admin_addadmin", description="Thêm admin mới (chỉ SuperAdmin)")
    async def admin_addadmin(self, interaction: discord.Interaction, user: discord.User):
        if interaction.user.id != SUPER_ADMIN:
            await interaction.response.send_message("❌ Bạn không có quyền thêm admin.")
            return

        table = get_table("admins")
        table.insert({"user_id": user.id}).execute()
        await interaction.response.send_message(f"✅ {user.mention} đã được thêm làm admin.")

    @app_commands.command(name="admin_balance", description="Quản lý số dư của người chơi (set/add/sub)")
    async def admin_balance(self, interaction: discord.Interaction, user: discord.User, action: str, amount: int):
        if not await self.admin_check(interaction.user.id):
            await interaction.response.send_message("❌ Bạn không có quyền dùng lệnh này.")
            return

        prof = get_table("profiles")
        data = prof.select("balance").eq("user_id", user.id).execute()
        balance = data.data[0]["balance"] if data.data else 0

        if action == "set":
            new_balance = amount
        elif action == "add":
            new_balance = balance + amount
        elif action == "sub":
            new_balance = max(0, balance - amount)
        else:
            await interaction.response.send_message("❌ Hành động không hợp lệ (set/add/sub).")
            return

        prof.update({"balance": new_balance}).eq("user_id", user.id).execute()
        await interaction.response.send_message(f"💰 Đã {action} số dư của {user.mention} ➜ {fmt_money(new_balance)}")
        log_info(f"Admin {interaction.user.id} chỉnh tiền {user.id} ({action} {amount})")

async def setup(bot):
    await bot.add_cog(Admin(bot))
