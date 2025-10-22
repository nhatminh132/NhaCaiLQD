# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
from discord import ui, app_commands # Thay đổi import
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone, date, time
from supabase import create_client, Client
import typing
import random
import asyncio
import math
import discord.utils
import pytz

# Import tệp keep_alive
from keep_alive import keep_alive

# --- Tải Token và Cài đặt Bot ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# --- Cài đặt Supabase ---
if not SUPABASE_URL or not SUPABASE_KEY: print("LỖI: Không tìm thấy SUPABASE_URL hoặc SUPABASE_KEY"); exit()
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Cài đặt Bot Discord (SỬ DỤNG discord.Bot) ---
intents = discord.Intents.default()
intents.message_content = True # Vẫn cần cho một số logic nền
intents.members = True
# Sử dụng discord.Bot thay vì commands.Bot
bot = discord.Bot(intents=intents)

# --- BIẾN TOÀN CỤC CHO GAME ---
game_message = None # Tin nhắn game Tài Xỉu
game_channel_id = None # Kênh game Tài Xỉu
current_bets = {} # Cược ván Tài Xỉu hiện tại
bot.blackjack_games = {} # Lưu các ván Blackjack
bot.mines_games = {} # Lưu các ván Dò Mìn
bot.users_in_animation = set() # Dùng để khóa lệnh khi game có hiệu ứng
bot.guess_the_number_game = None # Lưu state game Đoán Số
bot.spin_the_wheel_games = {} # (MỚI) Lưu các ván Vòng Quay May Mắn

# --- ĐỊNH NGHĨA HẰNG SỐ ---
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24
ADMIN_ROLE = "Bot Admin"
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LOTTERY_DRAW_TIME = time(18, 0, 0, tzinfo=VIETNAM_TZ)
LOTTERY_TICKET_PRICE = 100
# (Các hằng số game khác giữ nguyên)
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
ROULETTE_PAYOUTS = {'single': 35, 'split': 17, 'street': 11, 'corner': 8, 'sixline': 5, 'dozen': 2, 'column': 2, 'color': 1, 'evenodd': 1, 'half': 1}
BAU_CUA_FACES = {'bầu': 'Bầu 🍐', 'bau': 'Bầu 🍐', '🍐': 'Bầu 🍐', 'cua': 'Cua 🦀', '🦀': 'Cua 🦀', 'tôm': 'Tôm 🦐', 'tom': 'Tôm 🦐', '🦐': 'Tôm 🦐', 'cá': 'Cá 🐟', 'ca': 'Cá 🐟', '🐟': 'Cá 🐟', 'gà': 'Gà 🐓', 'ga': 'Gà 🐓', '🐓': 'Gà 🐓', 'nai': 'Nai 🦌', '🦌': 'Nai 🦌'}
BAU_CUA_LIST = ['Bầu 🍐', 'Cua 🦀', 'Tôm 🦐', 'Cá 🐟', 'Gà 🐓', 'Nai 🦌']
NUM_HORSES = 6; RACE_LENGTH = 20
SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL, SLOT_WEIGHTS, SLOT_PAYOUTS = [], [], {}
for (symbol, weight, payout) in SLOT_SYMBOLS: SLOT_WHEEL.append(symbol); SLOT_WEIGHTS.append(weight); SLOT_PAYOUTS[symbol] = payout
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
CARD_RANKS_BACCARAT = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 0, 'J': 0, 'Q': 0, 'K': 0, 'A': 1}
CARD_RANKS_BJ = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}
CARD_RANKS_HILO = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
# (MỚI) Vòng Quay May Mắn (Tên ô, Trọng số, Hệ số Payout/Giá trị đặc biệt)
WHEEL_SEGMENTS = [
    ('0.5x', 15, 0.5), ('1x', 20, 1.0), ('1.5x', 10, 1.5),
    ('2x', 8, 2.0), ('3x', 5, 3.0), ('5x', 3, 5.0),
    ('10x', 1, 10.0), # Jackpot nhỏ
    ('💣 Mất', 10, 0.0), # Ô mất tiền
    # ('🎁 +100🪙', 5, 100), # Thưởng cố định (có thể thêm)
    # ('✨ X2 Lần sau', 2, 'x2_next') # Phần thưởng đặc biệt (phức tạp)
]
WHEEL_OPTIONS, WHEEL_WEIGHTS = [], []
for (label, weight, value) in WHEEL_SEGMENTS: WHEEL_OPTIONS.append((label, value)); WHEEL_WEIGHTS.append(weight)

# --- CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
# Sử dụng decorator check thay vì before_invoke cho slash commands
def global_rate_limit():
    async def predicate(interaction: discord.Interaction):
        if interaction.data.get('name') == 'help': # Bỏ qua check cho lệnh help (nếu có)
             return True
        bucket = global_cooldown.get_bucket(interaction) # Dùng interaction làm key
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise app_commands.CommandOnCooldown(bucket, retry_after)
        return True
    return app_commands.check(predicate)

