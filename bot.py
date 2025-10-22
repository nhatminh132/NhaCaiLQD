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
