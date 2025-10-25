import discord
from discord import app_commands
from discord.ext import commands
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from datetime import timedelta

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Xem hồ sơ người chơi của bạn")
    async def profile(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        table = get_table("profiles")

        result = table.select("*").eq("user_id", user_id).execute()
        if not result.data:
            table.insert({"user_id": user_id, "balance": 0, "games_played": 0}).execute()
            balance = 0
            games = 0
            total_won = 0
        else:
            data = result.data[0]
            balance = data.get("balance", 0)
            games = data.get("games_played", 0)
            total_won = data.get("total_won", 0)

        embed = discord.Embed(
            title=f"Hồ sơ của {interaction.user.name}",
            description=f"🪙 Số dư: {fmt_money(balance)}\n🎮 Số ván chơi: {games}\n🏆 Tổng thắng: {fmt_money(total_won)}",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Nhận thưởng hàng ngày (500.000 xu)")
    async def daily(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        table = get_table("profiles")
        now = now_vn()

        data = table.select("*").eq("user_id", user_id).execute()
        if not data.data:
            table.insert({"user_id": user_id, "balance": 500000, "last_daily": now.isoformat()}).execute()
            await interaction.response.send_message(f"🎁 Bạn nhận được 500.000 🪙 hôm nay!")
            return

        last_daily_str = data.data[0].get("last_daily")
        if last_daily_str:
            last_daily = now.fromisoformat(last_daily_str)
            if (now - last_daily) < timedelta(hours=24):
                await interaction.response.send_message("⏳ Bạn đã nhận thưởng hôm nay rồi, quay lại sau 24 giờ.")
                return

        new_balance = data.data[0]["balance"] + 500000
        table.update({"balance": new_balance, "last_daily": now.isoformat()}).eq("user_id", user_id).execute()
        await interaction.response.send_message("🎁 Bạn nhận được **500.000 🪙** hôm nay! Quay lại vào ngày mai nhé.")
        log_info(f"Người chơi {user_id} nhận daily 500.000 xu.")

async def setup(bot):
    await bot.add_cog(Profile(bot))
