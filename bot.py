# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
from discord import ui, app_commands # Sử dụng app_commands cho slash
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone, date, time
from supabase import create_client, Client
import typing
import random
import asyncio
import math
import discord.utils
import pytz # Thêm thư viện múi giờ
import re # Thêm thư viện regex cho cược Roulette phức tạp

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

# --- Cài đặt Bot Discord (SỬ DỤNG discord.Bot cho Slash Commands) ---
intents = discord.Intents.default()
# intents.message_content = True # Có thể bật nếu cần đọc tin nhắn thường cho tính năng khác
intents.members = True # Cần để lấy thông tin Member
bot = discord.Bot(intents=intents) # Sử dụng discord.Bot

# --- BIẾN TOÀN CỤC CHO GAME ---
game_message = None # Tin nhắn game Tài Xỉu
game_channel_id = None # Kênh game Tài Xỉu
current_bets = {} # Cược ván Tài Xỉu hiện tại
bot.blackjack_games = {} # Lưu các ván Blackjack
bot.mines_games = {} # Lưu các ván Dò Mìn
bot.users_in_animation = set() # Dùng để khóa lệnh khi game có hiệu ứng
bot.guess_the_number_game = None # Lưu state game Đoán Số
bot.spin_the_wheel_games = {} # Lưu các ván Vòng Quay May Mắn

# --- ĐỊNH NGHĨA HẰNG SỐ ---
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24
ADMIN_ROLE = "Bot Admin" # Vẫn cần cho các lệnh admin khác
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
LOTTERY_DRAW_TIME = time(18, 0, 0, tzinfo=VIETNAM_TZ)
LOTTERY_TICKET_PRICE = 100

# Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
ROULETTE_PAYOUTS = {'single': 35, 'split': 17, 'street': 11, 'corner': 8, 'sixline': 5, 'dozen': 2, 'column': 2, 'color': 1, 'evenodd': 1, 'half': 1}

# Bầu Cua
BAU_CUA_FACES = {'bầu': 'Bầu 🍐', 'bau': 'Bầu 🍐', '🍐': 'Bầu 🍐', 'cua': 'Cua 🦀', '🦀': 'Cua 🦀', 'tôm': 'Tôm 🦐', 'tom': 'Tôm 🦐', '🦐': 'Tôm 🦐', 'cá': 'Cá 🐟', 'ca': 'Cá 🐟', '🐟': 'Cá 🐟', 'gà': 'Gà 🐓', 'ga': 'Gà 🐓', '🐓': 'Gà 🐓', 'nai': 'Nai 🦌', '🦌': 'Nai 🦌'}
BAU_CUA_LIST = ['Bầu 🍐', 'Cua 🦀', 'Tôm 🦐', 'Cá 🐟', 'Gà 🐓', 'Nai 🦌']

# Đua Ngựa
NUM_HORSES = 6; RACE_LENGTH = 20

# Máy Xèng (Slots)
SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL, SLOT_WEIGHTS, SLOT_PAYOUTS = [], [], {}
for (symbol, weight, payout) in SLOT_SYMBOLS: SLOT_WHEEL.append(symbol); SLOT_WEIGHTS.append(weight); SLOT_PAYOUTS[symbol] = payout

# Bài (Cards)
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
# J=10, Q=10, K=10, A=1 (Baccarat), A=11/1 (BJ), A=14 (Hilo)
CARD_RANKS_BACCARAT = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 0, 'J': 0, 'Q': 0, 'K': 0, 'A': 1}
CARD_RANKS_BJ = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}
CARD_RANKS_HILO = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

# Vòng Quay May Mắn
WHEEL_SEGMENTS = [('0.5x', 15, 0.5), ('1x', 20, 1.0), ('1.5x', 10, 1.5), ('2x', 8, 2.0), ('3x', 5, 3.0), ('5x', 3, 5.0), ('10x', 1, 10.0), ('💣 Mất', 10, 0.0)]
WHEEL_OPTIONS, WHEEL_WEIGHTS = [], []
for (label, weight, value) in WHEEL_SEGMENTS: WHEEL_OPTIONS.append((label, value)); WHEEL_WEIGHTS.append(weight)

# --- CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
def global_rate_limit():
    async def predicate(interaction: discord.Interaction):
        # Không cần check help vì không còn lệnh help
        bucket = global_cooldown.get_bucket(interaction)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise app_commands.CommandOnCooldown(bucket, retry_after)
        return True
    return app_commands.check(predicate)

global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)


# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
def get_user_data(user_id: int) -> typing.Dict:
    try:
        response = supabase.table('profiles').select('*').eq('user_id', user_id).single().execute()
        data = response.data
        if not data: raise Exception("User not found initially") # Ném lỗi nếu single() trả về None
        # Đảm bảo các cột tồn tại với giá trị mặc định nếu thiếu
        data.setdefault('balance', STARTING_TOKENS)
        data.setdefault('last_daily', None)
        data.setdefault('used_codes', [])
        data.setdefault('total_bet', 0)
        data.setdefault('total_won', 0)
        data.setdefault('games_played', 0)
        data.setdefault('daily_streak', 0)
        data.setdefault('last_streak_date', None)
        return data
    except Exception as e:
        if "JSON object requested" in str(e) or "User not found initially" in str(e): # User chưa tồn tại, tạo mới
             try:
                 insert_response = supabase.table('profiles').insert({'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': [], 'total_bet': 0, 'total_won': 0, 'games_played': 0, 'daily_streak': 0, 'last_streak_date': None}).execute()
                 return insert_response.data[0]
             except Exception as e2: print(f"Lỗi khi tạo user mới {user_id}: {e2}"); return None
        else: print(f"Lỗi khi get_user_data cho {user_id}: {e}"); return None

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    try:
        # Gọi RPC function đã tạo trong Supabase
        response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
        return response.data # Trả về số dư mới
    except Exception as e:
        print(f"Lỗi khi update_balance cho {user_id}: {e}")
        # Nếu lỗi có thể do user chưa tồn tại, thử tạo/lấy lại
        user_data = get_user_data(user_id)
        if user_data: # Nếu user tồn tại (hoặc vừa được tạo), thử gọi RPC lại
             try:
                 response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
                 return response.data
             except Exception as e2: print(f"Lỗi lần 2 khi update_balance: {e2}")
        return None # Trả về None nếu vẫn lỗi

def update_profile_stats(user_id: int, bet_amount: int, net_gain: int):
    try:
        user_data = get_user_data(user_id) # Lấy data để đảm bảo có giá trị mặc định
        if not user_data: return

        new_total_bet = user_data.get('total_bet', 0) + bet_amount
        new_total_won = user_data.get('total_won', 0) + max(0, net_gain) # Chỉ cộng phần lời
        new_games_played = user_data.get('games_played', 0) + 1

        supabase.table('profiles').update({
            'total_bet': new_total_bet,
            'total_won': new_total_won,
            'games_played': new_games_played
        }).eq('user_id', user_id).execute()
    except Exception as e: print(f"Lỗi khi update_profile_stats cho {user_id}: {e}")

def get_jackpot_pool(game_name: str):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        response = supabase.table(table_name).select('pool_amount').eq('game_name', game_name).maybe_single().execute()
        return response.data['pool_amount'] if response.data else 0
    except Exception as e: print(f"Lỗi khi lấy jackpot {game_name}: {e}"); return 0

def update_jackpot_pool(game_name: str, amount: int):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        # Sử dụng atomic increment/decrement nếu có thể (ví dụ qua RPC)
        # Tạm thời vẫn đọc-ghi
        current_pool = get_jackpot_pool(game_name)
        new_pool = max(0, current_pool + amount) # Đảm bảo hũ không âm
        supabase.table(table_name).update({'pool_amount': new_pool}).eq('game_name', game_name).execute()
        return new_pool
    except Exception as e: print(f"Lỗi khi cập nhật jackpot {game_name}: {e}"); return get_jackpot_pool(game_name)

def get_taixiu_history():
    try:
        response = supabase.table('jackpot').select('history').eq('game_name', 'taixiu').maybe_single().execute()
        return response.data.get('history', [])[-10:] if response.data else []
    except Exception as e: print(f"Loi khi lay history taixiu: {e}"); return []


# --- HÀM KIỂM TRA & SỰ KIỆN BOT ---
@bot.event
async def on_ready():
    # Đăng ký View persistent cho Tài Xỉu để nút hoạt động sau khi bot khởi động lại
    bot.add_view(TaiXiuGameView())
    # Khởi động task xổ số
    if not lottery_draw_task.is_running():
        lottery_draw_task.start()
    print(f'Bot {bot.user.name} ({bot.user.id}) đã sẵn sàng!')
    # Đồng bộ hóa Slash Commands
    try:
        synced = await bot.tree.sync()
        print(f"Đã đồng bộ hóa {len(synced)} lệnh ứng dụng.")
    except Exception as e:
        print(f"Lỗi khi đồng bộ hóa lệnh: {e}")
    print('------')

@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    command_name = interaction.command.name if interaction.command else "Unknown"
    original_error = getattr(error, 'original', error)

    async def safe_response(content: str, ephemeral: bool = True, delete_after: typing.Optional[int] = None):
        try:
            if interaction.response.is_done(): await interaction.followup.send(content, ephemeral=ephemeral, delete_after=delete_after)
            else: await interaction.response.send_message(content, ephemeral=ephemeral, delete_after=delete_after)
        except discord.InteractionResponded:
            try: await interaction.followup.send(content, ephemeral=ephemeral, delete_after=delete_after)
            except Exception as e_inner: print(f"Lỗi gửi followup sau InteractionResponded: {e_inner}")
        except Exception as e_outer: print(f"Lỗi gửi phản hồi lỗi chung: {e_outer}")

    if isinstance(error, app_commands.CommandOnCooldown):
        seconds = error.retry_after; await safe_response(f"⏳ Bot đang xử lý quá nhiều yêu cầu! Vui lòng thử lại sau **{seconds:.1f} giây**.", delete_after=5)
    elif isinstance(error, app_commands.MissingRole):
        await safe_response(f"Rất tiếc {interaction.user.mention}, bạn không có quyền dùng lệnh này. Cần role `{ADMIN_ROLE}`.")
    elif isinstance(error, app_commands.CheckFailure):
         await safe_response(f"⏳ {interaction.user.mention}, bạn đang có một trò chơi khác đang chạy hoặc không thể thực hiện lệnh này ngay bây giờ.", delete_after=5)
    elif isinstance(error, app_commands.CommandInvokeError):
        if isinstance(original_error, ValueError) and "Invalid Roulette bet type" in str(original_error):
             bet_arg = interaction.data.get('options', [{}])[0].get('options', [{}])[-1].get('value', 'không rõ')
             await safe_response(f"Loại cược Roulette không hợp lệ: `{bet_arg}`. Gõ `/` xem ví dụ.")
        else:
            print(f"Lỗi không xác định từ lệnh '{command_name}': {original_error}")
            await safe_response('Đã xảy ra lỗi bên trong lệnh. Vui lòng thử lại sau.')
    elif isinstance(error, app_commands.TransformerError) or isinstance(error, app_commands.ArgumentParsingError):
         await safe_response(f'Tham số bạn nhập cho lệnh `{command_name}` không hợp lệ. Vui lòng kiểm tra lại.')
    else:
        print(f"Lỗi không xác định từ lệnh '{command_name}': {error}")
        await safe_response('Đã xảy ra lỗi không xác định.')

