import discord
import random
import asyncio
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from core.economy import update_balance

LOTTERY_PRICE = 100_000
SCRATCH_PRICE = 50_000

class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_big_win = None  # để kiểm soát trúng giải lớn

    # Vé số thường: công bố 8h & 17h
    @app_commands.command(name="game_lottery", description="Mua vé số thường, kết quả công bố 8h sáng và 17h chiều")
    async def game_lottery(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        prof = get_table("profiles")
        data = prof.select("balance").eq("user_id", user_id).execute()
        balance = data.data[0]["balance"] if data.data else 0

        if balance < LOTTERY_PRICE:
            await interaction.response.send_message("❌ Bạn không đủ tiền để mua vé số (100.000 🪙).")
            return

        prof.update({"balance": balance - LOTTERY_PRICE}).eq("user_id", user_id).execute()

        get_table("lottery_tickets").insert({
            "user_id": user_id,
            "type": "daily",
            "bought_at": now_vn().isoformat()
        }).execute()

        await interaction.response.send_message("🎟️ Bạn đã mua **1 vé số thường**, kết quả công bố vào 8h sáng hoặc 17h chiều hôm nay!")

    # Vé số cào: biết kết quả ngay
    @app_commands.command(name="game_scratch", description="Mua vé số cào — biết kết quả ngay")
    async def game_scratch(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        prof = get_table("profiles")
        data = prof.select("balance").eq("user_id", user_id).execute()
        balance = data.data[0]["balance"] if data.data else 0

        if balance < SCRATCH_PRICE:
            await interaction.response.send_message("❌ Bạn không đủ tiền để mua vé số cào (50.000 🪙).")
            return

        prof.update({"balance": balance - SCRATCH_PRICE}).eq("user_id", user_id).execute()

        # Xác suất: 85% (4 số), 10% (5 số), 5% (6 số)
        roll = random.random()
        reward = 0
        matched = 0

        if roll < 0.85:
            matched = 4
            reward = 10_000
        elif roll < 0.95:
            matched = 5
            reward = 500_000
        else:
            matched = 6
            if self.last_big_win and (now_vn() - self.last_big_win) < timedelta(hours=12):
                reward = 500_000  # bị giảm vì vừa có người trúng lớn
            else:
                reward = 10_000_000
                self.last_big_win = now_vn()

        await update_balance(user_id, reward, f"Trúng vé số cào ({matched} số đúng)")
        embed = discord.Embed(
            title="🎰 Kết quả Vé Số Cào",
            description=f"Bạn trúng {matched} số đúng!\nPhần thưởng: {fmt_money(reward)}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        log_info(f"Vé số cào: {user_id} trúng {matched} số ({reward} xu)")

async def setup(bot):
    await bot.add_cog(Lottery(bot))
lottery.py
