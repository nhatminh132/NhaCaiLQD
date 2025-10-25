import discord, random
from discord.ext import commands
from discord import app_commands
from core.economy import update_balance
from core.utils import fmt_money

class Baccarat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="baccarat", description="♠️ Baccarat – chọn cửa Banker hoặc Player")
    async def baccarat(self, interaction: discord.Interaction, cua: str, tien_cuoc: int):
        cua = cua.lower()
        if cua not in ["banker", "player"]:
            await interaction.response.send_message("❌ Cửa không hợp lệ! (banker/player)")
            return

        cards = [random.randint(1, 9) for _ in range(4)]
        player = (cards[0] + cards[1]) % 10
        banker = (cards[2] + cards[3]) % 10
        result = "player" if player > banker else "banker" if banker > player else "tie"

        if result == cua:
            win = int(tien_cuoc * 1.95)
            await update_balance(interaction.user.id, win, "Thắng Baccarat")
            msg = f"🎉 {result.upper()} thắng! Bạn nhận {fmt_money(win)} 🪙"
        else:
            await update_balance(interaction.user.id, -tien_cuoc, "Thua Baccarat")
            msg = f"😢 {result.upper()} thắng, bạn thua cược."

        embed = discord.Embed(
            title="♠️ Baccarat",
            description=f"Player: {player}\nBanker: {banker}\n\n{msg}",
            color=discord.Color.dark_blue()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Baccarat(bot))
