import discord
import random
import asyncio
from discord import app_commands
from discord.ext import commands
from core.supabase_client import get_table
from core.utils import fmt_money, log_info, now_vn
from core.economy import update_balance

BETTING_TIME = 30  # 30 giây cược

class TaiXiu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bets = {}  # {user_id: {"cua": "tai", "amount": 10000}}
        self.running = False
        self.hu_taixiu = 1_000_000

    @app_commands.command(name="game_taixiu", description="Bắt đầu một ván Tài Xỉu")
    async def game_taixiu(self, interaction: discord.Interaction):
        if self.running:
            await interaction.response.send_message("🎲 Một ván đang diễn ra, hãy chờ kết thúc!")
            return

        self.running = True
        self.bets = {}
        msg = await interaction.response.send_message(embed=self._create_embed(30))
        log_info(f"Ván Tài Xỉu mới bắt đầu bởi {interaction.user.id}")

        for sec in range(BETTING_TIME, 0, -5):
            await asyncio.sleep(5)
            await msg.edit(embed=self._create_embed(sec))

        await asyncio.sleep(1)
        await self._ket_thuc_van(interaction, msg)

    async def _ket_thuc_van(self, interaction, msg):
        dice = [random.randint(1, 6) for _ in range(3)]
        tong = sum(dice)
        ketqua_tai = "Tài" if tong >= 11 else "Xỉu"
        chanle = "Chẵn" if tong % 2 == 0 else "Lẻ"

        get_table("taixiu_history").insert({
            "dice": dice,
            "total": tong,
            "result_tai": ketqua_tai,
            "result_chan": chanle,
            "created_at": now_vn().isoformat()
        }).execute()

        embed = discord.Embed(
            title="🎲 Kết quả Tài Xỉu",
            description=f"🎯 Xúc xắc: {dice[0]} + {dice[1]} + {dice[2]} = **{tong}**\n🏁 Kết quả: **{ketqua_tai}** ({chanle})",
            color=discord.Color.green()
        )
        await msg.edit(embed=embed)
        self.running = False

    def _create_embed(self, countdown):
        embed = discord.Embed(
            title="🎮 TÀI XỈU #1",
            description=(
                "Tỉ lệ cược: Tài/Xỉu x1.9 | Chẵn/Lẻ x1.9\n"
                "Nổ hũ khi ra bộ ba giống nhau 🎰\n\n"
                "⚫: **Tài**\n⚪: **Xỉu**\n🟣: **Chẵn**\n🟡: **Lẻ**\n\n"
                f"⏳ Kết thúc trong **{countdown} giây**.\n"
                "Powered by Nhật Minh"
            ),
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 HŨ TÀI XỈU", value=fmt_money(self.hu_taixiu))
        embed.add_field(name="🔮 Soi cầu", value=self._load_soi_cau(), inline=False)
        return embed

    def _load_soi_cau(self):
        data = get_table("taixiu_history").select("result_tai,result_chan").order("created_at", desc=True).limit(10).execute()
        if not data.data:
            return "Chưa có dữ liệu cầu."
        row_tai = " ".join(["⚫" if d["result_tai"] == "Tài" else "⚪" for d in data.data])
        row_chan = " ".join(["🟣" if d["result_chan"] == "Chẵn" else "🟡" for d in data.data])
        return f"{row_tai}\n{row_chan}"

async def setup(bot):
    await bot.add_cog(TaiXiu(bot))