global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)


# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
# (Các hàm get_user_data, update_balance, update_profile_stats, get_jackpot_pool, update_jackpot_pool, get_taixiu_history giữ nguyên)
# ... (Dán code các hàm này từ phiên bản trước) ...


# --- HÀM KIỂM TRA & SỰ KIỆN BOT ---
@bot.event
async def on_ready():
    bot.add_view(TaiXiuGameView()) # Đăng ký view Tài Xỉu
    # Không cần add_view cho các game UI theo lượt vì chúng được tạo mới mỗi lần chơi
    lottery_draw_task.start()
    print(f'Bot {bot.user.name} đã sẵn sàng!')
    # (MỚI) Đồng bộ hóa Slash Commands với Discord
    try:
        synced = await bot.tree.sync()
        print(f"Đã đồng bộ hóa {len(synced)} lệnh ứng dụng.")
    except Exception as e:
        print(f"Lỗi khi đồng bộ hóa lệnh: {e}")
    print('------')

# (MỚI) Xử lý lỗi cho Slash Commands
@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    command_name = interaction.command.name if interaction.command else "Unknown"
    if isinstance(error, app_commands.CommandOnCooldown):
        seconds = error.retry_after; await interaction.response.send_message(f"⏳ Bot đang xử lý quá nhiều yêu cầu! Vui lòng thử lại sau **{seconds:.1f} giây**.", ephemeral=True, delete_after=5)
    elif isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message(f"Rất tiếc {interaction.user.mention}, bạn không có quyền dùng lệnh này. Cần role `{ADMIN_ROLE}`.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure): # Lỗi check chung (bao gồm is_user_in_game)
         await interaction.response.send_message(f"⏳ {interaction.user.mention}, bạn đang có một trò chơi khác đang chạy hoặc không thể thực hiện lệnh này ngay bây giờ.", ephemeral=True, delete_after=5)
    elif isinstance(error, app_commands.CommandInvokeError): # Lỗi xảy ra bên trong lệnh
        original = error.original
        print(f"Lỗi không xác định từ lệnh '{command_name}': {original}")
        # Cố gắng gửi phản hồi, có thể đã bị defer hoặc responded
        try:
             if not interaction.response.is_done():
                 await interaction.response.send_message('Đã xảy ra lỗi bên trong lệnh. Vui lòng thử lại sau.', ephemeral=True)
             else:
                 await interaction.followup.send('Đã xảy ra lỗi bên trong lệnh. Vui lòng thử lại sau.', ephemeral=True)
        except discord.InteractionResponded:
             await interaction.followup.send('Đã xảy ra lỗi bên trong lệnh. Vui lòng thử lại sau.', ephemeral=True)
        except Exception as e:
             print(f"Lỗi khi gửi thông báo lỗi invoke: {e}")
    else:
        print(f"Lỗi không xác định từ lệnh '{command_name}': {error}")
        try:
             if not interaction.response.is_done():
                 await interaction.response.send_message('Đã xảy ra lỗi không xác định.', ephemeral=True)
             else:
                 await interaction.followup.send('Đã xảy ra lỗi không xác định.', ephemeral=True)
        except discord.InteractionResponded:
              await interaction.followup.send('Đã xảy ra lỗi không xác định.', ephemeral=True)
        except Exception as e:
             print(f"Lỗi khi gửi thông báo lỗi chung: {e}")


# --- HÀM KIỂM TRA GAME ĐANG CHẠY (CHO SLASH COMMANDS) ---
def is_user_not_in_game():
    async def predicate(interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in bot.blackjack_games: return False
        if user_id in bot.mines_games: return False
        if bot.guess_the_number_game and user_id in bot.guess_the_number_game.participants: return False
        if user_id in bot.users_in_animation: return False
        if user_id in bot.spin_the_wheel_games: return False # Check game Vòng Quay
        return True
    return app_commands.check(predicate)


# --- LỆNH SLASH COMMANDS ---

# --- LỆNH CƠ BẢN VÀ XÃ HỘI ---
@bot.slash_command(name="kiemtra", description="Kiểm tra số dư token 🪙 hiện tại của bạn.")
@global_rate_limit() # Áp dụng rate limit
async def balance_check_slash(interaction: discord.Interaction):
    user_data = get_user_data(interaction.user.id)
    await interaction.response.send_message(f'🪙 {interaction.user.mention}, bạn đang có **{user_data.get("balance", 0):,}** token.' if user_data else 'Đã xảy ra lỗi khi lấy số dư của bạn.', ephemeral=True) # ephemeral=True: Chỉ người dùng thấy

@bot.slash_command(name="daily", description="Nhận thưởng token miễn phí hàng ngày và duy trì chuỗi đăng nhập.")
@global_rate_limit()
@is_user_not_in_game() # Không cho nhận daily khi đang chơi game
async def daily_reward_slash(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return

    can_claim = True
    time_left_str = ""
    current_streak = user_data.get('daily_streak', 0)
    last_streak_date_str = user_data.get('last_streak_date')
    today = datetime.now(VIETNAM_TZ).date()
    yesterday = today - timedelta(days=1)

    if user_data.get('last_daily'):
        try: last_daily_time = datetime.fromisoformat(user_data['last_daily']); cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        except: last_daily_time = None
        if last_daily_time and datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc); hours_left = int(time_left.total_seconds() // 3600); minutes_left = int((time_left.total_seconds() % 3600) // 60)
            time_left_str = f'Bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.'
            can_claim = False

    if not can_claim:
        await interaction.response.send_message(f'{interaction.user.mention}, {time_left_str}', ephemeral=True)
        return

    # Tính streak
    new_streak = 0
    streak_bonus = 0
    if last_streak_date_str:
        try: last_streak_date = date.fromisoformat(last_streak_date_str)
        except: last_streak_date = None

        if last_streak_date == today: # Đã nhận hôm nay rồi (trường hợp hiếm gặp nếu cooldown < 24h)
             new_streak = current_streak
        elif last_streak_date == yesterday: # Nối tiếp streak
             new_streak = current_streak + 1
        else: # Mất streak
             new_streak = 1
    else: # Lần đầu nhận streak
        new_streak = 1

    # Tính bonus (ví dụ: +10 token mỗi ngày streak, tối đa +100)
    streak_bonus = min(new_streak * 10, 100)
    total_reward = DAILY_REWARD + streak_bonus

    new_balance = update_balance(user_id, total_reward)
    if new_balance is None: await interaction.response.send_message("Lỗi cập nhật số dư!", ephemeral=True); return

    try:
        supabase.table('profiles').update({
            'last_daily': datetime.now(timezone.utc).isoformat(),
            'daily_streak': new_streak,
            'last_streak_date': str(today) # Lưu ngày streak dưới dạng string
        }).eq('user_id', user_id).execute()

        streak_msg = f"🔥 Chuỗi đăng nhập: **{new_streak} ngày** (+{streak_bonus}🪙 bonus)!" if new_streak > 1 else "🔥 Bắt đầu chuỗi đăng nhập!"
        await interaction.response.send_message(f'🎉 {interaction.user.mention}, bạn đã nhận được **{total_reward}** token ({DAILY_REWARD} + {streak_bonus} bonus)! {streak_msg}\nSố dư mới: **{new_balance:,}** 🪙.', ephemeral=True)
    except Exception as e: await interaction.response.send_message(f'Đã xảy ra lỗi khi cập nhật thời gian/streak: {e}', ephemeral=True)


@bot.slash_command(name="code", description="Nhập giftcode để nhận thưởng.")
@app_commands.describe(code_to_redeem="Mã code bạn muốn nhập")
@global_rate_limit()
@is_user_not_in_game()
async def redeem_code_slash(interaction: discord.Interaction, code_to_redeem: str):
    user_id = interaction.user.id; user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    code_to_redeem = code_to_redeem.upper()
    try: code_response = supabase.table('gift_codes').select('*').eq('code', code_to_redeem).execute()
    except Exception as e: await interaction.response.send_message(f'Lỗi khi kiểm tra code: {e}', ephemeral=True); return
    if not code_response.data: await interaction.response.send_message(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.', ephemeral=True); return
    if code_to_redeem in user_data.get('used_codes', []): await interaction.response.send_message(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.', ephemeral=True); return
    reward = code_response.data[0]['reward']; new_balance = update_balance(user_id, reward)
    if new_balance is None: await interaction.response.send_message("Lỗi cập nhật số dư!", ephemeral=True); return
    try: new_code_list = user_data.get('used_codes', []) + [code_to_redeem]; supabase.table('profiles').update({'used_codes': new_code_list}).eq('user_id', user_id).execute(); await interaction.response.send_message(f'🎁 {interaction.user.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward:,}** token! Số dư mới: **{new_balance:,}** 🪙.', ephemeral=True)
    except Exception as e: await interaction.response.send_message(f'Đã xảy ra lỗi khi cập nhật code đã dùng: {e}', ephemeral=True)


@bot.slash_command(name="top", description="Xem bảng xếp hạng những người giàu nhất.")
@app_commands.describe(top_n="Số lượng người muốn xem (mặc định 10)")
@global_rate_limit()
async def leaderboard_slash(interaction: discord.Interaction, top_n: int = 10):
    if top_n <= 0: top_n = 10
    if top_n > 25: top_n = 25 # Giới hạn Discord Embed Fields
    try:
        response = supabase.table('profiles').select('user_id', 'balance').order('balance', desc=True).limit(top_n).execute()
        if not response.data: await interaction.response.send_message('Chưa có ai trong bảng xếp hạng.'); return
        embed = discord.Embed(title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆", color=discord.Color.gold()); rank_count = 1
        user_mentions = []
        for user_data in response.data:
             try: user = await bot.fetch_user(user_data['user_id'])
             except discord.NotFound: user = None
             user_name = user.mention if user else f"User ID {user_data['user_id']}" # Mention thay vì display_name
             embed.add_field(name=f"#{rank_count}: {user_name}", value=f"**{user_data.get('balance', 0):,}** 🪙", inline=False); rank_count += 1
        await interaction.response.send_message(embed=embed)
    except Exception as e: await interaction.response.send_message(f'Lỗi khi lấy bảng xếp hạng: {e}', ephemeral=True)

@bot.slash_command(name="chuyenxu", description="Chuyển token cho người dùng khác.")
@app_commands.describe(recipient="Người bạn muốn chuyển token đến", amount="Số lượng token muốn chuyển")
@global_rate_limit()
@is_user_not_in_game()
async def transfer_tokens_slash(interaction: discord.Interaction, recipient: discord.Member, amount: int):
    sender_id = interaction.user.id; recipient_id = recipient.id
    if sender_id == recipient_id: await interaction.response.send_message('Bạn không thể tự chuyển cho chính mình!', ephemeral=True); return
    if amount <= 0: await interaction.response.send_message('Số tiền chuyển phải lớn hơn 0!', ephemeral=True); return
    sender_data = get_user_data(sender_id)
    if not sender_data: await interaction.response.send_message("Lỗi lấy dữ liệu người gửi.", ephemeral=True); return
    if sender_data.get('balance', 0) < amount: await interaction.response.send_message(f'Bạn không đủ tiền. Bạn chỉ có **{sender_data.get("balance", 0):,}** 🪙.', ephemeral=True); return
    try: update_balance(sender_id, -amount); new_recipient_balance = update_balance(recipient_id, amount); await interaction.response.send_message(f'✅ {interaction.user.mention} đã chuyển **{amount:,}** 🪙 cho {recipient.mention}!')
    except Exception as e: await interaction.response.send_message(f'Đã xảy ra lỗi trong quá trình chuyển: {e}', ephemeral=True)

@bot.slash_command(name="profile", description="Xem hồ sơ của bạn hoặc người khác.")
@app_commands.describe(member="Người dùng bạn muốn xem hồ sơ (để trống nếu là bạn)")
@global_rate_limit()
async def profile_slash(interaction: discord.Interaction, member: typing.Optional[discord.Member]):
    target_user = member or interaction.user; user_data = get_user_data(target_user.id)
    if not user_data: await interaction.response.send_message(f"Không tìm thấy dữ liệu cho {target_user.mention}.", ephemeral=True); return
    balance = user_data.get('balance', 0); total_bet = user_data.get('total_bet', 0); total_won = user_data.get('total_won', 0); games_played = user_data.get('games_played', 0)
    net_profit = total_won - total_bet # Lưu ý: total_won chỉ tính tiền lời
    streak = user_data.get('daily_streak', 0)
    embed = discord.Embed(title=f"📊 Hồ sơ của {target_user.display_name}", color=target_user.color); embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="💰 Số dư", value=f"**{balance:,}** 🪙", inline=True); embed.add_field(name="🔥 Chuỗi Daily", value=f"{streak} ngày", inline=True); embed.add_field(name="🎲 Số game đã chơi", value=f"{games_played:,}", inline=True)
    embed.add_field(name="📈 Tổng cược", value=f"{total_bet:,} 🪙", inline=False); embed.add_field(name="🏆 Tổng lời", value=f"{total_won:,} 🪙", inline=False) # Đổi thành Tổng lời
    embed.add_field(name="💹 Lãi/Lỗ ròng", value=f"**{net_profit:,}** 🪙", inline=False)
    await interaction.response.send_message(embed=embed)


# --- LỆNH ADMIN (SLASH COMMANDS) ---
# Sử dụng app_commands.checks.has_role
admin_group = app_commands.Group(name="admin", description="Các lệnh quản lý bot")

@admin_group.command(name="give", description="Cộng/Trừ token cho người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_give_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount == 0: await interaction.response.send_message("Số lượng phải khác 0.", ephemeral=True); return
    user_id = member.id; new_balance = update_balance(user_id, amount)
    if new_balance is None: await interaction.response.send_message("Lỗi cập nhật số dư!", ephemeral=True); return
    action = "cộng" if amount > 0 else "trừ"
    abs_amount = abs(amount)
    await interaction.response.send_message(f"✅ Đã {action} **{abs_amount:,}** 🪙 cho {member.mention}. Số dư mới: **{new_balance:,}** 🪙.")

@admin_group.command(name="set", description="Đặt số dư của người dùng về một con số cụ thể.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_set_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    if amount < 0: await interaction.response.send_message("Không thể set số dư âm.", ephemeral=True); return
    try: supabase.rpc('set_balance', {'user_id_input': member.id, 'amount_input': amount}).execute(); await interaction.response.send_message(f"✅ Đã set số dư của {member.mention} thành **{amount:,}** 🪙.")
    except Exception as e: await interaction.response.send_message(f"Đã xảy ra lỗi khi set balance: {e}", ephemeral=True)

@admin_group.command(name="createcode", description="Tạo một giftcode mới.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_createcode_slash(interaction: discord.Interaction, code: str, reward: int):
    if reward <= 0: await interaction.response.send_message("Phần thưởng phải lớn hơn 0.", ephemeral=True); return
    code = code.upper()
    try: supabase.table('gift_codes').insert({'code': code, 'reward': reward}).execute(); await interaction.response.send_message(f"✅ Đã tạo giftcode `{code}` trị giá **{reward:,}** 🪙.")
    except Exception as e: await interaction.response.send_message(f"Lỗi! Code `{code}` có thể đã tồn tại. ({e})", ephemeral=True)

@admin_group.command(name="deletecode", description="Xóa một giftcode.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_deletecode_slash(interaction: discord.Interaction, code: str):
    code = code.upper()
    try: response = supabase.table('gift_codes').delete().eq('code', code).execute()
    except Exception as e: await interaction.response.send_message(f"Đã xảy ra lỗi khi xóa code: {e}", ephemeral=True); return
    if response.data: await interaction.response.send_message(f"✅ Đã xóa thành công giftcode `{code}`.")
    else: await interaction.response.send_message(f"Lỗi! Không tìm thấy giftcode nào tên là `{code}`.", ephemeral=True)

@admin_group.command(name="view", description="Xem chi tiết thông tin của người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_view_slash(interaction: discord.Interaction, member: discord.Member):
    user_data = get_user_data(member.id)
    if not user_data: await interaction.response.send_message("Không tìm thấy user.", ephemeral=True); return
    embed = discord.Embed(title=f"👀 Xem thông tin: {member.display_name}", color=member.color)
    for key, value in user_data.items():
        if key == 'used_codes' and isinstance(value, list): embed.add_field(name=key, value=f"`{'`, `'.join(value)}`" if value else "Chưa dùng code nào", inline=False)
        elif key == 'last_daily' and value:
             try: dt_object = datetime.fromisoformat(value).astimezone(VIETNAM_TZ); embed.add_field(name=key, value=f"{dt_object.strftime('%Y-%m-%d %H:%M:%S %Z')}", inline=False)
             except: embed.add_field(name=key, value=f"`{value}` (Lỗi format)", inline=False)
        elif key == 'last_streak_date' and value:
             try: dt_object = date.fromisoformat(value); embed.add_field(name=key, value=f"{dt_object.strftime('%Y-%m-%d')}", inline=False)
             except: embed.add_field(name=key, value=f"`{value}` (Lỗi format)", inline=False)
        elif isinstance(value, (int, float)): embed.add_field(name=key, value=f"`{value:,}`", inline=False)
        else: embed.add_field(name=key, value=f"`{value}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True) # Admin xem riêng tư

@admin_group.command(name="resetdaily", description="Reset thời gian !daily cho người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_resetdaily_slash(interaction: discord.Interaction, member: discord.Member):
    try: supabase.table('profiles').update({'last_daily': None, 'last_streak_date': None, 'daily_streak': 0}).eq('user_id', member.id).execute(); await interaction.response.send_message(f"✅ Đã reset thời gian `daily` và streak cho {member.mention}.")
    except Exception as e: await interaction.response.send_message(f"Lỗi khi reset daily: {e}", ephemeral=True)

@admin_group.command(name="announce", description="Gửi thông báo tới kênh chỉ định.")
@app_commands.checks.has_role(ADMIN_ROLE)
@app_commands.describe(channel="Kênh muốn gửi thông báo", message="Nội dung thông báo")
@global_rate_limit()
async def admin_announce_slash(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    try: embed = discord.Embed(title="📢 Thông Báo Từ Admin 📢", description=message, color=discord.Color.orange()); embed.set_footer(text=f"Gửi bởi {interaction.user.display_name}"); await channel.send(embed=embed); await interaction.response.send_message("✅ Đã gửi thông báo.", ephemeral=True)
    except Exception as e: await interaction.response.send_message(f"Lỗi khi gửi thông báo: {e}", ephemeral=True)

# Thêm nhóm lệnh admin vào cây lệnh
bot.tree.add_command(admin_group)


# --- GAME 24/7: TÀI XỈU (UI) ---
# (Class BetModal, TaiXiuGameView, get_bet_totals, tai_xiu_game_loop giữ nguyên)
# ... (Dán code các phần này từ phiên bản trước) ...

# (MỚI) Lệnh /start_taixiu và /stop_taixiu (KHÔNG CẦN ADMIN ROLE CHO START)
@bot.slash_command(name="start_taixiu", description="Bắt đầu vòng lặp game Tài Xỉu 24/7 tại kênh này.")
@global_rate_limit()
# @app_commands.checks.has_role(ADMIN_ROLE) # Bỏ check role admin
async def start_taixiu_slash(interaction: discord.Interaction):
    global game_channel_id
    # Kiểm tra xem có game đang chạy ở kênh khác không
    if game_channel_id and game_channel_id != interaction.channel_id and tai_xiu_game_loop.is_running():
        await interaction.response.send_message(f"Game Tài Xỉu đã chạy ở kênh <#{game_channel_id}> rồi!", ephemeral=True)
        return
        
    game_channel_id = interaction.channel_id
    if not tai_xiu_game_loop.is_running():
        tai_xiu_game_loop.start()
        await interaction.response.send_message(f"✅ Đã bắt đầu Game Tài Xỉu 24/7 tại kênh <#{game_channel_id}>.")
    else:
        await interaction.response.send_message(f"Game đã chạy tại kênh <#{game_channel_id}> rồi.", ephemeral=True)

@bot.slash_command(name="stop_taixiu", description="(ADMIN) Dừng vòng lặp game Tài Xỉu.")
@app_commands.checks.has_role(ADMIN_ROLE) # Vẫn cần admin để dừng
@global_rate_limit()
async def stop_taixiu_slash(interaction: discord.Interaction):
    global game_channel_id
    if tai_xiu_game_loop.is_running():
        tai_xiu_game_loop.stop()
        # Không reset game_channel_id ngay lập tức để tránh lỗi
        # game_channel_id = None
        await interaction.response.send_message("✅ Đã dừng Game Tài Xỉu.")
        # Reset biến sau khi xác nhận dừng
        await asyncio.sleep(1)
        game_channel_id = None
    else:
        await interaction.response.send_message("Game chưa chạy.", ephemeral=True)


# --- GAME THEO LỆNH (SLASH COMMANDS, CÓ HIỆU ỨNG VÀ KHÓA) ---

@bot.slash_command(name="slots", description="Chơi máy xèng.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược")
@global_rate_limit()
@is_user_not_in_game()
async def slots_slash(interaction: discord.Interaction, bet_amount: int):
    user_id, balance = interaction.user.id, get_user_data(interaction.user.id)['balance']
    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance is None or bet_amount > balance: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer() # Báo cho Discord biết lệnh sẽ mất thời gian
    try:
        final_results = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
        embed = discord.Embed(title="🎰 Máy Xèng 🎰", description="| - | - | - |", color=discord.Color.blue())
        embed.set_footer(text=f"{interaction.user.display_name} đã cược {bet_amount:,} 🪙")
        # Sử dụng followup.send vì đã defer()
        slot_message = await interaction.followup.send(embed=embed, wait=True)

        await asyncio.sleep(1.66); embed.description = f"| {final_results[0]} | - | - |"
        try: await slot_message.edit(embed=embed)
        except discord.NotFound: raise asyncio.CancelledError("Message deleted")
        await asyncio.sleep(1.66); embed.description = f"| {final_results[0]} | {final_results[1]} | - |"
        try: await slot_message.edit(embed=embed)
        except discord.NotFound: raise asyncio.CancelledError("Message deleted")
        await asyncio.sleep(1.66); embed.description = f"| {final_results[0]} | {final_results[1]} | {final_results[2]} |"
        try: await slot_message.edit(embed=embed)
        except discord.NotFound: raise asyncio.CancelledError("Message deleted")

        winnings = 0; jackpot_win = 0; is_jackpot = (final_results[0] == final_results[1] == final_results[2] == '7️⃣')
        if is_jackpot:
            jackpot_pool = get_jackpot_pool('slots'); winnings = jackpot_pool; jackpot_win = winnings
            embed.description += f"\n\n**💥💥💥 JACKPOT TIẾN TRIỂN!!! 💥💥💥**"; update_jackpot_pool('slots', -jackpot_pool); update_jackpot_pool('slots', 1000)
        elif final_results[0] == final_results[1] == final_results[2]:
            payout = SLOT_PAYOUTS[final_results[0]]; winnings = bet_amount * payout
            embed.description += f"\n\n**JACKPOT!** Bạn trúng 3x {final_results[0]} (1 ăn {payout})!"
        elif final_results[0] == final_results[1] or final_results[1] == final_results[2]:
            matching_symbol = final_results[1]; winnings = bet_amount * 1
            embed.description += f"\n\nBạn trúng 2x {matching_symbol} (1 ăn 1)!"

        jackpot_contrib = int(bet_amount * 0.01) if not is_jackpot else 0
        if jackpot_contrib > 0: update_jackpot_pool('slots', jackpot_contrib)
        net_gain = winnings if is_jackpot else (winnings - jackpot_contrib if winnings > 0 else -(bet_amount - jackpot_contrib))
        new_balance = update_balance(user_id, net_gain)
        update_profile_stats(user_id, bet_amount, net_gain)

        if winnings > 0: embed.description += f"\n🎉 Bạn thắng **{winnings:,}** 🪙!\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description += f"\n\n😢 Chúc may mắn lần sau.\nBạn mất **{bet_amount:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        current_jackpot = get_jackpot_pool('slots'); embed.add_field(name="💰 Jackpot Slots Hiện Tại", value=f"**{current_jackpot:,}** 🪙", inline=False)

        try: await slot_message.edit(embed=embed)
        except discord.NotFound: await interaction.followup.send(embed=embed) # Gửi lại nếu bị xóa

    except asyncio.CancelledError: pass
    except Exception as e: print(f"Lỗi /slots: {e}"); await interaction.followup.send("Đã xảy ra lỗi khi chơi Slots.", ephemeral=True)
    finally: bot.users_in_animation.discard(user_id)


# ... (Chuyển đổi tương tự cho /hilo, /tungxu, /xucxac, /baucua, /duangua, /quay, /baccarat) ...
# ... (Nhớ dùng interaction.response.defer(), interaction.followup.send(), interaction.followup.edit_message()) ...
# ... (Thêm update_profile_stats và try...finally...discard(user_id) cho tất cả) ...

# --- XỔ SỐ (LOTTERY) - SLASH COMMANDS ---
lottery_group = app_commands.Group(name="lottery", description="Lệnh liên quan đến xổ số")

@lottery_group.command(name="buy", description="Mua vé số (6 số từ 1 đến 45).")
@app_commands.describe(n1="Số 1", n2="Số 2", n3="Số 3", n4="Số 4", n5="Số 5", n6="Số 6")
@global_rate_limit()
@is_user_not_in_game()
async def lottery_buy_slash(interaction: discord.Interaction, n1: int, n2: int, n3: int, n4: int, n5: int, n6: int):
     # ... (Code mua vé như cũ, dùng interaction.response.send_message) ...
     pass

@lottery_group.command(name="result", description="Xem kết quả xổ số gần nhất.")
@global_rate_limit()
async def lottery_result_slash(interaction: discord.Interaction):
     # ... (Code xem kết quả như cũ, dùng interaction.response.send_message) ...
     pass

bot.tree.add_command(lottery_group)

# --- ĐOÁN SỐ (GUESS THE NUMBER) - SLASH COMMANDS ---
guess_group = app_commands.Group(name="guess", description="Lệnh chơi game đoán số")

@guess_group.command(name="start", description="Bắt đầu game Đoán Số (1-100).")
@app_commands.describe(bet_amount="Số tiền cược để tham gia")
@global_rate_limit()
@is_user_not_in_game()
async def guess_the_number_start_slash(interaction: discord.Interaction, bet_amount: int):
     # ... (Code bắt đầu game như cũ, dùng interaction.response.send_message) ...
     pass

@guess_group.command(name="number", description="Đoán số trong game Đoán Số đang chạy.")
@app_commands.describe(number="Số bạn đoán (1-100)")
@global_rate_limit()
async def guess_number_slash(interaction: discord.Interaction, number: int):
     # ... (Code đoán số như cũ, dùng interaction.response.send_message, message.delete) ...
     pass

bot.tree.add_command(guess_group)


# --- GAME GIAO DIỆN UI (BLACKJACK & MINES) - SLASH COMMANDS ---
@bot.slash_command(name="blackjack", description="Chơi Xì Dách (Blackjack) với bot.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược")
@global_rate_limit()
@is_user_not_in_game()
async def blackjack_slash(interaction: discord.Interaction, bet_amount: int):
     # ... (Code game Blackjack như cũ, dùng interaction.response.send_message) ...
     pass

@bot.slash_command(name="mines", description="Chơi Dò Mìn.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược", bomb_count="Số lượng bom (1-24)")
@global_rate_limit()
@is_user_not_in_game()
async def mines_slash(interaction: discord.Interaction, bet_amount: int, bomb_count: int):
     # ... (Code game Mines như cũ, dùng interaction.response.send_message) ...
     pass


# --- VÒNG QUAY MAY MẮN (SPIN THE WHEEL) - (MỚI) ---

class SpinButton(ui.Button):
    def __init__(self, label, value):
        super().__init__(style=discord.ButtonStyle.secondary, label=label)
        self.value = value # Giá trị hoặc label của ô được chọn

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in bot.spin_the_wheel_games: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        if user_id != self.view.author_id: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return

        game = bot.spin_the_wheel_games[user_id]
        if game['state'] != 'betting': await interaction.response.send_message("Đã hết thời gian chọn ô!", ephemeral=True); return

        game['chosen_bet'] = self.value # Lưu lựa chọn của người chơi
        # Làm nổi bật nút đã chọn (tùy chọn)
        for item in self.view.children: item.disabled = True; item.style = discord.ButtonStyle.grey
        self.style = discord.ButtonStyle.success

        await interaction.response.edit_message(content=f"Bạn đã chọn: **{self.label}**. Đang quay...", view=self.view)
        await self.view.spin_wheel(interaction)


class SpinTheWheelView(ui.View):
    def __init__(self, author_id, game):
        super().__init__(timeout=30.0) # 30 giây để chọn ô
        self.author_id = author_id
        self.game = game

        # Tạo nút cho các ô có thể cược (ví dụ: cược payout)
        bet_options = [(label, value) for label, value in WHEEL_OPTIONS if isinstance(value, float) or isinstance(value, int)]
        # Chia nút thành các hàng nếu cần
        for label, value in bet_options:
             self.add_item(SpinButton(label=label, value=value))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return False
        return True

    async def on_timeout(self):
         if self.author_id in bot.spin_the_wheel_games and self.game['state'] == 'betting':
             game = bot.spin_the_wheel_games.pop(self.author_id)
             await game['message'].edit(content="Hết giờ chọn ô cược. Ván chơi bị hủy. Tiền đã được hoàn lại.", embed=None, view=None)
             # Hoàn tiền (nếu đã trừ tiền trước) - Hiện tại chưa trừ tiền trước
             # update_balance(self.author_id, game['bet'])
             # update_profile_stats(self.author_id, 0, game['bet'])

    async def spin_wheel(self, interaction: discord.Interaction):
        game = self.game
        game['state'] = 'spinning'

        # Hiệu ứng quay
        spin_duration = 5 # giây
        update_interval = 0.5 # giây
        steps = int(spin_duration / update_interval)
        chosen_label = [label for label, val in WHEEL_OPTIONS if val == game['chosen_bet']][0]

        for i in range(steps):
             # Hiển thị ô ngẫu nhiên
             temp_label, _ = random.choice(WHEEL_OPTIONS)
             await game['message'].edit(content=f"Bạn đã chọn: **{chosen_label}**. Đang quay... [{temp_label}]", view=self)
             await asyncio.sleep(update_interval)

        # Kết quả cuối cùng
        result_label, result_value = random.choices(WHEEL_OPTIONS, weights=WHEEL_WEIGHTS, k=1)[0]

        winnings = 0; payout = 0
        is_win = False
        result_extra = ""

        if isinstance(result_value, float): # Trúng ô Payout
             if game['chosen_bet'] == result_value: # Cược trúng ô Payout đó
                 is_win = True
                 winnings = int(game['bet'] * result_value)
                 payout = winnings - game['bet'] # Lời/lỗ ròng
             elif result_value == 0.0: # Trúng ô mất tiền
                 is_win = False
                 payout = -game['bet']
             else: # Cược ô payout khác nhưng quay ra ô payout khác -> thua
                 is_win = False
                 payout = -game['bet']
        elif result_value == 0.0: # Quay trúng ô mất tiền (💣)
            is_win = False
            payout = -game['bet']
        # Xử lý các ô đặc biệt khác nếu có (hiện tại chưa thêm)

        new_balance = update_balance(self.author_id, payout)
        update_profile_stats(self.author_id, game['bet'], payout)

        final_content = f"🎡 Vòng quay dừng tại: **{result_label}** 🎡\n"
        final_content += f"Bạn đã cược **{game['bet']:,}** 🪙 vào **{chosen_label}**.\n"
        if is_win:
             final_content += f"🎉 **Bạn đã thắng!** Bạn nhận được **{winnings:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."
        else:
             final_content += f"😢 **Bạn đã thua!** Bạn mất **{abs(payout):,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."

        await game['message'].edit(content=final_content, view=None)
        bot.spin_the_wheel_games.pop(self.author_id, None)


@bot.slash_command(name="spin", description="Chơi Vòng Quay May Mắn.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược")
@global_rate_limit()
@is_user_not_in_game()
async def spin_the_wheel_slash(interaction: discord.Interaction, bet_amount: int):
    user_id, balance = interaction.user.id, get_user_data(interaction.user.id)['balance']
    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance is None or bet_amount > balance: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    game_state = {
         'user_id': user_id,
         'bet': bet_amount,
         'message': None, # Sẽ cập nhật sau khi gửi
         'state': 'betting', # Trạng thái: betting -> spinning -> finished
         'chosen_bet': None # Ô người chơi chọn
    }
    view = SpinTheWheelView(user_id, game_state)
    await interaction.response.send_message(f"🎡 Vòng Quay May Mắn! Cược: **{bet_amount:,}** 🪙\nHãy chọn một ô để đặt cược trong vòng 30 giây:", view=view)
    message = await interaction.original_response()
    game_state['message'] = message
    bot.spin_the_wheel_games[user_id] = game_state


# --- XỔ SỐ TASK ---
@tasks.loop(time=LOTTERY_DRAW_TIME)
async def lottery_draw_task():
    # ... (code quay số như cũ) ...
    pass

# --- CHẠY BOT ---
if TOKEN:
    keep_alive(); bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN")
