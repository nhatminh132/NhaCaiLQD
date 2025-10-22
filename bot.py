# -*- coding: utf-8 -*-
import discord
from discord.ext import commands, tasks
from discord import ui
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

# Cài đặt Bot Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- BIẾN TOÀN CỤC CHO GAME ---
game_message = None # Tin nhắn game Tài Xỉu
game_channel_id = None # Kênh game Tài Xỉu
current_bets = {} # Cược ván Tài Xỉu hiện tại
bot.blackjack_games = {} # Lưu các ván Blackjack
bot.mines_games = {} # Lưu các ván Dò Mìn
bot.users_in_animation = set() # Dùng để khóa lệnh khi game có hiệu ứng
bot.guess_the_number_game = None # Lưu state game Đoán Số

# --- ĐỊNH NGHĨA HẰNG SỐ ---
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24
ADMIN_ROLE = "Bot Admin"
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh') # Múi giờ VN
LOTTERY_DRAW_TIME = time(18, 0, 0, tzinfo=VIETNAM_TZ) # 18:00 VN hàng ngày
LOTTERY_TICKET_PRICE = 100 # Giá vé số

# (Các hằng số game khác giữ nguyên)
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
BAU_CUA_FACES = {'bầu': 'Bầu 🍐', 'bau': 'Bầu 🍐', '🍐': 'Bầu 🍐', 'cua': 'Cua 🦀', '🦀': 'Cua 🦀', 'tôm': 'Tôm 🦐', 'tom': 'Tôm 🦐', '🦐': 'Tôm 🦐', 'cá': 'Cá 🐟', 'ca': 'Cá 🐟', '🐟': 'Cá 🐟', 'gà': 'Gà 🐓', 'ga': 'Gà 🐓', '🐓': 'Gà 🐓', 'nai': 'Nai 🦌', '🦌': 'Nai 🦌'}
BAU_CUA_LIST = ['Bầu 🍐', 'Cua 🦀', 'Tôm 🦐', 'Cá 🐟', 'Gà 🐓', 'Nai 🦌']
NUM_HORSES = 6; RACE_LENGTH = 20
SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL, SLOT_WEIGHTS, SLOT_PAYOUTS = [], [], {}
for (symbol, weight, payout) in SLOT_SYMBOLS: SLOT_WHEEL.append(symbol); SLOT_WEIGHTS.append(weight); SLOT_PAYOUTS[symbol] = payout
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
CARD_RANKS = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11} # A=11 (hoặc 1), JQK=10 trong Blackjack & Baccarat

# --- CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)

# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
def get_user_data(user_id: int) -> typing.Dict:
    try:
        response = supabase.table('profiles').select('*').eq('user_id', user_id).single().execute()
        return response.data
    except Exception as e:
        # User chưa tồn tại, tạo mới
        if "JSON object requested" in str(e): # Lỗi phổ biến khi .single() không tìm thấy
             try:
                 insert_response = supabase.table('profiles').insert({'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': [], 'total_bet': 0, 'total_won': 0, 'games_played': 0}).execute()
                 return insert_response.data[0]
             except Exception as e2:
                 print(f"Lỗi khi tạo user mới {user_id}: {e2}")
                 return None
        else:
             print(f"Lỗi khi get_user_data cho {user_id}: {e}")
             return None

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    try:
        response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
        return response.data
    except Exception as e:
        print(f"Lỗi khi update_balance cho {user_id}: {e}")
        # User có thể chưa tồn tại, thử tạo
        user_data = get_user_data(user_id)
        if user_data: # Nếu tạo thành công, thử lại
             try:
                 response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
                 return response.data
             except Exception as e2: print(f"Lỗi lần 2 khi update_balance: {e2}")
        return None

def update_profile_stats(user_id: int, bet_amount: int, net_gain: int): # Sửa winnings thành net_gain
    """Cập nhật total_bet, total_won, games_played."""
    try:
        current_stats = supabase.table('profiles').select('total_bet', 'total_won', 'games_played').eq('user_id', user_id).single().execute().data
        if not current_stats: return

        new_total_bet = current_stats.get('total_bet', 0) + bet_amount
        # Total won chỉ cộng phần lời (nếu net_gain > 0)
        new_total_won = current_stats.get('total_won', 0) + max(0, net_gain)
        new_games_played = current_stats.get('games_played', 0) + 1

        supabase.table('profiles').update({
            'total_bet': new_total_bet,
            'total_won': new_total_won,
            'games_played': new_games_played
        }).eq('user_id', user_id).execute()
    except Exception as e:
        print(f"Lỗi khi update_profile_stats cho {user_id}: {e}")

def get_jackpot_pool(game_name: str):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        data = supabase.table(table_name).select('pool_amount').eq('game_name', game_name).single().execute().data
        return data['pool_amount'] if data else 0
    except Exception as e:
        print(f"Lỗi khi lấy jackpot {game_name}: {e}"); return 0

