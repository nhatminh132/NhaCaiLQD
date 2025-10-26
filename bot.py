# ==========================================================
# 🏦 BOT CASINO CHÍNH - HỖ TRỢ SUPABASE + FLASK KEEP-ALIVE
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
import importlib

# ==========================================================
# ⚙️ KHỞI TẠO BIẾN MÔI TRƯỜNG
# ==========================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# ==========================================================
# 🤖 KHỞI TẠO BOT DISCORD
# ==========================================================
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ==========================================================
# 🔌 KHỞI TẠO SUPABASE
# ==========================================================
try:
    init_supabase()
    log_info("Supabase đã sẵn sàng ✅")
except Exception as e:
    log_error(f"Lỗi khi khởi tạo Supabase: {e}")
    raise

# ==========================================================
# 🎉 SỰ KIỆN KHI BOT KHỞI ĐỘNG
# ==========================================================
@bot.event
async def on_ready():
    log_info(f"Bot đã đăng nhập thành công dưới tên: {bot.user}")

    try:
        if GUILD_ID:
            synced = await tree.sync(guild=discord.Object(id=int(GUILD_ID)))
            log_info(f"Đã đồng bộ {len(synced)} lệnh slash cho server ID {GUILD_ID}")
        else:
            synced = await tree.sync()
            log_warn(f"Không có GUILD_ID — đã đồng bộ {len(synced)} lệnh slash toàn cầu.")
    except Exception as e:
        log_error(f"Lỗi khi sync lệnh: {e}")

# ==========================================================
# 👤 /profile — HIỂN THỊ HỒ SƠ NGƯỜI CHƠI
# ==========================================================
@tree.command(name="profile", description="Xem hồ sơ người chơi")
async def profile(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    await interaction.response.defer(thinking=True)

    try:
        rows = query("users", filters=f"&email=eq.{user.id}", limit=1)
        if not rows:
            await interaction.followup.send(f"❌ Người chơi `{user.display_name}` chưa có trong hệ thống.")
            return

        u = rows[0]
        embed = discord.Embed(
            title=f"Hồ sơ của {user.display_name}",
            color=discord.Color.gold(),
            description=(
                f"💰 **Số dư:** {u.get('balance', 0):,} Mcoin\n"
                f"🎮 **Tổng cược:** {u.get('total_bet', 0):,}\n"
                f"🏆 **Tổng thắng:** {u.get('total_won', 0):,}"
            )
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải dữ liệu: `{e}`")

# ==========================================================
# 💸 /chuyentien — CHUYỂN MCOIN GIỮA NGƯỜI CHƠI
# ==========================================================
@tree.command(name="chuyentien", description="Chuyển Mcoin cho người chơi khác")
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
            await interaction.followup.send("❌ Bạn chưa đăng ký tài khoản.")
            return
        if not nhan:
            await interaction.followup.send("❌ Người nhận chưa có tài khoản.")
            return

        balance_gui = gui[0].get("balance", 0)
        if balance_gui < so_tien:
            await interaction.followup.send("❌ Bạn không đủ Mcoin để chuyển.")
            return

        update("users", f"email=eq.{nguoi_gui.id}", {"balance": balance_gui - so_tien})
        update("users", f"email=eq.{nguoi_nhan.id}", {"balance": nhan[0].get('balance', 0) + so_tien})

        await interaction.followup.send(
            f"✅ **{nguoi_gui.display_name}** đã chuyển **{so_tien:,} Mcoin** cho **{nguoi_nhan.display_name}**!"
        )
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi thực hiện chuyển tiền: `{e}`")

# ==========================================================
# 🎮 /game — GỌI GAME MODULE ĐỘNG (LOADSTRING)
# ==========================================================
@tree.command(name="game", description="Chơi game tại casino 🎲")
@app_commands.describe(tro_choi="Tên game muốn chơi (vd: taixiu, bau_cua, slots, horse_race)")
async def game(interaction: discord.Interaction, tro_choi: str):
    await interaction.response.defer(thinking=True)

    try:
        module_name = f"games.{tro_choi}"
        file_path = f"./games/{tro_choi}.py"
        if not os.path.exists(file_path):
            await interaction.followup.send(f"❌ Game `{tro_choi}` không tồn tại.")
            return

        game_module = importlib.import_module(module_name)
        if hasattr(game_module, "start_game"):
            await game_module.start_game(interaction)
        else:
            await interaction.followup.send(f"⚠️ Game `{tro_choi}` chưa có hàm `start_game()`.")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải game: `{e}`")

# ==========================================================
# 🏦 /register — ĐĂNG KÝ TÀI KHOẢN NGƯỜI CHƠI
# ==========================================================
@tree.command(name="register", description="Đăng ký tài khoản mới trong casino")
async def register(interaction: discord.Interaction):
    user = interaction.user
    await interaction.response.defer(thinking=True)

    try:
        exists = query("users", filters=f"&email=eq.{user.id}", limit=1)
        if exists:
            await interaction.followup.send("⚠️ Bạn đã có tài khoản rồi.")
            return

        insert("users", {"email": str(user.id), "balance": 100000})
        await interaction.followup.send(f"🎉 Đăng ký thành công! Bạn nhận được **100,000 Mcoin** miễn phí.")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi đăng ký: `{e}`")

# ==========================================================
# 🚀 CHẠY BOT VÀ FLASK GIỮ CHO RENDER KHÔNG TẮT
# ==========================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive and running on Render!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    log_info("Đang khởi chạy bot Discord...")
    bot.run(TOKEN)
