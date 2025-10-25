import discord, random
from discord.ext import commands
from discord import app_commands
from core.economy import update_balance
from core.utils import fmt_money

def draw_card():
    v = random.randint(1, 13)
    return min(v, 10)  # JQK = 10

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="🃏 Blackjack – ai gần 21 hơn thắng")
    async def blackjack(self, interaction: discord.Interaction, tien_cuoc: int):
        user_total = draw_card() + draw_card()
        dealer_total = draw_card() + draw_card()

        if user_total > dealer_total:
            win = int(tien_cuoc * 2)
            await update_balance(interaction.user.id, win, "Thắng Blackjack")
            result = f"🎉 Bạn thắng {fmt_money(win)}!"
        elif user_total == dealer_total:
            result = "😐 Hòa, tiền cược được hoàn lại."
        else:
            await update_balance(interaction.user.id, -tien_cuoc, "Thua Blackjack")
            result = "😢 Dealer thắng, bạn mất cược."

        embed = discord.Embed(
            title="🃏 Blackjack",
            description=f"Bạn: {user_total}\nDealer: {dealer_total}\n\n{result}",
            color=discord.Color.teal()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
