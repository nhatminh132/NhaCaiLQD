import discord, random
from discord.ext import commands
from discord import app_commands

ICONS = ["🍒", "🍋", "🍉", "⭐", "💎", "🔔"]

class Slots(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="🎰 Slot machine – chỉ để vui, không mất tiền")
    async def slots(self, interaction: discord.Interaction):
        result = [random.choice(ICONS) for _ in range(3)]
        msg = " ".join(result)
        if len(set(result)) == 1:
            note = "💎 JACKPOT! 3 hình giống nhau!"
        elif len(set(result)) == 2:
            note = "⭐ Gần trúng rồi!"
        else:
            note = "😅 Thử lại nhé!"

        embed = discord.Embed(title="🎰 Máy Slot", description=f"{msg}\n\n{note}", color=discord.Color.purple())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Slots(bot))
