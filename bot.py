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
# 🔧 Tải biến môi trường
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
# 🧠 Hàm tự động khởi tạo người chơi nếu chưa có
# ==========================================================
async def ensure_user_exists(user_id: int):
    try:
        rows = query("users", filters=f"&email=eq.{user_id}", limit=1)
        if not rows:
            insert("users", {"email": str(user_id), "balance": 100000})
            log_info(f"✅ Đã tạo tài khoản mới cho user {user_id}")
        return True
    except Exception as e:
        log_warn(f"Lỗi khi kiểm tra/tạo tài khoản: {e}")
        return False

# ==========================================================
# 🚀 Khởi tạo Supabase
# ==========================================================
try:
    init_supabase()
    log_info("Supabase đã sẵn sàng ✅")
except Exception as e:
    log_error(f"Lỗi khi khởi tạo Supabase: {e}")
    raise

# ==========================================================
# ⚙️ Sự kiện on_ready
# ==========================================================
@bot.event
async def on_ready():
    log_info(f"Bot đã đăng nhập thành công dưới tên: {bot.user}")
    try:
        tree.clear_commands(guild=discord.Object(id=GUILD_ID))
        synced = await tree.sync(guild=discord.Object(id=GUILD_ID))
        log_info(f"Đã đồng bộ {len(synced)} lệnh slash cho server ID {GUILD_ID}")
    except Exception as e:
        log_error(f"Lỗi khi sync lệnh: {e}")

# ==========================================================
# 👤 /profile — xem thông tin người chơi
# ==========================================================
@tree.command(name="profile", description="Xem hồ sơ người chơi", guild=discord.Object(id=GUILD_ID))
async def profile(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    await interaction.response.defer(thinking=True)

    await ensure_user_exists(user.id)
    try:
        rows = query("users", filters=f"&email=eq.{user.id}", limit=1)
        u = rows[0]

        embed = discord.Embed(
            title=f"Hồ sơ của {user.display_name}",
            color=discord.Color.gold(),
            description=f"💰 Số dư: **{u.get('balance', 0):,} Mcoin**"
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải dữ liệu: `{e}`")

# ==========================================================
# 💸 /chuyentien — chuyển tiền giữa người chơi
# ==========================================================
@tree.command(name="chuyentien", description="Chuyển Mcoin cho người chơi khác", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(nguoi_nhan="Người nhận tiền", so_tien="Số Mcoin cần chuyển")
async def chuyentien(interaction: discord.Interaction, nguoi_nhan: discord.User, so_tien: int):
    nguoi_gui = interaction.user
    await interaction.response.defer(thinking=True)

    if so_tien <= 0:
        await interaction.followup.send("❌ Số tiền phải lớn hơn 0.")
        return

    await ensure_user_exists(nguoi_gui.id)
    await ensure_user_exists(nguoi_nhan.id)

    try:
        gui = query("users", filters=f"&email=eq.{nguoi_gui.id}", limit=1)[0]
        nhan = query("users", filters=f"&email=eq.{nguoi_nhan.id}", limit=1)[0]

        if gui["balance"] < so_tien:
            await interaction.followup.send("❌ Bạn không đủ Mcoin để chuyển.")
            return

        update("users", f"email=eq.{nguoi_gui.id}", {"balance": gui["balance"] - so_tien})
        update("users", f"email=eq.{nguoi_nhan.id}", {"balance": nhan["balance"] + so_tien})

        await interaction.followup.send(
            f"✅ **{nguoi_gui.display_name}** đã chuyển **{so_tien:,} Mcoin** cho **{nguoi_nhan.display_name}**!"
        )

    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi thực hiện chuyển tiền: `{e}`")

# ==========================================================
# 🎮 /game — gọi module game động
# ==========================================================
@tree.command(name="game", description="Chơi game tại casino 🎲", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(tro_choi="Tên game (vd: taixiu, bau_cua, slots, horse_race)")
async def game(interaction: discord.Interaction, tro_choi: str):
    await interaction.response.defer(thinking=True)

    await ensure_user_exists(interaction.user.id)
    try:
        module_name = f"games.{tro_choi}"
        file_path = f"./games/{tro_choi}.py"
        if not os.path.exists(file_path):
            await interaction.followup.send(f"❌ Game `{tro_choi}` không tồn tại.")
            return

        import importlib
        game_module = importlib.import_module(module_name)
        if hasattr(game_module, "start_game"):
            await game_module.start_game(interaction)
        else:
            await interaction.followup.send(f"⚠️ Game `{tro_choi}` chưa có hàm `start_game()`.")
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải game: `{e}`")

# ==========================================================
# 🌐 Flask keep-alive server (Render Free)
# ==========================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ==========================================================
# 🚀 Chạy bot Discord song song với Flask
# ==========================================================
if __name__ == "__main__":
    log_info("Đang khởi chạy bot Discord...")
    threading.Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