def update_jackpot_pool(game_name: str, amount: int):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        current_pool = get_jackpot_pool(game_name)
        new_pool = max(0, current_pool + amount)
        supabase.table(table_name).update({'pool_amount': new_pool}).eq('game_name', game_name).execute()
        return new_pool
    except Exception as e:
        print(f"Lỗi khi cập nhật jackpot {game_name}: {e}"); return get_jackpot_pool(game_name)

def get_taixiu_history():
    try:
        data = supabase.table('jackpot').select('history').eq('game_name', 'taixiu').single().execute().data
        return data['history'][-10:] if data and data['history'] else []
    except Exception as e: print(f"Loi khi lay history taixiu: {e}"); return []

# --- HÀM KIỂM TRA & SỰ KIỆN BOT ---
@bot.before_invoke
async def global_check_before_command(ctx):
    if ctx.command and ctx.command.name == 'help': return # Sửa lỗi check help
    bucket = global_cooldown.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after: raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.default)

@bot.event
async def on_ready():
    bot.add_view(TaiXiuGameView())
    lottery_draw_task.start()
    print(f'Bot {bot.user.name} đã sẵn sàng!'); print('------')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        seconds = error.retry_after; await ctx.send(f"⏳ Bot đang xử lý quá nhiều yêu cầu! Vui lòng thử lại sau **{seconds:.1f} giây**.", delete_after=5)
    elif isinstance(error, commands.MissingRole):
        await ctx.send(f"Rất tiếc {ctx.author.mention}, bạn không có quyền dùng lệnh này. Cần role `{ADMIN_ROLE}`.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Cú pháp sai! Gõ `!help` để xem hướng dẫn lệnh `{ctx.command.name}`.')
    elif isinstance(error, commands.BadArgument):
        if ctx.command and ctx.command.name in ['admin_give', 'admin_set', 'chuyenxu', 'profile', 'admin_view', 'admin_resetdaily']: await ctx.send('Không tìm thấy người dùng đó hoặc số tiền không hợp lệ.')
        elif ctx.command and ctx.command.name == 'lottery_buy': await ctx.send('Vui lòng nhập 6 số hợp lệ (1-45).')
        elif ctx.command and ctx.command.name == 'admin_announce': await ctx.send('Không tìm thấy kênh đó.')
        else: await ctx.send('Số tiền cược hoặc số đoán/số ngựa/số bom không hợp lệ.')
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"⏳ {ctx.author.mention}, bạn đang có một trò chơi khác đang chạy. Vui lòng chờ cho nó kết thúc!", ephemeral=True, delete_after=5)
    else:
        print(f"Lỗi không xác định từ lệnh '{ctx.command.name if ctx.command else 'Unknown'}': {error}")
        await ctx.send('Đã xảy ra lỗi. Vui lòng thử lại sau.')

def is_user_in_game(ctx):
    user_id = ctx.author.id
    if user_id in bot.blackjack_games: return False
    if user_id in bot.mines_games: return False
    if bot.guess_the_number_game and user_id in bot.guess_the_number_game.participants: return False # Check game đoán số
    if user_id in bot.users_in_animation: return False
    return True

# --- LỆNH !HELP ---
@bot.command(name='help')
async def custom_help(ctx):
    embed = discord.Embed(title="Trợ giúp Bot Casino 🎰", color=discord.Color.gold())
    embed.add_field(name="🪙 Lệnh Cơ bản", value="`!help`\n`!kiemtra` (`!bal`, `!sodu`)\n`!daily`\n`!code <mã>`\n`!chuyenxu @user <số_tiền>`\n`!bangxephang` (`!top`)\n`!profile [@user]` - Xem hồ sơ", inline=False)
    embed.add_field(name="🎲 Trò chơi (Gõ lệnh)", value="`!slots <số_tiền>` - Chơi máy xèng.\n`!hilo <số_tiền> <cao/thấp>` - Đoán lá bài tiếp theo.\n`!tungxu <số_tiền> <sấp/ngửa>` - Cược 50/50.\n`!xucxac <số_tiền> <số_đoán>` - Đoán số (1-6), thắng 1 ăn 5.\n`!baucua <số_tiền> <linh_vật>` - Cược Bầu Cua Tôm Cá.\n`!duangua <số_tiền> <số_ngựa>` - Cược đua ngựa (1-6), thắng 1 ăn 4.\n`!quay <số_tiền> <loại_cược>` - Chơi Roulette.\n`!baccarat <số_tiền> <player/banker/tie>`\n`!lottery buy <s1>..<s6>` - Mua vé số (1-45)\n`!lottery result` - Xem kết quả XS\n`!guessthenumber start <số_tiền>` - Bắt đầu đoán số\n`!guess <số>` - Đoán số (1-100)", inline=False)
    embed.add_field(name="🃏 Trò chơi (Giao diện UI)", value="`!blackjack <số_tiền>` (`!bj`)\n`!mines <số_tiền> <số_bom>`", inline=False)
    embed.add_field(name="🎮 Game 24/7 (Dùng Nút)", value="Tìm kênh **Tài Xỉu** và dùng Nút để cược.", inline=False)
    embed.add_field(name="🛠️ Lệnh Admin", value="`!admin_give @user <số_tiền>`\n`!admin_set @user <số_tiền>`\n`!admin_createcode <code> <reward>`\n`!admin_deletecode <code>`\n`!start_taixiu`\n`!stop_taixiu`\n`!admin_view @user` - Xem thông tin user\n`!admin_resetdaily @user` - Reset daily\n`!admin_announce #channel <nội dung>`", inline=False)
    embed.set_footer(text="Chúc bạn may mắn!"); await ctx.send(embed=embed)

