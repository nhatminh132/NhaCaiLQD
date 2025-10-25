import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from core.supabase_client import get_table
from core.utils import fmt_money, now_vn, log_info
from core.economy import update_balance

class Event(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="event_info", description="Xem các sự kiện đang diễn ra")
    async def event_info(self, interaction: discord.Interaction):
        table = get_table("events")
        res = table.select("*").execute()
        if not res.data:
            await interaction.response.send_message("📭 Hiện không có sự kiện nào đang diễn ra.")
            return

        desc = ""
        for e in res.data:
            start = datetime.fromisoformat(e["start_time"]).strftime("%d/%m %H:%M")
            end = datetime.fromisoformat(e["end_time"]).strftime("%d/%m %H:%M")
            desc += f"🎯 **{e['name']}**\nThời gian: {start} - {end}\nGiải thưởng: {fmt_money(e['reward'])}\n\n"

        embed = discord.Embed(title="🔥 Sự kiện đang diễn ra", description=desc, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="event_join", description="Tham gia sự kiện hiện tại")
    async def event_join(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        events = get_table("events").select("*").execute()
        if not events.data:
            await interaction.response.send_message("Không có sự kiện nào để tham gia.")
            return

        active = [e for e in events.data if datetime.fromisoformat(e["start_time"]) <= now_vn() <= datetime.fromisoformat(e["end_time"])]
        if not active:
            await interaction.response.send_message("❌ Không có sự kiện nào đang diễn ra.")
            return

        evt = active[0]
        part = get_table("event_participants")
        check = part.select("*").eq("user_id", user_id).eq("event_id", evt["id"]).execute()
        if check.data:
            await interaction.response.send_message("✅ Bạn đã tham gia sự kiện này rồi.")
            return

        part.insert({"event_id": evt["id"], "user_id": user_id, "joined_at": now_vn().isoformat(), "score": 0}).execute()
        await interaction.response.send_message(f"🎉 Bạn đã tham gia sự kiện **{evt['name']}** thành công!")

    @app_commands.command(name="tournament_top", description="Xem bảng xếp hạng giải đấu hiện tại")
    async def tournament_top(self, interaction: discord.Interaction):
        table = get_table("event_participants")
        events = get_table("events").select("*").execute()
        if not events.data:
            await interaction.response.send_message("Không có giải đấu nào đang diễn ra.")
            return

        evt = events.data[0]
        ranks = table.select("*").eq("event_id", evt["id"]).order("score", desc=True).limit(10).execute().data
        desc = "\n".join([f"🏅 <@{r['user_id']}> — {r['score']} điểm" for r in ranks]) or "Chưa có ai tham gia"

        embed = discord.Embed(
            title=f"🏆 BXH Giải Đấu: {evt['name']}",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Event(bot))
