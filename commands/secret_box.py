import discord
import random
from discord import app_commands
from discord.ext import commands
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from core.economy import update_balance

BOX_PRICES = {"dong": 20_000, "bac": 100_000, "vang": 500_000}
BOX_REWARDS = {
    "dong": (10_000, 100_000),
    "bac": (50_000, 500_000),
    "vang": (300_000, 2_000_000)
}

class SecretBox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="box", description="Mở hộp bí ẩn (Đồng, Bạc, Vàng)")
    async def box(self, interaction: discord.Interaction, loai: str):
        loai = loai.lower()
        if loai not in BOX_PRICES:
            await interaction.response.send_message("❌ Loại hộp không hợp lệ. Chọn: đồng, bạc, hoặc vàng.")
            return

        price = BOX_PRICES[loai]
        prof = get_table("profiles")
        data = prof.select("balance").eq("user_id", interaction.user.id).execute()
        balance = data.data[0]["balance"] if data.data else 0

        if balance < price:
            await interaction.response.send_message(f"Bạn cần {fmt_money(price)} để mở hộp **{loai}**.")
            return

        prof.update({"balance": balance - price}).eq("user_id", interaction.user.id).execute()

        # Random phần thưởng
        min_reward, max_reward = BOX_REWARDS[loai]
        reward = random.randint(min_reward, max_reward)
        bonus = 1.0

        if random.random() < 0.05:  # 5% chance "siêu phẩm"
            bonus = 3.0
            reward = int(reward * bonus)
            msg = "🌟 SIÊU PHẨM!"
        else:
            msg = "🎁 Bạn mở hộp thành công!"

        await update_balance(interaction.user.id, reward, f"Mở hộp {loai.capitalize()}")
        get_table("secret_boxes").insert({
            "user_id": interaction.user.id,
            "box_type": loai,
            "reward": reward,
            "opened_at": now_vn().isoformat()
        }).execute()

        embed = discord.Embed(
            title=f"📦 Hộp {loai.capitalize()}",
            description=f"{msg}\nPhần thưởng: {fmt_money(reward)} 🪙",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)
        log_info(f"{interaction.user.id} mở hộp {loai} và nhận {reward}")

async def setup(bot):
    await bot.add_cog(SecretBox(bot))