# --- LỆNH CƠ BẢN VÀ XÃ HỘI ---
# (!kiemtra, !daily, !code, !bangxephang, !chuyenxu, !profile giữ nguyên)
# ... (Dán code các lệnh này từ phiên bản trước) ...

# --- LỆNH ADMIN ---
# (!admin_give, !admin_set, !admin_createcode, !admin_deletecode, !admin_view, !admin_resetdaily, !admin_announce giữ nguyên)
# ... (Dán code các lệnh này từ phiên bản trước) ...

# --- GAME 24/7: TÀI XỈU (UI) ---
# (Toàn bộ logic game Tài Xỉu 24/7 giữ nguyên, bao gồm BetModal, TaiXiuGameView, get_bet_totals, tai_xiu_game_loop, start/stop_taixiu)
# ... (Dán code game Tài Xỉu UI từ phiên bản trước) ...

# --- GAME THEO LỆNH (CÓ HIỆU ỨNG VÀ KHÓA) ---
# (!slots, !hilo, !tungxu, !xucxac, !baucua, !duangua, !quay giữ nguyên, chỉ cần thêm update_profile_stats)

@bot.command(name='slots', aliases=['slot'])
@commands.check(is_user_in_game)
async def slots(ctx, bet_amount: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game slots với hiệu ứng và jackpot)
        net_gain = winnings if is_jackpot else (winnings - jackpot_contrib)
        update_profile_stats(user_id, bet_amount, net_gain) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='hilo', aliases=['caothap'])
@commands.check(is_user_in_game)
async def hilo(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game hilo với hiệu ứng)
        payout = bet_amount if is_win else -bet_amount
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='tungxu', aliases=['coinflip'])
@commands.check(is_user_in_game)
async def coinflip(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game tungxu với hiệu ứng)
        payout = bet_amount if is_win else -bet_amount # is_win được xác định trong logic
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='xucxac', aliases=['dice'])
@commands.check(is_user_in_game)
async def dice_roll(ctx, bet_amount: int, guess: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game xucxac với hiệu ứng)
        is_win = (guess == result) # result được xác định trong logic
        payout = winnings if is_win else -bet_amount
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='baucua', aliases=['bc'])
@commands.check(is_user_in_game)
async def bau_cua(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game baucua với hiệu ứng)
        is_win = (hits > 0) # hits được xác định trong logic
        payout = winnings if is_win else -bet_amount
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='duangua', aliases=['race'])
@commands.check(is_user_in_game)
async def dua_ngua(ctx, bet_amount: int, horse_number: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game duangua với hiệu ứng)
        payout = winnings if is_win else -bet_amount # is_win được xác định trong logic
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='quay', aliases=['roulette'])
@commands.check(is_user_in_game)
async def roulette(ctx, bet_amount: int, bet_type: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game roulette với hiệu ứng và cược phức tạp)
        payout = winnings if is_win else -bet_amount # is_win được xác định trong logic
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

# --- GAME MỚI THEO LỆNH ---
# (!baccarat, !lottery group, !guessthenumber group giữ nguyên)
# ... (Dán code các game này từ phiên bản trước) ...

# --- GAME GIAO DIỆN UI (BLACKJACK & MINES) ---
# (Toàn bộ code Blackjack và Mines giữ nguyên, bao gồm các Class View, Button và lệnh chính)
# ... (Dán code game Blackjack UI từ phiên bản trước) ...
# ... (Dán code game Mines UI từ phiên bản trước) ...

# --- XỔ SỐ TASK ---
# (Task lottery_draw_task giữ nguyên)
@tasks.loop(time=LOTTERY_DRAW_TIME)
async def lottery_draw_task():
     # ... (code như cũ)
     pass


# --- CHẠY BOT ---
if TOKEN:
    keep_alive(); bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN")
