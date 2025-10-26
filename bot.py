import os
import threading
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from dotenv import load_dotenv

from core.supabase_client import init_supabase, query, insert, update, delete
from core.utils import log_info, log_error

# ==========================================================
# 🌐 Tải biến môi trường
# ==========================================================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ==========================================================
# 🔧 Khởi tạo Supabase
# ==========================================================
try:
    init_supabase()
    log_info("✅ Supabase đã sẵn sàng")
except Exception as e:
    log_error(f"Lỗi khi khởi tạo Supabase: {e}")
    raise

# ==========================================================
# ⚙️ Sự kiện khởi động bot
# ==========================================================
@bot.event
async def on_ready():
    log_info(f"Bot đã đăng nhập thành công dưới tên: {bot.user}")

    try:
        guild = discord.Object(id=GUILD_ID)
        await tree.clear_commands(guild=guild)   # Xóa cache lệnh cũ
        synced = await tree.sync(guild=guild)    # Đăng ký lại tất cả slash command
        log_info(f"Đã xóa & đồng bộ {len(synced)} lệnh slash cho server ID {GUILD_ID}")
    except Exception as e:
        log_error(f"Lỗi khi sync lệnh: {e}")

# ==========================================================
# 👤 /profile — Xem hồ sơ người chơi
# ==========================================================
@tree.command(name="profile", description="Xem hồ sơ người chơi", guild=discord.Object(id=GUILD_ID))
async def profile(interaction: discord.Interaction, user: discord.User = None):
    user = user or interaction.user
    await interaction.response.defer(thinking=True)

    try:
        rows = query("users", filters=f"&email=eq.{user.id}", limit=1)
        balance = rows[0].get("balance", 0) if rows else 100000  # Default nếu chưa có
        if not rows:
            insert("users", {"email": str(user.id), "balance": balance})

        embed = discord.Embed(
            title=f"Hồ sơ của {user.display_name}",
            color=discord.Color.gold(),
            description=f"💰 Số dư hiện tại: **{balance:,} Mcoin**"
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi tải dữ liệu: `{e}`")

# ==========================================================
# 💸 /chuyentien — Giao dịch giữa người chơi
# ==========================================================
@tree.command(name="chuyentien", description="Chuyển Mcoin cho người chơi khác", guild=discord.Object(id=GUILD_ID))
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
            gui = [{"balance": 100000}]
        if not nhan:
            insert("users", {"email": str(nguoi_nhan.id), "balance": 100000})
            nhan = [{"balance": 100000}]

        balance_gui = gui[0].get("balance", 0)
        balance_nhan = nhan[0].get("balance", 0)

        if balance_gui < so_tien:
            await interaction.followup.send("❌ Bạn không đủ Mcoin để chuyển.")
            return

        update("users", f"email=eq.{nguoi_gui.id}", {"balance": balance_gui - so_tien})
        update("users", f"email=eq.{nguoi_nhan.id}", {"balance": balance_nhan + so_tien})

        await interaction.followup.send(
            f"✅ **{nguoi_gui.display_name}** đã chuyển **{so_tien:,} Mcoin** cho **{nguoi_nhan.display_name}**!"
        )

    except Exception as e:
        await interaction.followup.send(f"⚠️ Lỗi khi thực hiện chuyển tiền: `{e}`")

# ==========================================================
# 🎮 /game — Gọi module game động (taixiu, slots, ...)
# ==========================================================
@tree.command(name="game", description="Chơi game tại casino 🎲", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(tro_choi="Tên game muốn chơi (vd: taixiu, bau_cua, slots, horse_race)")
async def game(interaction: discord.Interaction, tro_choi: str):
    await interaction.response.defer(thinking=True)

    try:
        module_name = f"games.{tro_choi}"
        if not os.path.exists(f"./games/{tro_choi}.py"):
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
# 🌍 Flask Keep-Alive (Render)
# ==========================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ==========================================================
# 🚀 Main
# ==========================================================
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    log_info("Đang khởi chạy bot Discord...")
    bot.run(TOKEN)
