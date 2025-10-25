import discord, random, asyncio
from discord.ext import commands
from discord import app_commands
from core.economy import update_balance
from core.utils import fmt_money

HORSES = ["🐎", "🦄", "🐴", "🐐", "🐆"]

class HorseRace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_race = False

    @app_commands.command(name="horse_race", description="🐎 Đua ngựa – cược xem con nào về nhất!")
    async def horse_race(self, interaction: discord.Interaction, lua_chon: int, tien_cuoc: int):
        if self.active_race:
            await interaction.response.send_message("⏳ Đang có cuộc đua diễn ra, vui lòng chờ kết thúc.")
            return

        self.active_race = True
        msg = await interaction.response.send_message("🐴 Bắt đầu đua trong 3 giây...")
        await asyncio.sleep(3)

        track = {i: 0 for i in range(5)}
        while True:
            await asyncio.sleep(1)
            move = random.choice(list(track.keys()))
            track[move] += 1

            race_view = "\n".join([f"{HORSES[i]} {'-'*track[i]}🏁" for i in range(5)])
            await msg.edit(content=f"🏇 Cuộc đua đang diễn ra!\n\n{race_view}")

            if track[move] >= 8:
                winner = move
                break

        if lua_chon == winner:
            win = int(tien_cuoc * 5)
            await update_balance(interaction.user.id, win, "Thắng Đua Ngựa")
            result = f"🎉 Ngựa {HORSES[winner]} về nhất! Bạn nhận {fmt_money(win)} 🪙"
        else:
            await update_balance(interaction.user.id, -tien_cuoc, "Thua Đua Ngựa")
            result = f"😢 Ngựa {HORSES[winner]} thắng, bạn thua cược."

        await msg.edit(content=f"🏁 Kết thúc!\n\n{result}")
        self.active_race = False

async def setup(bot):
    await bot.add_cog(HorseRace(bot))
