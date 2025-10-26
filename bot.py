# ==========================================================
# 🎰 BOT CASINO — Phiên bản auto-sync ổn định (Render + Discord.py)
# ==========================================================
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from core.supabase_client import init_supabase, query, insert, update
from core.utils import log_info, log_warn, log_error
from flask import Flask
import threading

# ==========================================================
# ⚙️ Tải biến môi trường và setup
# ==========================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ==========================================================
# 🔗 Kết nối Supabase
# ==========================================================
try:
    init_supabase()
    log_info("✅ Supabase đã sẵn sàng.")
except Exception as e:
    log_error(f"❌ Lỗi khi khởi tạo Supabase: {e}")
    raise

# ==========================================================
# 🚀 Sự kiện khởi động bot
# ==========================================================
@bot.event
async def on_ready():
    log_info(f"🤖 Bot đã đăng nhập thành công dưới tên: {bot.user}")
    guild_obj = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

    # Thử đồng bộ slash command (tối đa 3 lần)
    for i in range(3):
        try:
            if guild_obj:
                synced = await tree.sync(guild=guild_obj)
                log_info(f"🔄 Đồng bộ {len(synced)} lệnh slash cho server ID {GUILD_ID}")
            else:
                synced = await tree.sync()
                log_info(f"🌍 Đồng bộ {len(synced)} lệnh slash toàn cầu")
            break
        except Exception as e:
            log_warn(f"Lỗi khi sync lần {i+1}: {e}")
            await asyncio.sleep(5)

# ==========================================================
# 👤 /profile — Xem hồ sơ người chơi
# ==========================================================
@tree.command(name="profile", description="Xem hồ sơ người chơi")
async def profile(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    await interaction.response.defer(thinking=True)

    try:
        rows = query("users", filters=f"&email=eq.{user.id}", limit=1)
        if not rows:
            # Nếu chưa có dữ liệu, tự tạo hồ sơ mặc định
            insert("users", {"email": str(user.id), "balance": 100000})
            await interaction.followup.send(
                f"🆕 Hồ sơ mới được tạo cho **{user.display_name}** với **100,000 Mcoin**!"
            )
            return

        u = rows[0]
        embed = discord.Embed(
            title=f"👤 Hồ sơ của {user.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="💰 Số dư", value=f"{u.get('balance', 0):,} Mcoin", inline=True)
        embed.add_field(name="🎮 Tổng cược", value=f"{u.get('total_bet', 0):,}", inline=True)
        embed.add_field(name="🏆 Tổng thắng", value=f"{u.get('total_won', 0):,}", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải hồ sơ: `{e}`")

# ==========================================================
# 💸 /chuyentien — Chuyển tiền giữa người chơi
# ==========================================================
@tree.command(name="chuyentien", description="Chuyển Mcoin cho người khác")
@app_commands.describe(nguoi_nhan="Người nhận tiền", so_tien="Số Mcoin cần chuyển")
async def chuyentien(interaction: discord.Interaction, nguoi_nhan: discord.User, so_tien: int):
    nguoi_gui = interaction.user
    await interaction.response.defer(thinking=True)

    if so_tien <= 0:
        await interaction.followup.send("❌ Số tiền phải lớn hơn 0.")
        return

    try:
        gui = query("users", filters=f"&email=eq.{nguoi_gui.id}", limit=1)
        nhan = query("users", filters=f"&email=eq.{nguoi_nhan.id}", limit=1)

        if not gui:
            insert("users", {"email": str(nguoi_gui.id), "balance": 100000})
            gui = query("users", filters=f"&email=eq.{nguoi_gui.id}", limit=1)
        if not nhan:
            insert("users", {"email": str(nguoi_nhan.id), "balance": 100000})
            nhan = query("users", filters=f"&email=eq.{nguoi_nhan.id}", limit=1)

        balance_gui = gui[0].get("balance", 0)
        if balance_gui < so_tien:
            await interaction.followup.send("💸 Bạn không đủ Mcoin để chuyển.")
            return

        update("users", f"email=eq.{nguoi_gui.id}", {"balance": balance_gui - so_tien})
        update("users", f"email=eq.{nguoi_nhan.id}", {"balance": nhan[0].get('balance', 0) + so_tien})

        await interaction.followup.send(
            f"✅ **{nguoi_gui.display_name}** đã chuyển **{so_tien:,} Mcoin** cho **{nguoi_nhan.display_name}**!"
        )

    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi chuyển tiền: `{e}`")

# ==========================================================
# 🎮 /game — Gọi game module động
# ==========================================================
@tree.command(name="game", description="Chơi game tại casino 🎲")
@app_commands.describe(tro_choi="Tên game muốn chơi (vd: taixiu, bau_cua, slots, horse_race)")
async def game(interaction: discord.Interaction, tro_choi: str):
    await interaction.response.defer(thinking=True)
    try:
        module_path = f"games/{tro_choi}.py"
        if not os.path.exists(module_path):
            await interaction.followup.send(f"❌ Game `{tro_choi}` không tồn tại.")
            return

        import importlib
        game_module = importlib.import_module(f"games.{tro_choi}")
        if hasattr(game_module, "start_game"):
            await game_module.start_game(interaction)
        else:
            await interaction.followup.send(f"⚠️ Game `{tro_choi}` chưa hoàn thiện.")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải game `{tro_choi}`: `{e}`")

# ==========================================================
# 🌐 Flask keep-alive (Render Free)
# ==========================================================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive and running on Render!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ==========================================================
# 🚀 Chạy bot
# ==========================================================
if __name__ == "__main__":
    log_info("🚀 Đang khởi chạy bot Discord...")
    bot.run(TOKEN)
