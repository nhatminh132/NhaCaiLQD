import discord, random
from discord.ext import commands
from discord import app_commands
from core.supabase_client import get_table
from core.economy import update_balance
from core.utils import fmt_money, now_vn, log_info

ICONS = ["🦀", "🐟", "🦌", "🦋", "🐔", "🍐"]

class BauCua(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bau_cua", description="🦀 Chơi Bầu Cua – chọn 1 biểu tượng, ăn x6 nếu trúng!")
    async def bau_cua(self, interaction: discord.Interaction, lua_chon: str, tien_cuoc: int):
        lua_chon = lua_chon.lower()
        if lua_chon not in ["cua", "ca", "huou", "bau", "ga", "nai"]:
            await interaction.response.send_message("❌ Lựa chọn không hợp lệ! (cua/ca/huou/bau/ga/nai)")
            return

        # Lấy số dư
        profile = get_table("profiles").select("balance").eq("user_id", interaction.user.id).execute()
        if not profile.data or profile.data[0]["balance"] < tien_cuoc:
            await interaction.response.send_message("💸 Bạn không đủ tiền để cược.")
            return

        # Giảm tiền
        update_balance(interaction.user.id, -tien_cuoc, "Cược Bầu Cua")

        # Quay
        roll = random.choices(ICONS, k=3)
        result_str = " ".join(roll)
        if any(lua_chon in icon for icon in roll):
            win = tien_cuoc * 6
            await update_balance(interaction.user.id, win, "Thắng Bầu Cua")
            result = f"🎉 Bạn TRÚNG! Nhận {fmt_money(win)} 🪙"
        else:
            result = "😢 Bạn thua mất rồi."

        embed = discord.Embed(
            title="🎲 Kết quả Bầu Cua",
            description=f"{result_str}\n\n{result}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        log_info(f"{interaction.user.id} chơi Bầu Cua kết quả: {roll}")

async def setup(bot):
    await bot.add_cog(BauCua(bot))