# --- HÀM KIỂM TRA GAME ĐANG CHẠY (CHO SLASH COMMANDS) ---
def is_user_not_in_game():
    async def predicate(interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in bot.blackjack_games: return False
        if user_id in bot.mines_games: return False
        if user_id in bot.spin_the_wheel_games: return False
        # Cho phép đoán khi game đoán số đang chạy
        is_guessing = interaction.command and interaction.command.name == "guess" and interaction.command.parent and interaction.command.parent.name == "guess"
        if bot.guess_the_number_game and user_id in bot.guess_the_number_game.participants and not is_guessing:
             return False
        if user_id in bot.users_in_animation: return False
        return True
    return app_commands.check(predicate)

# --- LỆNH SLASH COMMANDS ---

# --- LỆNH CƠ BẢN VÀ XÃ HỘI ---
@bot.slash_command(name="kiemtra", description="Kiểm tra số dư token 🪙 hiện tại của bạn.")
@global_rate_limit()
async def balance_check_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_data = get_user_data(interaction.user.id)
    await interaction.followup.send(f'🪙 {interaction.user.mention}, bạn đang có **{user_data.get("balance", 0):,}** token.' if user_data else 'Đã xảy ra lỗi khi lấy số dư của bạn.')

@bot.slash_command(name="daily", description="Nhận thưởng token hàng ngày và duy trì chuỗi đăng nhập.")
@global_rate_limit()
@is_user_not_in_game()
async def daily_reward_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.followup.send("Lỗi lấy dữ liệu user."); return

    can_claim = True; time_left_str = ""; current_streak = user_data.get('daily_streak', 0); last_streak_date_str = user_data.get('last_streak_date'); today = datetime.now(VIETNAM_TZ).date(); yesterday = today - timedelta(days=1)
    if user_data.get('last_daily'):
        try: last_daily_time = datetime.fromisoformat(user_data['last_daily']); cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        except: last_daily_time = None
        if last_daily_time and datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc); hours_left = int(time_left.total_seconds() // 3600); minutes_left = int((time_left.total_seconds() % 3600) // 60)
            time_left_str = f'Bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.'
            can_claim = False
    if not can_claim: await interaction.followup.send(f'{interaction.user.mention}, {time_left_str}'); return

    new_streak = 0; streak_bonus = 0
    if last_streak_date_str:
        try: last_streak_date = date.fromisoformat(last_streak_date_str)
        except: last_streak_date = None
        if last_streak_date == today: new_streak = current_streak
        elif last_streak_date == yesterday: new_streak = current_streak + 1
        else: new_streak = 1
    else: new_streak = 1
    streak_bonus = min(new_streak * 10, 100); total_reward = DAILY_REWARD + streak_bonus
    new_balance = update_balance(user_id, total_reward)
    if new_balance is None: await interaction.followup.send("Lỗi cập nhật số dư!"); return
    try:
        supabase.table('profiles').update({'last_daily': datetime.now(timezone.utc).isoformat(), 'daily_streak': new_streak, 'last_streak_date': str(today)}).eq('user_id', user_id).execute()
        streak_msg = f"🔥 Chuỗi đăng nhập: **{new_streak} ngày** (+{streak_bonus}🪙 bonus)!" if new_streak > 1 else "🔥 Bắt đầu chuỗi đăng nhập!"
        await interaction.followup.send(f'🎉 {interaction.user.mention}, bạn đã nhận được **{total_reward}** token ({DAILY_REWARD} + {streak_bonus} bonus)! {streak_msg}\nSố dư mới: **{new_balance:,}** 🪙.')
    except Exception as e: await interaction.followup.send(f'Đã xảy ra lỗi khi cập nhật thời gian/streak: {e}')

@bot.slash_command(name="code", description="Nhập giftcode để nhận thưởng.")
@app_commands.describe(code_to_redeem="Mã code bạn muốn nhập")
@global_rate_limit()
@is_user_not_in_game()
async def redeem_code_slash(interaction: discord.Interaction, code_to_redeem: str):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id; user_data = get_user_data(user_id)
    if not user_data: await interaction.followup.send("Lỗi lấy dữ liệu user."); return
    code_to_redeem = code_to_redeem.upper()
    try: code_response = supabase.table('gift_codes').select('*').eq('code', code_to_redeem).execute()
    except Exception as e: await interaction.followup.send(f'Lỗi khi kiểm tra code: {e}'); return
    if not code_response.data: await interaction.followup.send(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.'); return
    if code_to_redeem in user_data.get('used_codes', []): await interaction.followup.send(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.'); return
    reward = code_response.data[0]['reward']; new_balance = update_balance(user_id, reward)
    if new_balance is None: await interaction.followup.send("Lỗi cập nhật số dư!"); return
    try: new_code_list = user_data.get('used_codes', []) + [code_to_redeem]; supabase.table('profiles').update({'used_codes': new_code_list}).eq('user_id', user_id).execute(); await interaction.followup.send(f'🎁 {interaction.user.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward:,}** token! Số dư mới: **{new_balance:,}** 🪙.')
    except Exception as e: await interaction.followup.send(f'Đã xảy ra lỗi khi cập nhật code đã dùng: {e}')

@bot.slash_command(name="top", description="Xem bảng xếp hạng những người giàu nhất.")
@app_commands.describe(top_n="Số lượng người muốn xem (mặc định 10)")
@global_rate_limit()
async def leaderboard_slash(interaction: discord.Interaction, top_n: int = 10):
    await interaction.response.defer()
    if top_n <= 0: top_n = 10
    if top_n > 25: top_n = 25
    try:
        response = supabase.table('profiles').select('user_id', 'balance').order('balance', desc=True).limit(top_n).execute()
        if not response.data: await interaction.followup.send('Chưa có ai trong bảng xếp hạng.'); return
        embed = discord.Embed(title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆", color=discord.Color.gold()); rank_count = 1
        for user_data in response.data:
             user_mention = f"<@{user_data['user_id']}>" # Tạo mention string
             embed.add_field(name=f"#{rank_count}: {user_mention}", value=f"**{user_data.get('balance', 0):,}** 🪙", inline=False); rank_count += 1
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f'Lỗi khi lấy bảng xếp hạng: {e}', ephemeral=True)

@bot.slash_command(name="chuyenxu", description="Chuyển token cho người dùng khác.")
@app_commands.describe(recipient="Người bạn muốn chuyển token đến", amount="Số lượng token muốn chuyển")
@global_rate_limit()
@is_user_not_in_game()
async def transfer_tokens_slash(interaction: discord.Interaction, recipient: discord.Member, amount: int):
    await interaction.response.defer()
    sender_id = interaction.user.id; recipient_id = recipient.id
    if sender_id == recipient_id: await interaction.followup.send('Bạn không thể tự chuyển cho chính mình!', ephemeral=True); return
    if amount <= 0: await interaction.followup.send('Số tiền chuyển phải lớn hơn 0!', ephemeral=True); return
    sender_data = get_user_data(sender_id)
    if not sender_data: await interaction.followup.send("Lỗi lấy dữ liệu người gửi.", ephemeral=True); return
    if sender_data.get('balance', 0) < amount: await interaction.followup.send(f'Bạn không đủ tiền. Bạn chỉ có **{sender_data.get("balance", 0):,}** 🪙.', ephemeral=True); return
    # Thực hiện chuyển tiền (cần đảm bảo cả hai update thành công - transaction lý tưởng nhất)
    sender_new_balance = update_balance(sender_id, -amount)
    if sender_new_balance is None: await interaction.followup.send("Lỗi khi trừ tiền người gửi!", ephemeral=True); return # Báo lỗi nếu trừ tiền thất bại
    recipient_new_balance = update_balance(recipient_id, amount)
    if recipient_new_balance is None:
        # Lỗi cộng tiền người nhận -> Hoàn tiền người gửi
        update_balance(sender_id, amount) # Cố gắng hoàn tiền
        await interaction.followup.send("Lỗi khi cộng tiền người nhận! Giao dịch bị hủy.", ephemeral=True); return
    await interaction.followup.send(f'✅ {interaction.user.mention} đã chuyển **{amount:,}** 🪙 cho {recipient.mention}!')

@bot.slash_command(name="profile", description="Xem hồ sơ của bạn hoặc người khác.")
@app_commands.describe(member="Người dùng bạn muốn xem hồ sơ (để trống nếu là bạn)")
@global_rate_limit()
async def profile_slash(interaction: discord.Interaction, member: typing.Optional[discord.Member]):
    await interaction.response.defer()
    target_user = member or interaction.user; user_data = get_user_data(target_user.id)
    if not user_data: await interaction.followup.send(f"Không tìm thấy dữ liệu cho {target_user.mention}."); return
    balance = user_data.get('balance', 0); total_bet = user_data.get('total_bet', 0); total_won = user_data.get('total_won', 0); games_played = user_data.get('games_played', 0)
    net_profit = total_won - total_bet; streak = user_data.get('daily_streak', 0)
    embed = discord.Embed(title=f"📊 Hồ sơ của {target_user.display_name}", color=target_user.color); embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="💰 Số dư", value=f"**{balance:,}** 🪙", inline=True); embed.add_field(name="🔥 Chuỗi Daily", value=f"{streak} ngày", inline=True); embed.add_field(name="🎲 Số game đã chơi", value=f"{games_played:,}", inline=True)
    embed.add_field(name="📈 Tổng cược", value=f"{total_bet:,} 🪙", inline=False); embed.add_field(name="🏆 Tổng lời", value=f"{total_won:,} 🪙", inline=False)
    embed.add_field(name="💹 Lãi/Lỗ ròng", value=f"**{net_profit:,}** 🪙", inline=False)
    await interaction.followup.send(embed=embed)


# --- LỆNH ADMIN (SLASH COMMANDS) ---
admin_group = app_commands.Group(name="admin", description="Các lệnh quản lý bot", guild_only=True, default_permissions=discord.Permissions(manage_guild=True)) # Chỉ người có quyền Manage Server thấy?

@admin_group.command(name="give", description="Cộng/Trừ token cho người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE) # Vẫn check role cụ thể
@global_rate_limit()
async def admin_give_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    if amount == 0: await interaction.followup.send("Số lượng phải khác 0."); return
    user_id = member.id; new_balance = update_balance(user_id, amount)
    if new_balance is None: await interaction.followup.send("Lỗi cập nhật số dư!"); return
    action = "cộng" if amount > 0 else "trừ"; abs_amount = abs(amount)
    await interaction.followup.send(f"✅ Đã {action} **{abs_amount:,}** 🪙 cho {member.mention}. Số dư mới: **{new_balance:,}** 🪙.")

@admin_group.command(name="set", description="Đặt số dư của người dùng về một con số cụ thể.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_set_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    if amount < 0: await interaction.followup.send("Không thể set số dư âm."); return
    try: supabase.rpc('set_balance', {'user_id_input': member.id, 'amount_input': amount}).execute(); await interaction.followup.send(f"✅ Đã set số dư của {member.mention} thành **{amount:,}** 🪙.")
    except Exception as e: await interaction.followup.send(f"Đã xảy ra lỗi khi set balance: {e}")

@admin_group.command(name="createcode", description="Tạo một giftcode mới.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_createcode_slash(interaction: discord.Interaction, code: str, reward: int):
    await interaction.response.defer(ephemeral=True)
    if reward <= 0: await interaction.followup.send("Phần thưởng phải lớn hơn 0."); return
    code = code.upper()
    try: supabase.table('gift_codes').insert({'code': code, 'reward': reward}).execute(); await interaction.followup.send(f"✅ Đã tạo giftcode `{code}` trị giá **{reward:,}** 🪙.")
    except Exception as e: await interaction.followup.send(f"Lỗi! Code `{code}` có thể đã tồn tại. ({e})")

@admin_group.command(name="deletecode", description="Xóa một giftcode.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_deletecode_slash(interaction: discord.Interaction, code: str):
    await interaction.response.defer(ephemeral=True)
    code = code.upper()
    try: response = supabase.table('gift_codes').delete().eq('code', code).execute()
    except Exception as e: await interaction.followup.send(f"Đã xảy ra lỗi khi xóa code: {e}"); return
    if response.data: await interaction.followup.send(f"✅ Đã xóa thành công giftcode `{code}`.")
    else: await interaction.followup.send(f"Lỗi! Không tìm thấy giftcode nào tên là `{code}`.")

@admin_group.command(name="view", description="Xem chi tiết thông tin của người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_view_slash(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    user_data = get_user_data(member.id)
    if not user_data: await interaction.followup.send("Không tìm thấy user."); return
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
    await interaction.followup.send(embed=embed)

@admin_group.command(name="resetdaily", description="Reset thời gian daily và streak cho người dùng.")
@app_commands.checks.has_role(ADMIN_ROLE)
@global_rate_limit()
async def admin_resetdaily_slash(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try: supabase.table('profiles').update({'last_daily': None, 'last_streak_date': None, 'daily_streak': 0}).eq('user_id', member.id).execute(); await interaction.followup.send(f"✅ Đã reset thời gian `daily` và streak cho {member.mention}.")
    except Exception as e: await interaction.followup.send(f"Lỗi khi reset daily: {e}")

@admin_group.command(name="announce", description="Gửi thông báo tới kênh chỉ định.")
@app_commands.checks.has_role(ADMIN_ROLE)
@app_commands.describe(channel="Kênh muốn gửi thông báo", message="Nội dung thông báo")
@global_rate_limit()
async def admin_announce_slash(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await interaction.response.defer(ephemeral=True)
    try: embed = discord.Embed(title="📢 Thông Báo Từ Admin 📢", description=message, color=discord.Color.orange()); embed.set_footer(text=f"Gửi bởi {interaction.user.display_name}"); await channel.send(embed=embed); await interaction.followup.send("✅ Đã gửi thông báo.")
    except Exception as e: await interaction.followup.send(f"Lỗi khi gửi thông báo: {e}")

bot.tree.add_command(admin_group) # Đăng ký nhóm lệnh admin


# --- GAME 24/7: TÀI XỈU (UI) ---
# (Class BetModal, TaiXiuGameView, get_bet_totals, tai_xiu_game_loop giữ nguyên như user_19/user_21)
# ... Dán code BetModal ...
# ... Dán code TaiXiuGameView ...
# ... Dán code get_bet_totals ...
# ... Dán code @tasks.loop tai_xiu_game_loop (bao gồm xử lý nổ hũ) ...
# ... Dán code @tai_xiu_game_loop.before_loop ...

# (Lệnh start/stop dùng Slash Commands, start không cần role)
@bot.slash_command(name="start_taixiu", description="Bắt đầu vòng lặp game Tài Xỉu 24/7 tại kênh này.")
@global_rate_limit()
async def start_taixiu_slash(interaction: discord.Interaction):
    global game_channel_id
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
        await interaction.response.send_message("✅ Đã dừng Game Tài Xỉu.")
        await asyncio.sleep(1) # Đợi loop thực sự dừng
        game_channel_id = None
        current_bets = {} # Xóa cược còn lại
        if game_message: # Xóa tin nhắn game cũ nếu có
            try: await game_message.delete()
            except: pass
            game_message = None
    else:
        await interaction.response.send_message("Game chưa chạy.", ephemeral=True)


# --- GAME THEO LỆNH (SLASH COMMANDS, CÓ HIỆU ỨNG VÀ KHÓA) ---
# (Chuyển đổi !slots, !hilo, !tungxu, !xucxac, !baucua, !duangua, !quay, !baccarat sang Slash)
# Ví dụ cho slots:
@bot.slash_command(name="slots", description="Chơi máy xèng.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược")
@global_rate_limit()
@is_user_not_in_game()
async def slots_slash(interaction: discord.Interaction, bet_amount: int):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer() # Quan trọng: báo Discord chờ
    try:
        final_results = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
        embed = discord.Embed(title="🎰 Máy Xèng 🎰", description="| - | - | - |", color=discord.Color.blue())
        embed.set_footer(text=f"{interaction.user.display_name} đã cược {bet_amount:,} 🪙")
        slot_message = await interaction.followup.send(embed=embed, wait=True) # Dùng followup

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
            embed.description += f"\n\n**💥💥💥 JACKPOT TIẾN TRIỂN!!! 💥💥💥**"; update_jackpot_pool('slots', -jackpot_pool); update_jackpot_pool('slots', 1000) # Reset về 1000
        elif final_results[0] == final_results[1] == final_results[2]:
            payout = SLOT_PAYOUTS[final_results[0]]; winnings = bet_amount * payout
            embed.description += f"\n\n**JACKPOT!** Bạn trúng 3x {final_results[0]} (1 ăn {payout})!"
        elif final_results[0] == final_results[1] or final_results[1] == final_results[2]:
            matching_symbol = final_results[1]; winnings = bet_amount * 1 # Chỉ trả 1:1 cho 2x
            embed.description += f"\n\nBạn trúng 2x {matching_symbol} (1 ăn 1)!"

        jackpot_contrib = int(bet_amount * 0.01) if not is_jackpot and bet_amount > 0 else 0 # Chỉ contrib nếu cược > 0
        if jackpot_contrib > 0: update_jackpot_pool('slots', jackpot_contrib)
        net_gain = winnings if is_jackpot else (winnings - jackpot_contrib if winnings > 0 else -(bet_amount - jackpot_contrib)) # Tính net gain/loss chính xác hơn
        new_balance = update_balance(user_id, net_gain)
        update_profile_stats(user_id, bet_amount, net_gain)

        if winnings > 0: embed.description += f"\n🎉 Bạn thắng **{winnings:,}** 🪙!\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description += f"\n\n😢 Chúc may mắn lần sau.\nBạn mất **{bet_amount:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        current_jackpot = get_jackpot_pool('slots'); embed.add_field(name="💰 Jackpot Slots Hiện Tại", value=f"**{current_jackpot:,}** 🪙", inline=False)

        try: await slot_message.edit(embed=embed)
        except discord.NotFound: await interaction.followup.send(embed=embed) # Gửi lại nếu bị xóa

    except asyncio.CancelledError: await interaction.followup.send("Trò chơi bị hủy do tin nhắn bị xóa.", ephemeral=True)
    except Exception as e: print(f"Lỗi /slots: {e}"); await interaction.followup.send("Đã xảy ra lỗi khi chơi Slots.", ephemeral=True)
    finally: bot.users_in_animation.discard(user_id)

# ... (Tương tự chuyển đổi /hilo, /tungxu, /xucxac, /baucua, /duangua, /quay, /baccarat) ...
@bot.slash_command(name="hilo", description="Đoán lá bài tiếp theo cao hay thấp hơn.")
@app_commands.describe(bet_amount="Số tiền cược", choice="Đoán 'cao' hay 'thấp'")
@app_commands.choices(choice=[
    app_commands.Choice(name="Cao", value="cao"),
    app_commands.Choice(name="Thấp", value="thấp")
])
@global_rate_limit()
@is_user_not_in_game()
async def hilo_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer() # Báo Discord chờ
    try:
        # Rút lá 1
        rank1 = random.choice(list(CARD_RANKS_HILO.keys())); suit1 = random.choice(CARD_SUITS); val1 = CARD_RANKS_HILO[rank1]; card1_str = f"**{rank1}{suit1}** (Giá trị: {val1})"

        embed = discord.Embed(title="⬆️ Cao hay Thấp ⬇️", color=discord.Color.blue())
        embed.add_field(name="Lá bài đầu tiên", value=card1_str, inline=False)
        embed.add_field(name="Bạn cược", value=f"**{bet_amount:,}** 🪙 vào **{choice.upper()}**", inline=False)
        embed.add_field(name="Lá bài tiếp theo", value="Đang rút bài...", inline=False)
        msg = await interaction.followup.send(embed=embed, wait=True)
        await asyncio.sleep(3)

        # Rút lá 2
        rank2 = random.choice(list(CARD_RANKS_HILO.keys())); suit2 = random.choice(CARD_SUITS); val2 = CARD_RANKS_HILO[rank2]; card2_str = f"**{rank2}{suit2}** (Giá trị: {val2})"
        embed.set_field_at(2, name="Lá bài tiếp theo", value=card2_str, inline=False)

        is_win = False
        result_desc = ""
        if val2 > val1:
            result_desc = f"{val2} **LỚN HƠN** {val1}"
            if choice == 'cao': is_win = True
        elif val2 < val1:
            result_desc = f"{val2} **NHỎ HƠN** {val1}"
            if choice == 'thấp': is_win = True
        else: # val1 == val2
            result_desc = "Bằng nhau! Nhà cái thắng."
            is_win = False

        embed.add_field(name="Kết quả", value=result_desc, inline=False)

        payout = bet_amount if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        if is_win: embed.description = f"🎉 **Bạn đã thắng!**\nBạn nhận được **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()

        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Lỗi /hilo: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi chơi Cao/Thấp.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

@bot.slash_command(name="tungxu", description="Cược 50/50 sấp hay ngửa.")
@app_commands.describe(bet_amount="Số tiền cược", choice="Đoán 'sấp' hay 'ngửa'")
@app_commands.choices(choice=[
    app_commands.Choice(name="Sấp", value="sấp"),
    app_commands.Choice(name="Ngửa", value="ngửa")
])
@global_rate_limit()
@is_user_not_in_game()
async def coinflip_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        embed = discord.Embed(title="🪙 Đang tung đồng xu...", description="Đồng xu đang xoay trên không...", color=discord.Color.blue())
        msg = await interaction.followup.send(embed=embed, wait=True)
        await asyncio.sleep(2.5)

        result = random.choice(['sấp', 'ngửa'])
        # Chuẩn hóa choice đầu vào (nếu người dùng gõ sap/ngua)
        normalized_choice = 'sấp' if choice in ['sấp', 'sap'] else 'ngửa'
        is_win = (normalized_choice == result)

        payout = bet_amount if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        embed.title = f"Tung đồng xu 🪙... Kết quả là **{result.upper()}**!"
        if is_win: embed.description = f"🎉 Bạn đoán đúng! Bạn thắng **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Lỗi /tungxu: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi tung xu.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

@bot.slash_command(name="xucxac", description="Đoán kết quả 1 viên xúc xắc (1-6), thắng 1 ăn 5.")
@app_commands.describe(bet_amount="Số tiền cược", guess="Số bạn đoán (1 đến 6)")
@global_rate_limit()
@is_user_not_in_game()
async def dice_roll_slash(interaction: discord.Interaction, bet_amount: int, guess: app_commands.Range[int, 1, 6]): # Dùng Range để giới hạn
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        embed = discord.Embed(title="🎲 Đang gieo xúc xắc...", description="Xúc xắc đang lăn...", color=discord.Color.dark_purple())
        msg = await interaction.followup.send(embed=embed, wait=True)
        await asyncio.sleep(2.5)

        result = random.randint(1, 6)
        is_win = (guess == result)
        winnings = bet_amount * 5 if is_win else 0
        payout = winnings if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        embed.title = f"Gieo xúc xắc 🎲... Kết quả là **{result}**!"
        if is_win: embed.description = f"🎉 Chính xác! Bạn thắng **{winnings:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Lỗi /xucxac: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi gieo xúc xắc.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

@bot.slash_command(name="baucua", description="Cược Bầu Cua Tôm Cá.")
@app_commands.describe(bet_amount="Số tiền cược", choice="Linh vật bạn muốn cược")
@app_commands.choices(choice=[ # Tạo lựa chọn sẵn cho người dùng
    app_commands.Choice(name="Bầu 🍐", value="bầu"),
    app_commands.Choice(name="Cua 🦀", value="cua"),
    app_commands.Choice(name="Tôm 🦐", value="tôm"),
    app_commands.Choice(name="Cá 🐟", value="cá"),
    app_commands.Choice(name="Gà 🐓", value="gà"),
    app_commands.Choice(name="Nai 🦌", value="nai"),
])
@global_rate_limit()
@is_user_not_in_game()
async def bau_cua_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    user_choice_full = BAU_CUA_FACES.get(choice.lower().strip()) # Lấy tên đầy đủ + emoji
    if not user_choice_full: await interaction.response.send_message('Lựa chọn không hợp lệ!', ephemeral=True); return # Lỗi này không nên xảy ra với choices

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        final_results = random.choices(BAU_CUA_LIST, k=3)
        embed = discord.Embed(title="🦀 Đang lắc Bầu Cua...", description="| ❔ | ❔ | ❔ |", color=discord.Color.dark_orange())
        embed.set_footer(text=f"{interaction.user.display_name} cược {bet_amount:,} 🪙 vào {user_choice_full}")
        msg = await interaction.followup.send(embed=embed, wait=True)
        current_display = ['❔'] * 3
        for i in range(5): # Hiệu ứng khóa
            if i < 2: current_display[0] = random.choice(BAU_CUA_LIST)
            else: current_display[0] = final_results[0]
            if i < 3: current_display[1] = random.choice(BAU_CUA_LIST)
            else: current_display[1] = final_results[1]
            if i < 4: current_display[2] = random.choice(BAU_CUA_LIST)
            else: current_display[2] = final_results[2]
            embed.description = f"| **{current_display[0]}** | **{current_display[1]}** | **{current_display[2]}** |"
            try: await msg.edit(embed=embed)
            except discord.NotFound: raise asyncio.CancelledError("Message deleted")
            await asyncio.sleep(0.7)

        hits = final_results.count(user_choice_full)
        is_win = (hits > 0)
        winnings = bet_amount * hits if is_win else 0
        payout = winnings if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        embed.title = "🦀 Lắc Bầu Cua 🎲"
        if is_win: embed.description += f"\n\n🎉 **Bạn đã thắng!** Trúng {hits} lần.\nBạn nhận được **{winnings:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description += f"\n\n😢 **Bạn đã thua!** Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except asyncio.CancelledError: await interaction.followup.send("Trò chơi bị hủy do tin nhắn bị xóa.", ephemeral=True)
    except Exception as e:
        print(f"Lỗi /baucua: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi chơi Bầu Cua.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

# Helper function for horse race track display
def get_race_track(positions):
    track = ""
    for i in range(NUM_HORSES):
        pos_clamped = min(positions[i], RACE_LENGTH)
        # Display trophy only if exactly at finish line or beyond
        finish_char = '🏆' if positions[i] >= RACE_LENGTH else '🏁'
        track += f"🐎 {i+1}: {'─' * pos_clamped}{finish_char}\n" # Use a different dash
    return track

@bot.slash_command(name="duangua", description="Cược đua ngựa (1-6), thắng 1 ăn 4.")
@app_commands.describe(bet_amount="Số tiền cược", horse_number="Ngựa bạn chọn (1 đến 6)")
@global_rate_limit()
@is_user_not_in_game()
async def dua_ngua_slash(interaction: discord.Interaction, bet_amount: int, horse_number: app_commands.Range[int, 1, NUM_HORSES]):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        positions = [0] * NUM_HORSES
        embed = discord.Embed(title="🐎 Cuộc Đua Bắt Đầu! 🐎", description=get_race_track(positions), color=discord.Color.blue())
        embed.set_footer(text=f"{interaction.user.display_name} cược {bet_amount:,} 🪙 vào ngựa số {horse_number}.")
        race_msg = await interaction.followup.send(embed=embed, wait=True)

        winner = None
        while winner is None:
            await asyncio.sleep(2)
            # Determine winner(s) in this step
            potential_winners = []
            for i in range(NUM_HORSES):
                if positions[i] < RACE_LENGTH: # Only move horses not finished
                    positions[i] += random.randint(1, 3)
                    if positions[i] >= RACE_LENGTH:
                        potential_winners.append(i + 1)

            # Check if there's a winner or a tie
            if potential_winners:
                 # Simple tie-breaking: lowest number wins if tied in the same step
                 winner = min(potential_winners)

            # Update display
            embed.description = get_race_track(positions)
            try: await race_msg.edit(embed=embed)
            except discord.NotFound: raise asyncio.CancelledError("Message deleted")
            # Loop breaks naturally if winner is found

        is_win = (winner == horse_number)
        winnings = bet_amount * 4 if is_win else 0
        payout = winnings if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        result_title = f"🐎 Ngựa số {winner} đã chiến thắng! 🏆"
        result_description = get_race_track(positions) # Final track display
        if is_win:
            result_description += f"\n\n🎉 **Bạn đã thắng!** Ngựa số {horse_number} đã về nhất!\nBạn nhận được **{winnings:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else:
            result_description += f"\n\n😢 **Bạn đã thua!** Ngựa của bạn (số {horse_number}) đã không thắng.\nBạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        embed.title = result_title; embed.description = result_description
        try: await race_msg.edit(embed=embed)
        except discord.NotFound: await interaction.followup.send(embed=embed) # Send new if deleted
    except asyncio.CancelledError: await interaction.followup.send("Trò chơi bị hủy do tin nhắn bị xóa.", ephemeral=True)
    except Exception as e:
        print(f"Lỗi /duangua: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi đua ngựa.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

# Helper function to parse complex Roulette bets
def parse_roulette_bet(bet_type_str):
    bet_type_str = bet_type_str.lower().strip()
    numbers_involved = []
    payout_category = None

    # Single number
    if bet_type_str.isdigit() and 0 <= int(bet_type_str) <= 36:
        numbers_involved.append(int(bet_type_str))
        payout_category = 'single'
    # Colors, Even/Odd, Halves
    elif bet_type_str in ['đỏ', 'red']: payout_category = 'color'; numbers_involved = RED_NUMBERS
    elif bet_type_str in ['đen', 'black']: payout_category = 'color'; numbers_involved = BLACK_NUMBERS
    elif bet_type_str in ['lẻ', 'odd']: payout_category = 'evenodd'; numbers_involved = [n for n in range(1, 37) if n % 2 != 0]
    elif bet_type_str in ['chẵn', 'even']: payout_category = 'evenodd'; numbers_involved = [n for n in range(1, 37) if n % 2 == 0]
    elif bet_type_str in ['nửa1', '1-18']: payout_category = 'half'; numbers_involved = list(range(1, 19))
    elif bet_type_str in ['nửa2', '19-36']: payout_category = 'half'; numbers_involved = list(range(19, 37))
    # Dozens
    elif bet_type_str in ['tá1', '1-12', 'dozen1']: payout_category = 'dozen'; numbers_involved = list(range(1, 13))
    elif bet_type_str in ['tá2', '13-24', 'dozen2']: payout_category = 'dozen'; numbers_involved = list(range(13, 25))
    elif bet_type_str in ['tá3', '25-36', 'dozen3']: payout_category = 'dozen'; numbers_involved = list(range(25, 37))
    # Columns (Example: col1 includes 1, 4, 7,... 34)
    elif bet_type_str in ['cột1', 'col1']: payout_category = 'column'; numbers_involved = [n for n in range(1, 37) if n % 3 == 1]
    elif bet_type_str in ['cột2', 'col2']: payout_category = 'column'; numbers_involved = [n for n in range(1, 37) if n % 3 == 2]
    elif bet_type_str in ['cột3', 'col3']: payout_category = 'column'; numbers_involved = [n for n in range(1, 37) if n % 3 == 0]
    # Complex bets (Split, Street, Corner, Six Line) using regex
    else:
        # Split (e.g., split-1-2, split-17-20)
        split_match = re.match(r"split-(\d{1,2})-(\d{1,2})", bet_type_str)
        if split_match:
            n1, n2 = int(split_match.group(1)), int(split_match.group(2))
            # Basic validation (add more robust checks if needed, e.g., adjacency)
            if 1 <= n1 <= 36 and 1 <= n2 <= 36 and n1 != n2:
                numbers_involved = [n1, n2]; payout_category = 'split'
        # Street (e.g., street-1-2-3, street-34-35-36)
        street_match = re.match(r"street-(\d{1,2})-(\d{1,2})-(\d{1,2})", bet_type_str)
        if street_match:
            n1, n2, n3 = int(street_match.group(1)), int(street_match.group(2)), int(street_match.group(3))
            if 1 <= n1 <= 36 and 1 <= n2 <= 36 and 1 <= n3 <= 36 and n1 != n2 != n3 != n1:
                 numbers_involved = [n1, n2, n3]; payout_category = 'street'
        # Corner (e.g., corner-1-2-4-5)
        corner_match = re.match(r"corner-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})", bet_type_str)
        if corner_match:
             n1, n2, n3, n4 = map(int, corner_match.groups())
             if all(1 <= n <= 36 for n in [n1, n2, n3, n4]) and len(set([n1, n2, n3, n4])) == 4:
                 numbers_involved = [n1, n2, n3, n4]; payout_category = 'corner'
        # Six Line (e.g., sixline-1-6)
        sixline_match = re.match(r"sixline-(\d{1,2})-(\d{1,2})", bet_type_str)
        if sixline_match:
             start, end = int(sixline_match.group(1)), int(sixline_match.group(2))
             # Basic validation: ensure it's a valid range of 6
             if 1 <= start <= 31 and end == start + 5:
                  numbers_involved = list(range(start, end + 1)); payout_category = 'sixline'

    if not payout_category:
        raise ValueError(f"Invalid Roulette bet type: {bet_type_str}")

    return {'category': payout_category, 'numbers': numbers_involved}


@bot.slash_command(name="quay", description="Chơi Roulette.")
@app_commands.describe(bet_amount="Số tiền cược", bet_type="Loại cược (số, màu, tá, cột, split-x-y, etc.)")
@global_rate_limit()
@is_user_not_in_game()
async def roulette_slash(interaction: discord.Interaction, bet_amount: int, bet_type: str):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    try:
        parsed_bet = parse_roulette_bet(bet_type)
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True)
        return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        embed = discord.Embed(title="🎰 Vòng quay Roulette 🎰", description="Bóng đang quay... 🔄", color=discord.Color.dark_red())
        embed.set_footer(text=f"{interaction.user.display_name} cược {bet_amount:,} 🪙 vào {bet_type}")
        msg = await interaction.followup.send(embed=embed, wait=True)

        spin_result = random.randint(0, 36)
        spin_color = 'xanh lá 🟩' if spin_result == 0 else ('đỏ 🟥' if spin_result in RED_NUMBERS else 'đen ⬛')
        await asyncio.sleep(4)

        is_win = (spin_result != 0 and spin_result in parsed_bet['numbers']) or \
                 (spin_result == 0 and 0 in parsed_bet['numbers']) # Check win condition

        winnings = 0
        payout_rate = 0
        if is_win:
            payout_rate = ROULETTE_PAYOUTS[parsed_bet['category']]
            winnings = bet_amount * payout_rate

        payout = winnings if is_win else -bet_amount
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        result_message = f"**Bóng dừng tại số: {spin_result} ({spin_color})**\n\n"
        result_message += f"{interaction.user.mention} đã cược **{bet_amount:,}** 🪙 vào **{bet_type}**.\n"

        if is_win:
            result_message += f"🎉 **Bạn đã thắng!** (1 ăn {payout_rate})\nBạn nhận được **{winnings:,}** token.\n"; embed.color = discord.Color.green()
        else:
            result_message += f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount:,}** token.\n"; embed.color = discord.Color.red()
        result_message += f"Số dư mới: **{new_balance:,}** 🪙."
        embed.description = result_message
        await msg.edit(embed=embed)

    except Exception as e:
        print(f"Lỗi /quay: {e}")
        # Dont send error if due to invalid bet handled above
        if "Invalid Roulette bet type" not in str(e):
             await interaction.followup.send("Đã xảy ra lỗi khi chơi Roulette.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

# Helper to create Baccarat deck (A=1, JQK=0)
def create_baccarat_deck():
    deck = []
    for suit in CARD_SUITS:
        for rank, value in CARD_RANKS_BACCARAT.items():
            deck.append({'rank': rank, 'suit': suit, 'value': value})
    random.shuffle(deck)
    return deck

# Helper to calculate Baccarat score (unit digit)
def calculate_baccarat_score(hand):
    return sum(card['value'] for card in hand) % 10

@bot.slash_command(name="baccarat", description="Chơi Baccarat. Cược Player, Banker, hoặc Tie.")
@app_commands.describe(bet_amount="Số tiền cược", choice="Cửa bạn muốn cược")
@app_commands.choices(choice=[
    app_commands.Choice(name="Player", value="player"),
    app_commands.Choice(name="Banker", value="banker"),
    app_commands.Choice(name="Tie (Hòa)", value="tie")
])
@global_rate_limit()
@is_user_not_in_game()
async def baccarat_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)

    if bet_amount <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.response.send_message(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    bot.users_in_animation.add(user_id)
    await interaction.response.defer()
    try:
        embed = discord.Embed(title="🃏 Baccarat 🃏", description="Đang chia bài...", color=discord.Color.dark_green())
        embed.set_footer(text=f"{interaction.user.display_name} cược {bet_amount:,} 🪙 vào {choice.upper()}")
        msg = await interaction.followup.send(embed=embed, wait=True)
        await asyncio.sleep(3)

        deck = create_baccarat_deck()
        player_hand = [deck.pop(), deck.pop()]
        banker_hand = [deck.pop(), deck.pop()]
        player_score = calculate_baccarat_score(player_hand)
        banker_score = calculate_baccarat_score(banker_hand)

        player_draw = False
        player_third_card_value = -1 # Giá trị lá thứ 3 của player (nếu rút)

        # Kiểm tra Natural win
        natural_win = False
        if player_score >= 8 or banker_score >= 8:
             natural_win = True
        else:
            # Luật rút lá thứ 3
            if player_score <= 5: # Player draws
                player_third_card = deck.pop()
                player_hand.append(player_third_card)
                player_score = calculate_baccarat_score(player_hand)
                player_draw = True
                player_third_card_value = player_third_card['value']

            banker_draws = False
            if not player_draw: # Player stands
                if banker_score <= 5: banker_draws = True
            else: # Player draws
                if banker_score <= 2: banker_draws = True
                elif banker_score == 3 and player_third_card_value != 8: banker_draws = True
                elif banker_score == 4 and player_third_card_value in [2, 3, 4, 5, 6, 7]: banker_draws = True
                elif banker_score == 5 and player_third_card_value in [4, 5, 6, 7]: banker_draws = True
                elif banker_score == 6 and player_third_card_value in [6, 7]: banker_draws = True

            if banker_draws:
                banker_hand.append(deck.pop())
                banker_score = calculate_baccarat_score(banker_hand)

        # Xác định người thắng
        winner = "tie"
        if player_score > banker_score: winner = "player"
        elif banker_score > player_score: winner = "banker"

        winnings = 0; payout = 0
        if winner == choice:
            if winner == 'player': winnings = bet_amount * 1; payout = winnings
            elif winner == 'banker': winnings = int(bet_amount * 0.95); payout = winnings
            elif winner == 'tie': winnings = bet_amount * 8; payout = winnings
        else:
            payout = -bet_amount # Thua

        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)

        embed.title = f"🃏 Baccarat - {winner.upper()} Thắng! 🃏"
        embed.add_field(name=f"Player ({player_score})", value=hand_to_string(player_hand), inline=True)
        embed.add_field(name=f"Banker ({banker_score})", value=hand_to_string(banker_hand), inline=True)
        if payout >= 0: # Bao gồm cả hòa (payout=0)
            embed.description = f"🎉 Bạn cược {choice.upper()} và đã {'thắng' if payout > 0 else 'hòa'}!\nBạn nhận được **{winnings:,}** 🪙!\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else:
            embed.description = f"😢 Bạn cược {choice.upper()} và đã thua!\nBạn mất **{bet_amount:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()

        await msg.edit(embed=embed)
    except Exception as e:
        print(f"Lỗi /baccarat: {e}")
        await interaction.followup.send("Đã xảy ra lỗi khi chơi Baccarat.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(user_id)

lottery_group = app_commands.Group(name="lottery", description="Lệnh liên quan đến xổ số")

@lottery_group.command(name="buy", description="Mua vé số (6 số từ 1 đến 45).")
@app_commands.describe(n1="Số 1", n2="Số 2", n3="Số 3", n4="Số 4", n5="Số 5", n6="Số 6")
@global_rate_limit()
@is_user_not_in_game()
async def lottery_buy_slash(interaction: discord.Interaction,
                             n1: app_commands.Range[int, 1, 45], n2: app_commands.Range[int, 1, 45],
                             n3: app_commands.Range[int, 1, 45], n4: app_commands.Range[int, 1, 45],
                             n5: app_commands.Range[int, 1, 45], n6: app_commands.Range[int, 1, 45]):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if not user_data: await interaction.followup.send("Lỗi lấy dữ liệu user."); return
    balance = user_data.get('balance', 0)

    numbers = sorted(list(set([n1, n2, n3, n4, n5, n6]))) # Sắp xếp và loại trùng

    if len(numbers) != 6: await interaction.followup.send("Phải chọn đúng 6 số khác nhau."); return
    # Range đã kiểm tra 1-45

    if balance < LOTTERY_TICKET_PRICE: await interaction.followup.send(f"Bạn không đủ tiền mua vé! Cần {LOTTERY_TICKET_PRICE} 🪙."); return

    new_balance = update_balance(user_id, -LOTTERY_TICKET_PRICE)
    if new_balance is None: await interaction.followup.send("Lỗi khi trừ tiền!"); return
    update_profile_stats(user_id, LOTTERY_TICKET_PRICE, -LOTTERY_TICKET_PRICE)

    today = datetime.now(VIETNAM_TZ).date()
    try:
        supabase.table('lottery_tickets').insert({'user_id': user_id, 'numbers': numbers, 'draw_date': str(today)}).execute()
        await interaction.followup.send(f"✅ Bạn đã mua thành công vé số cho ngày {today.strftime('%d/%m/%Y')} với các số: `{' '.join(map(str, numbers))}`. Số dư: {new_balance:,} 🪙.")
    except Exception as e:
        await interaction.followup.send(f"Lỗi khi lưu vé số: {e}")
        # Cố gắng hoàn tiền
        update_balance(user_id, LOTTERY_TICKET_PRICE)
        update_profile_stats(user_id, 0, LOTTERY_TICKET_PRICE)


@lottery_group.command(name="result", description="Xem kết quả xổ số gần nhất.")
@global_rate_limit()
async def lottery_result_slash(interaction: discord.Interaction):
    await interaction.response.defer()
    today_vn = datetime.now(VIETNAM_TZ).date()
    try:
        result = supabase.table('lottery_draws').select('*').lte('draw_date', str(today_vn)).order('draw_date', desc=True).limit(1).execute().data
        if not result: await interaction.followup.send("Chưa có kết quả xổ số."); return

        draw = result[0]; draw_date = date.fromisoformat(draw['draw_date']); winning_numbers = draw['winning_numbers']; jackpot = draw['jackpot_amount']; winners_data = draw['winners'] or []

        embed = discord.Embed(title=f"🏆 Kết quả Xổ số ngày {draw_date.strftime('%d/%m/%Y')} 🏆", color=discord.Color.gold())
        embed.add_field(name="🔢 Dãy số trúng thưởng", value=f"`{' '.join(map(str, winning_numbers))}`" if winning_numbers else "Chưa có", inline=False)
        embed.add_field(name="💰 Giải Jackpot kỳ này", value=f"**{jackpot:,}** 🪙", inline=False)

        winners_text = ""
        # Sắp xếp người thắng theo giải
        winners_data.sort(key=lambda w: int(w.get('matched', 0)), reverse=True)
        for winner in winners_data:
            user = bot.get_user(winner['user_id']) # Dùng get_user (nhanh hơn fetch nếu user trong cache)
            username = user.display_name if user else f"User ID {winner['user_id']}"
            winners_text += f"- {username}: Trúng giải {winner.get('prize_tier','N/A')} ({winner.get('matched', '?')} số) - **{winner.get('amount', 0):,}** 🪙\n"
        if not winners_text: winners_text = "Không có ai trúng thưởng kỳ này."
        embed.add_field(name="🎉 Người trúng thưởng", value=winners_text[:1020], inline=False) # Giới hạn 1024 ký tự

        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"Lỗi khi xem kết quả: {e}", ephemeral=True)

bot.tree.add_command(lottery_group)

# Task chạy xổ số hàng ngày
@tasks.loop(time=LOTTERY_DRAW_TIME)
async def lottery_draw_task():
    today = datetime.now(VIETNAM_TZ).date()
    print(f"[{datetime.now(VIETNAM_TZ)}] Bắt đầu quay số cho ngày {today}...")
    try:
        tickets_response = supabase.table('lottery_tickets').select('*').eq('draw_date', str(today)).execute()
        tickets = tickets_response.data
        if not tickets:
            print("Không có vé nào được mua hôm nay. Bỏ qua quay số.")
            try: supabase.table('lottery_draws').insert({'draw_date': str(today), 'winning_numbers': [], 'jackpot_amount': 0, 'winners': []}).execute()
            except Exception as insert_e: print(f"Lỗi khi insert draw rỗng: {insert_e}")
            return

        winning_numbers = sorted(random.sample(range(1, 46), 6))
        total_revenue = len(tickets) * LOTTERY_TICKET_PRICE
        current_jackpot = int(total_revenue * 0.5) + 10000 # Ví dụ jackpot

        winners = []; prize_tiers = {6: 1.0, 5: 0.15, 4: 0.05, 3: 0.01}; remaining_jackpot = current_jackpot
        for match_count in sorted(prize_tiers.keys(), reverse=True):
            tier_winners = []
            for ticket in tickets:
                user_numbers = set(ticket['numbers'])
                matched = len(user_numbers.intersection(winning_numbers))
                if matched == match_count: tier_winners.append({'user_id': ticket['user_id'], 'numbers': ticket['numbers']})

            if tier_winners:
                prize_pool_tier = int(current_jackpot * prize_tiers[match_count]); prize_pool_tier = min(prize_pool_tier, remaining_jackpot)
                if prize_pool_tier > 0:
                    amount_per_winner = prize_pool_tier // len(tier_winners)
                    if amount_per_winner > 0:
                        remaining_jackpot -= (amount_per_winner * len(tier_winners)) # Trừ số tiền thực tế đã chia
                        for winner in tier_winners:
                            update_balance(winner['user_id'], amount_per_winner)
                            update_profile_stats(winner['user_id'], 0, amount_per_winner)
                            winners.append({'user_id': winner['user_id'], 'prize_tier': f"Giải {match_count}", 'matched': match_count, 'amount': amount_per_winner})

        supabase.table('lottery_draws').insert({'draw_date': str(today), 'winning_numbers': winning_numbers, 'jackpot_amount': current_jackpot, 'winners': winners}).execute()
        print(f"Đã quay số xong cho ngày {today}. Số trúng: {winning_numbers}. Jackpot: {current_jackpot}. Winners: {len(winners)}")
    except Exception as e: print(f"LỖI trong lottery_draw_task: {e}")

@lottery_draw_task.before_loop
async def before_lottery_task():
    await bot.wait_until_ready() # Đảm bảo bot sẵn sàng trước khi task chạy

# --- ĐOÁN SỐ (GUESS THE NUMBER) ---
class GuessTheNumberGame:
    def __init__(self, interaction: discord.Interaction, bet_amount):
        self.interaction = interaction # Lưu interaction gốc để followup
        self.channel = interaction.channel
        self.host = interaction.user
        self.bet_amount = bet_amount
        self.number_to_guess = random.randint(1, 100)
        self.participants = {interaction.user.id} # Người khởi tạo tự động tham gia
        self.guesses = {} # user_id: guess_value
        self.message: typing.Optional[discord.WebhookMessage] = None # Sẽ là followup message
        self.start_time = datetime.now(VIETNAM_TZ)
        self.duration = timedelta(minutes=2)
        self._task = None # Task để kết thúc game

    async def start(self):
        embed = discord.Embed(title="🤔 Đoán Số 🤔 (1-100)", description=f"Game bắt đầu! Số tiền cược mỗi người: **{self.bet_amount:,}** 🪙.\nĐoán bằng lệnh `/guess number <số>`.\nCòn **2 phút**...", color=discord.Color.purple())
        embed.set_footer(text=f"Khởi tạo bởi {self.host.display_name}")
        # Gửi bằng followup vì start command đã defer
        self.message = await self.interaction.followup.send(embed=embed, wait=True)
        # Tạo task để tự động kết thúc
        self._task = asyncio.create_task(self.end_game_after_delay())

    async def end_game_after_delay(self):
        await asyncio.sleep(self.duration.total_seconds())
        # Kiểm tra xem game còn tồn tại không trước khi kết thúc
        if bot.guess_the_number_game is self:
             await self.end_game()

    async def add_guess(self, interaction: discord.Interaction, guess: int):
        user = interaction.user
        if not (1 <= guess <= 100):
            await interaction.response.send_message("Số đoán phải từ 1 đến 100.", ephemeral=True, delete_after=5)
            return False

        if datetime.now(VIETNAM_TZ) > self.start_time + self.duration:
             await interaction.response.send_message("Đã hết giờ đoán!", ephemeral=True, delete_after=5)
             return False

        if user.id not in self.participants:
            user_data = get_user_data(user.id)
            if not user_data or user_data.get('balance',0) < self.bet_amount:
                await interaction.response.send_message(f"Bạn không đủ {self.bet_amount:,} 🪙 để tham gia!", ephemeral=True, delete_after=5)
                return False
            new_balance = update_balance(user.id, -self.bet_amount)
            if new_balance is None: await interaction.response.send_message("Lỗi trừ tiền!", ephemeral=True); return False
            update_profile_stats(user.id, self.bet_amount, -self.bet_amount)
            self.participants.add(user.id)
            await interaction.response.send_message(f"Bạn đã tham gia đoán số với {self.bet_amount:,} 🪙. Số dư mới: {new_balance:,} 🪙.", ephemeral=True)
        else:
            # Chỉ cần xác nhận nếu đã tham gia
             await interaction.response.defer(ephemeral=True, thinking=False) # Không gửi gì cả

        self.guesses[user.id] = guess

        if guess == self.number_to_guess:
            # Hủy task tự động kết thúc
            if self._task: self._task.cancel()
            await self.end_game(winner=user)
            return True
        elif guess < self.number_to_guess:
            await self.channel.send(f"{user.mention} đoán `{guess}`: **CAO HƠN!**", delete_after=10)
        else:
            await self.channel.send(f"{user.mention} đoán `{guess}`: **THẤP HƠN!**", delete_after=10)
        return False

    async def end_game(self, winner: typing.Optional[discord.User] = None):
        global bot
        if bot.guess_the_number_game is not self: return # Game đã kết thúc bởi người khác / task khác
        bot.guess_the_number_game = None # Đánh dấu game kết thúc

        total_pot = len(self.participants) * self.bet_amount
        try:
             embed = self.message.embeds[0] # Lấy embed hiện tại
        except (AttributeError, IndexError): # Nếu message hoặc embed không tồn tại
             embed = discord.Embed(title="🤔 Đoán Số 🤔") # Tạo embed mới

        if winner:
            winnings = total_pot; net_gain = winnings - self.bet_amount # Lời = Tổng pot - tiền mình cược
            new_balance = update_balance(winner.id, winnings) # Trả lại cả pot
            update_profile_stats(winner.id, 0, net_gain) # Chỉ tính phần lời
            embed.title = f"🎉 {winner.display_name} ĐÃ ĐOÁN TRÚNG SỐ {self.number_to_guess}! 🎉"
            embed.description = f"Chúc mừng {winner.mention} đã thắng **{winnings:,}** 🪙!\nSố dư mới: **{new_balance:,}** 🪙."
            embed.color = discord.Color.gold()
        else:
            embed.title = f"⌛ HẾT GIỜ! Số cần đoán là {self.number_to_guess} ⌛"
            embed.description = "Không ai đoán trúng. Đã hoàn lại tiền cược cho người tham gia."
            embed.color = discord.Color.dark_grey()
            # Hoàn tiền (đã trừ lúc tham gia, giờ cộng lại)
            for user_id in self.participants:
                update_balance(user_id, self.bet_amount)
                update_profile_stats(user_id, 0, self.bet_amount) # Hoàn lại tiền đã tính lỗ

        try:
             await self.message.edit(embed=embed)
        except Exception as e:
             print(f"Lỗi khi edit message kết thúc GuessTheNumber: {e}")
             # Gửi tin nhắn mới nếu edit lỗi
             await self.channel.send(embed=embed)


guess_group = app_commands.Group(name="guess", description="Lệnh chơi game đoán số")

@guess_group.command(name="start", description="Bắt đầu game Đoán Số (1-100).")
@app_commands.describe(bet_amount="Số tiền cược để tham gia")
@global_rate_limit()
@is_user_not_in_game()
async def guess_the_number_start_slash(interaction: discord.Interaction, bet_amount: int):
    if bot.guess_the_number_game:
        await interaction.response.send_message("Đang có một game Đoán Số diễn ra rồi!", ephemeral=True); return
    if bet_amount <= 0: await interaction.response.send_message("Tiền cược phải lớn hơn 0!", ephemeral=True); return
    user_data = get_user_data(interaction.user.id)
    if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
    if user_data.get('balance',0) < bet_amount: await interaction.response.send_message(f"Bạn không đủ {bet_amount:,} 🪙 để bắt đầu game!", ephemeral=True); return

    await interaction.response.defer() # Defer trước khi trừ tiền và bắt đầu game

    new_balance = update_balance(interaction.user.id, -bet_amount)
    if new_balance is None: await interaction.followup.send("Lỗi trừ tiền!", ephemeral=True); return
    update_profile_stats(interaction.user.id, bet_amount, -bet_amount)

    bot.guess_the_number_game = GuessTheNumberGame(interaction, bet_amount)
    await bot.guess_the_number_game.start()

@guess_group.command(name="number", description="Đoán số trong game Đoán Số đang chạy.")
@app_commands.describe(number="Số bạn đoán (1-100)")
@global_rate_limit() # Vẫn áp dụng rate limit chung
# Không cần is_user_not_in_game ở đây vì phải cho phép đoán khi đang chơi
async def guess_number_slash(interaction: discord.Interaction, number: int):
    if not bot.guess_the_number_game:
        await interaction.response.send_message("Hiện không có game Đoán Số nào đang chạy.", ephemeral=True, delete_after=5); return

    # Thêm lượt đoán (hàm add_guess sẽ tự xử lý response)
    await bot.guess_the_number_game.add_guess(interaction, number)

bot.tree.add_command(guess_group)

# --- BLACKJACK (XÌ DÁCH) ---
def create_deck(use_bj_ranks=True): # Thêm tham số để dùng đúng rank
    deck = []
    ranks_to_use = CARD_RANKS_BJ if use_bj_ranks else CARD_RANKS_BACCARAT
    for suit in CARD_SUITS:
        for rank, value in ranks_to_use.items():
            deck.append({'rank': rank, 'suit': suit, 'value': value})
    random.shuffle(deck)
    return deck

def calculate_bj_score(hand): # Đổi tên hàm tính điểm BJ
    score = sum(card['value'] for card in hand)
    aces = sum(1 for card in hand if card['rank'] == 'A')
    while score > 21 and aces: score -= 10; aces -= 1 # A = 11 -> 1
    return score

def hand_to_string(hand): return " | ".join(f"**{c['rank']}{c['suit']}**" for c in hand)

class BlackjackView(ui.View):
    def __init__(self, author_id, game):
        super().__init__(timeout=300.0); self.author_id = author_id; self.game = game
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id: await interaction.response.send_message("Đây không phải ván bài của bạn!", ephemeral=True); return False
        return True
    async def on_timeout(self):
        # Kiểm tra xem game có thực sự còn trong dict không trước khi pop
        if self.author_id in bot.blackjack_games and bot.blackjack_games[self.author_id] == self.game:
            game = bot.blackjack_games.pop(self.author_id); embed = game['embed']
            embed.title = "🃏 Xì Dách (Hết giờ) 🃏"; embed.description = "Bạn đã không phản hồi. Ván bài bị hủy."; embed.color = discord.Color.dark_grey()
            for item in self.children: item.disabled = True
            try: await game['message'].edit(embed=embed, view=self)
            except discord.NotFound: pass # Bỏ qua nếu tin nhắn bị xóa
    async def end_game(self, interaction: typing.Optional[discord.Interaction], result_text: str, payout: int):
        user_id = self.author_id
        # Chỉ pop game nếu nó vẫn còn trong dict và là game hiện tại
        if user_id not in bot.blackjack_games or bot.blackjack_games[user_id] != self.game: return # Game đã kết thúc hoặc timeout
        game_data = bot.blackjack_games.pop(user_id) # Lấy và xóa game

        new_balance = update_balance(user_id, payout)
        # Update stats chỉ khi game kết thúc (không phải timeout)
        if interaction: update_profile_stats(user_id, game_data['bet'], payout)

        embed = game_data['embed']; embed.title = f"🃏 Xì Dách ({result_text}) 🃏"
        embed.color = discord.Color.green() if payout > 0 else (discord.Color.red() if payout < 0 else discord.Color.light_grey())
        dealer_score = calculate_bj_score(game_data['dealer_hand'])
        embed.set_field_at(0, name=f"Bài Dealer ({dealer_score})", value=hand_to_string(game_data['dealer_hand']), inline=False)
        if payout > 0: embed.description = f"🎉 **Bạn thắng {abs(payout):,} 🪙!**\nSố dư mới: **{new_balance:,}** 🪙."
        elif payout < 0: embed.description = f"😢 **Bạn thua {abs(payout):,} 🪙!**\nSố dư mới: **{new_balance:,}** 🪙."
        else: embed.description = f"⚖️ **Hòa (Push)!**\nBạn được hoàn tiền. Số dư: **{new_balance:,}** 🪙."
        for item in self.children: item.disabled = True
        # Nếu interaction tồn tại (kết thúc do người chơi), dùng response.edit
        if interaction: await interaction.response.edit_message(embed=embed, view=self)
        # Nếu interaction là None (kết thúc do timeout hoặc lỗi khác), dùng message.edit
        else:
             try: await game_data['message'].edit(embed=embed, view=self)
             except discord.NotFound: pass # Bỏ qua nếu tin nhắn bị xóa
    @ui.button(label="Rút (Hit)", style=discord.ButtonStyle.primary, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: ui.Button):
        if self.author_id not in bot.blackjack_games or bot.blackjack_games[self.author_id] != self.game: return # Kiểm tra game còn tồn tại
        game = self.game; game['player_hand'].append(game['deck'].pop()); player_score = calculate_bj_score(game['player_hand'])
        embed = game['embed']; embed.set_field_at(1, name=f"Bài của bạn ({player_score})", value=hand_to_string(game['player_hand']), inline=False)
        if player_score > 21: await self.end_game(interaction, "Bạn bị Quắc!", -game['bet'])
        else: self.children[2].disabled = True; await interaction.response.edit_message(embed=embed, view=self)
    @ui.button(label="Dằn (Stand)", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, button: ui.Button):
        if self.author_id not in bot.blackjack_games or bot.blackjack_games[self.author_id] != self.game: return
        game = self.game; dealer_hand = game['dealer_hand']; dealer_score = calculate_bj_score(dealer_hand)
        # Dealer rút bài theo luật (rút khi <= 16, dừng khi >= 17)
        while dealer_score < 17:
             if not game['deck']: break # Hết bài
             dealer_hand.append(game['deck'].pop()); dealer_score = calculate_bj_score(dealer_hand)
        player_score = calculate_bj_score(game['player_hand'])
        if dealer_score > 21: await self.end_game(interaction, "Dealer bị Quắc!", game['bet']) # Thắng 1:1
        elif dealer_score > player_score: await self.end_game(interaction, "Dealer thắng!", -game['bet'])
        elif player_score > dealer_score: await self.end_game(interaction, "Bạn thắng!", game['bet']) # Thắng 1:1
        else: await self.end_game(interaction, "Hòa!", 0) # Hòa (Push)
    @ui.button(label="Gấp đôi (Double)", style=discord.ButtonStyle.success, emoji="✖️2")
    async def double(self, interaction: discord.Interaction, button: ui.Button):
        if self.author_id not in bot.blackjack_games or bot.blackjack_games[self.author_id] != self.game: return
        game = self.game; user_id = self.author_id; user_data = get_user_data(user_id)
        if not user_data or user_data.get('balance', 0) < game['bet'] * 2: await interaction.response.send_message("Bạn không đủ tiền để Gấp đôi!", ephemeral=True); return
        if not game['deck']: await interaction.response.send_message("Hết bài để rút!", ephemeral=True); return # Check hết bài

        game['bet'] *= 2; game['player_hand'].append(game['deck'].pop()); player_score = calculate_bj_score(game['player_hand'])
        embed = game['embed']; embed.set_field_at(1, name=f"Bài của bạn ({player_score})", value=hand_to_string(game['player_hand']), inline=False)
        embed.set_footer(text=f"ĐÃ GẤP ĐÔI! Cược: {game['bet']:,} 🪙")
        if player_score > 21: await self.end_game(interaction, "Bạn bị Quắc!", -game['bet']) # Thua tiền cược gấp đôi
        else: await self.stand(interaction, button) # Tự động dằn sau khi double

@bot.slash_command(name="blackjack", description="Chơi Xì Dách (Blackjack) với bot.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược")
@global_rate_limit()
@is_user_not_in_game()
async def blackjack_slash(interaction: discord.Interaction, bet_amount: int):
    await interaction.response.defer()
    user_id = interaction.user.id; user_data = get_user_data(user_id)
    if not user_data: await interaction.followup.send("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)
    if bet_amount <= 0: await interaction.followup.send('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.followup.send(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return

    deck = create_deck(use_bj_ranks=True); player_hand = [deck.pop(), deck.pop()]; dealer_hand = [deck.pop(), deck.pop()]
    player_score = calculate_bj_score(player_hand); dealer_score_show_one = dealer_hand[0]['value'] if dealer_hand[0]['rank'] != 'A' else 11 # Điểm lá đầu của dealer
    embed = discord.Embed(title="🃏 Xì Dách 🃏", description="Chọn hành động của bạn.", color=discord.Color.blue())
    embed.add_field(name=f"Bài Dealer ({dealer_score_show_one if dealer_score_show_one <= 10 else 'A'})", value=f"**{dealer_hand[0]['rank']}{dealer_hand[0]['suit']}** | **[ ? ]**", inline=False) # Hiện điểm lá đầu
    embed.add_field(name=f"Bài của bạn ({player_score})", value=hand_to_string(player_hand), inline=False)
    embed.set_footer(text=f"Tiền cược: {bet_amount:,} 🪙");

    # Tạo View và kiểm tra Blackjack ban đầu
    game_state = {'bet': bet_amount, 'deck': deck, 'player_hand': player_hand, 'dealer_hand': dealer_hand, 'message': None, 'embed': embed} # message sẽ được set sau
    view = BlackjackView(user_id, game_state)

    if player_score == 21: # Blackjack!
        winnings = int(bet_amount * 1.5); payout = winnings
        new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)
        embed.title = "🃏 BLACKJACK! 🃏"; embed.description = f"🎉 **Bạn thắng {winnings:,} 🪙!**\nSố dư mới: **{new_balance:,}** 🪙."
        embed.color = discord.Color.gold(); dealer_final_score = calculate_bj_score(dealer_hand); embed.set_field_at(0, name=f"Bài Dealer ({dealer_final_score})", value=hand_to_string(dealer_hand), inline=False)
        for item in view.children: item.disabled = True
        await interaction.followup.send(embed=embed, view=view)
    else: # Game tiếp tục bình thường
        # Vô hiệu hóa nút Double nếu không đủ tiền
        if balance < bet_amount * 2:
            view.children[2].disabled = True
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        game_state['message'] = message
        bot.blackjack_games[user_id] = game_state # Lưu state sau khi gửi message

# --- MINES (DÒ MÌN) ---
def combinations(n, k):
    if k < 0 or k > n: return 0
    if k == 0 or k == n: return 1
    if k > n // 2: k = n - k
    # Tối ưu hóa tính toán tổ hợp
    res = 1
    for i in range(k):
        res = res * (n - i) // (i + 1)
    return res

def calculate_mines_payout(gems_revealed, total_bombs):
    total_cells = 25
    if gems_revealed <= 0: return 1.0
    # Đảm bảo gems_revealed không vượt quá số kim cương có thể có
    max_gems = total_cells - total_bombs
    if gems_revealed > max_gems: return calculate_mines_payout(max_gems, total_bombs) # Tính theo max gems nếu lỡ >

    numerator = combinations(total_cells, gems_revealed)
    denominator = combinations(max_gems, gems_revealed)
    if denominator == 0: return 1.0 # Tránh chia cho 0
    payout_multiplier = (numerator / denominator) * 0.95 # 95% House Edge
    # Giới hạn payout tối đa để tránh số quá lớn (ví dụ: 10000x)
    return min(payout_multiplier, 10000.0)


class MinesButton(ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=x); self.x = x; self.y = y
    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in bot.mines_games: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        game_view = self.view
        if user_id != game_view.author_id: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return

        game = bot.mines_games[user_id]; index = self.x * 5 + self.y
        if game['grid'][index] == '💣':
            self.style = discord.ButtonStyle.danger; self.label = '💣'; self.disabled = True
            payout = -game['bet']; new_balance = update_balance(user_id, payout)
            update_profile_stats(user_id, game['bet'], payout)
            embed = game['embed']; embed.title = "💥 BÙM! BẠN ĐÃ THUA! 💥"; embed.description = f"Bạn lật trúng bom!\nBạn mất **{game['bet']:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."
            embed.color = discord.Color.red(); game_view.stop_game(show_solution=True)
            await interaction.response.edit_message(embed=embed, view=game_view); bot.mines_games.pop(user_id, None)
        else: # Trúng kim cương
            self.style = discord.ButtonStyle.success; self.label = '💎'; self.disabled = True; game['revealed_count'] += 1
            payout_multiplier = calculate_mines_payout(game['revealed_count'], game['bomb_count']); game['current_payout'] = payout_multiplier
            winnings = int(game['bet'] * (payout_multiplier - 1)); embed = game['embed']
            embed.description = f"Tìm thấy **{game['revealed_count']}** 💎. Lật tiếp hoặc Rút tiền!"
            embed.set_field_at(1, name="Hệ số Hiện Tại", value=f"{payout_multiplier:.2f}x")
            embed.set_field_at(2, name="Tiền thắng (nếu rút)", value=f"{winnings:,} 🪙")
            game_view.children[-1].label = f"Rút tiền ({payout_multiplier:.2f}x | {winnings:,} 🪙)" # Cập nhật nút cashout

            if game['revealed_count'] == (25 - game['bomb_count']): # Thắng tuyệt đối
                net_gain = winnings # Thắng phần lời
                new_balance = update_balance(user_id, net_gain) # Cộng phần lời
                update_profile_stats(user_id, game['bet'], net_gain)
                embed.title = "🎉 BẠN ĐÃ THẮNG TUYỆT ĐỐI! 🎉"; embed.description = f"Bạn đã tìm thấy tất cả {game['revealed_count']} 💎!\nBạn thắng **{winnings:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."
                embed.color = discord.Color.gold(); game_view.stop_game(show_solution=False)
                await interaction.response.edit_message(embed=embed, view=game_view); bot.mines_games.pop(user_id, None)
            else: # Tiếp tục chơi
                await interaction.response.edit_message(embed=embed, view=game_view)

class MinesCashoutButton(ui.Button):
    def __init__(self): super().__init__(style=discord.ButtonStyle.primary, label="Rút tiền (1.00x)", row=4)
    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in bot.mines_games: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        game_view = self.view
        if user_id != game_view.author_id: await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        game = bot.mines_games[user_id]
        if game['revealed_count'] == 0: await interaction.response.send_message("Bạn phải lật ít nhất 1 ô!", ephemeral=True); return

        winnings = int(game['bet'] * (game['current_payout'] - 1)); net_gain = winnings
        new_balance = update_balance(user_id, net_gain) # Chỉ cộng phần lời
        update_profile_stats(user_id, game['bet'], net_gain)
        embed = game['embed']; embed.title = "✅ RÚT TIỀN THÀNH CÔNG ✅"
        embed.description = f"Bạn rút tiền tại **{game['current_payout']:.2f}x**.\nBạn thắng **{winnings:,}** 🪙.\nSố dư mới: **{new_balance:,}** 🪙."
        embed.color = discord.Color.green(); game_view.stop_game(show_solution=True)
        await interaction.response.edit_message(embed=embed, view=game_view); bot.mines_games.pop(user_id, None)

class MinesView(ui.View):
    def __init__(self, author_id, game):
        super().__init__(timeout=300.0); self.author_id = author_id; self.game = game
        button_index = 0
        for x in range(5):
            for y in range(5):
                 # Hàng cuối cùng (row 4) chỉ có 4 nút + cashout
                 if x == 4 and y == 4:
                      self.add_item(MinesCashoutButton())
                 else:
                      self.add_item(MinesButton(x, y))
                 button_index += 1

    async def on_timeout(self):
        if self.author_id in bot.mines_games and bot.mines_games[self.author_id] == self.game:
            game = bot.mines_games.pop(self.author_id); embed = game['embed']
            embed.title = "💣 Dò Mìn (Hết giờ) 💣"; embed.description = "Bạn đã không phản hồi. Ván game bị hủy. Bạn không mất tiền cược." # Không mất tiền nếu timeout
            embed.color = discord.Color.dark_grey(); self.stop_game(show_solution=False)
            try: await game['message'].edit(embed=embed, view=self)
            except discord.NotFound: pass

    def stop_game(self, show_solution: bool):
        game = self.game; button_index = 0
        for item in self.children:
            item.disabled = True
            if isinstance(item, MinesButton):
                grid_index = item.x * 5 + item.y
                if show_solution:
                    if game['grid'][grid_index] == '💣': item.label = '💣'; item.style = discord.ButtonStyle.danger
                    elif game['grid'][grid_index] == '💎': item.label = '💎'; item.style = discord.ButtonStyle.secondary if item.style != discord.ButtonStyle.success else item.style

@bot.slash_command(name="mines", description="Chơi Dò Mìn.")
@app_commands.describe(bet_amount="Số tiền bạn muốn cược", bomb_count="Số lượng bom (1-24)")
@global_rate_limit()
@is_user_not_in_game()
async def mines_slash(interaction: discord.Interaction, bet_amount: int, bomb_count: app_commands.Range[int, 1, 24]):
    await interaction.response.defer()
    user_id = interaction.user.id; user_data = get_user_data(user_id)
    if not user_data: await interaction.followup.send("Lỗi lấy dữ liệu user.", ephemeral=True); return
    balance = user_data.get('balance', 0)
    if bet_amount <= 0: await interaction.followup.send('Số tiền cược phải lớn hơn 0!', ephemeral=True); return
    if balance < bet_amount: await interaction.followup.send(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.', ephemeral=True); return
    # Không trừ tiền ngay, chỉ trừ khi thua hoặc cộng lời khi thắng/cashout

    grid = ['💣'] * bomb_count + ['💎'] * (25 - bomb_count); random.shuffle(grid)
    embed = discord.Embed(title=f"💣 Dò Mìn ({bomb_count} bom) 💣", description="Lật các ô để tìm kim cương 💎. Đừng trúng bom 💣!", color=discord.Color.blue())
    embed.add_field(name="Tiền cược", value=f"**{bet_amount:,}** 🪙")
    embed.add_field(name="Hệ số Hiện Tại", value="1.00x")
    embed.add_field(name="Tiền thắng (nếu rút)", value="0 🪙")
    game_state = {'bet': bet_amount, 'bomb_count': bomb_count, 'grid': grid, 'revealed_count': 0, 'current_payout': 1.0, 'message': None, 'embed': embed}
    view = MinesView(user_id, game_state); message = await interaction.followup.send(embed=embed, view=view, wait=True)
    game_state['message'] = message; bot.mines_games[user_id] = game_state



# --- XỔ SỐ (LOTTERY) - SLASH COMMANDS & TASK ---
# ... (Dán code lottery_group và lottery_draw_task đã được chuyển đổi) ...

# --- ĐOÁN SỐ (GUESS THE NUMBER) - SLASH COMMANDS ---
# ... (Dán code Class GuessTheNumberGame và guess_group đã được chuyển đổi) ...

# --- GAME GIAO DIỆN UI (BLACKJACK & MINES) - SLASH COMMANDS ---
# ... (Dán code Blackjack và Mines đã được chuyển đổi sang Slash Commands) ...

# --- VÒNG QUAY MAY MẮN (SPIN THE WHEEL) - SLASH COMMAND ---
# ... (Dán code Spin the Wheel đã được chuyển đổi sang Slash Commands) ...

# --- CHẠY BOT ---
if __name__ == "__main__":
    if TOKEN:
        keep_alive();
        try: bot.run(TOKEN)
        except Exception as e: print(f"Lỗi khi chạy bot: {e}")
    else:
        print("LỖI: Không tìm thấy DISCORD_TOKEN")
