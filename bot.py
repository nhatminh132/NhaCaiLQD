import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from core.supabase_client import supabase_init
from core.utils import log_info, log_warn
from web.server import keep_alive

# ==============================
# Khởi tạo môi trường
# ==============================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 1121380060897742850))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# ==============================
# Khởi tạo Supabase
# ==============================
supabase = supabase_init()

# ==============================
# Sự kiện khi bot khởi động
# ==============================
@bot.event
async def on_ready():
    log_info(f"Bot đã đăng nhập thành công dưới tên: {bot.user}")
    log_info("Tải module lệnh và game...")
    try:
        await bot.tree.sync()
        log_info("Đồng bộ slash command thành công.")
    except Exception as e:
        log_warn(f"Lỗi khi sync lệnh: {e}")

    # Flask keep-alive cho Render Free
    asyncio.create_task(keep_alive())
    log_info("Flask keep-alive đã khởi động.")
    log_info("✅ Bot đã sẵn sàng để phục vụ các cược thủ!")

# ==============================
# Load các module lệnh & game
# ==============================
async def load_all_modules():
    try:
        await bot.load_extension("commands.profile")
        await bot.load_extension("commands.bank")
        await bot.load_extension("commands.loan")
        await bot.load_extension("commands.admin")
        await bot.load_extension("commands.event")
        await bot.load_extension("games.taixiu")
        await bot.load_extension("games.lottery")
        await bot.load_extension("games.slots")
        await bot.load_extension("games.bau_cua")
        log_info("Đã nạp toàn bộ module.")
    except Exception as e:
        log_warn(f"Lỗi khi nạp module: {e}")

# ==============================
# Chạy bot
# ==============================
async def main():
    async with bot:
        await load_all_modules()
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_warn("Bot đã dừng thủ công.")

# Giữ bot sống
keep_alive()

# Chạy bot
bot.run(DISCORD_TOKEN)
