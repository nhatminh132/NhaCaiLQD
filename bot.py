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

# Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
# Cược Roulette phức tạp (Payout rate)
ROULETTE_PAYOUTS = {
    'single': 35, 'split': 17, 'street': 11, 'corner': 8, 'sixline': 5,
    'dozen': 2, 'column': 2, # Dozen/Column thực ra là 1 ăn 2
    'color': 1, 'evenodd': 1, 'half': 1 # Các cược 1 ăn 1
}

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


# --- CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)

# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
def get_user_data(user_id: int) -> typing.Dict:
    try:
        response = supabase.table('profiles').select('*').eq('user_id', user_id).single().execute()
        # Kiểm tra xem các cột stats đã tồn tại chưa, nếu chưa thì thêm giá trị mặc định
        data = response.data
        if 'total_bet' not in data: data['total_bet'] = 0
        if 'total_won' not in data: data['total_won'] = 0
        if 'games_played' not in data: data['games_played'] = 0
        return data
    except Exception as e:
        if "JSON object requested" in str(e): # User chưa tồn tại, tạo mới
             try:
                 insert_response = supabase.table('profiles').insert({'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': [], 'total_bet': 0, 'total_won': 0, 'games_played': 0}).execute()
                 return insert_response.data[0]
             except Exception as e2: print(f"Lỗi khi tạo user mới {user_id}: {e2}"); return None
        else: print(f"Lỗi khi get_user_data cho {user_id}: {e}"); return None

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    try:
        response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
        return response.data
    except Exception as e:
        print(f"Lỗi khi update_balance cho {user_id}: {e}")
        user_data = get_user_data(user_id) # Thử tạo/lấy lại user
        if user_data:
             try:
                 response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
                 return response.data
             except Exception as e2: print(f"Lỗi lần 2 khi update_balance: {e2}")
        return None

def update_profile_stats(user_id: int, bet_amount: int, net_gain: int):
    try:
        current_stats = supabase.table('profiles').select('total_bet', 'total_won', 'games_played').eq('user_id', user_id).single().execute().data
        if not current_stats: return # User không tồn tại (đã được xử lý ở get_user_data nhưng check lại cho chắc)

        # Sử dụng .get() với giá trị mặc định 0 để tránh lỗi nếu cột chưa có
        new_total_bet = current_stats.get('total_bet', 0) + bet_amount
        new_total_won = current_stats.get('total_won', 0) + max(0, net_gain) # Chỉ cộng phần lời
        new_games_played = current_stats.get('games_played', 0) + 1

        supabase.table('profiles').update({
            'total_bet': new_total_bet,
            'total_won': new_total_won,
            'games_played': new_games_played
        }).eq('user_id', user_id).execute()
    except Exception as e: print(f"Lỗi khi update_profile_stats cho {user_id}: {e}")

def get_jackpot_pool(game_name: str):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        data = supabase.table(table_name).select('pool_amount').eq('game_name', game_name).single().execute().data
        return data['pool_amount'] if data else 0
    except Exception as e: print(f"Lỗi khi lấy jackpot {game_name}: {e}"); return 0

def update_jackpot_pool(game_name: str, amount: int):
    try:
        table_name = 'jackpot' if game_name == 'taixiu' else 'progressive_jackpot'
        # Sử dụng phương pháp an toàn hơn để cập nhật (atomic increment) nếu Supabase hỗ trợ
        # Tạm thời vẫn dùng đọc-ghi
        current_pool = get_jackpot_pool(game_name)
        new_pool = max(0, current_pool + amount)
        supabase.table(table_name).update({'pool_amount': new_pool}).eq('game_name', game_name).execute()
        return new_pool
    except Exception as e: print(f"Lỗi khi cập nhật jackpot {game_name}: {e}"); return get_jackpot_pool(game_name)

def get_taixiu_history():
    try:
        data = supabase.table('jackpot').select('history').eq('game_name', 'taixiu').single().execute().data
        return data.get('history', [])[-10:] # Dùng get để an toàn hơn
    except Exception as e: print(f"Loi khi lay history taixiu: {e}"); return []

# --- HÀM KIỂM TRA & SỰ KIỆN BOT ---
@bot.before_invoke
async def global_check_before_command(ctx):
    command = ctx.command
    if command and command.name == 'help': return
    bucket = global_cooldown.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after: raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.default)

@bot.event
async def on_ready():
    bot.add_view(TaiXiuGameView()) # Đăng ký view Tài Xỉu
    # Đăng ký các view khác nếu cần (ví dụ Blackjack, Mines - nhưng chúng dùng timeout nên không cần thiết)
    lottery_draw_task.start()
    print(f'Bot {bot.user.name} đã sẵn sàng!')
    print('------')

@bot.event
async def on_command_error(ctx, error):
    command_name = ctx.command.name if ctx.command else "Unknown"
    if isinstance(error, commands.CommandOnCooldown):
        seconds = error.retry_after; await ctx.send(f"⏳ Bot đang xử lý quá nhiều yêu cầu! Vui lòng thử lại sau **{seconds:.1f} giây**.", delete_after=5)
    elif isinstance(error, commands.MissingRole):
        await ctx.send(f"Rất tiếc {ctx.author.mention}, bạn không có quyền dùng lệnh này. Cần role `{ADMIN_ROLE}`.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Cú pháp sai! Gõ `!help` để xem hướng dẫn lệnh `{command_name}`.')
    elif isinstance(error, commands.BadArgument):
        if command_name in ['admin_give', 'admin_set', 'chuyenxu', 'profile', 'admin_view', 'admin_resetdaily']: await ctx.send('Không tìm thấy người dùng đó hoặc số tiền không hợp lệ.')
        elif command_name == 'lottery_buy': await ctx.send('Vui lòng nhập 6 số hợp lệ (1-45).')
        elif command_name == 'admin_announce': await ctx.send('Không tìm thấy kênh đó.')
        else: await ctx.send('Số tiền cược hoặc số đoán/số ngựa/số bom/lựa chọn không hợp lệ.')
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"⏳ {ctx.author.mention}, bạn đang có một trò chơi khác đang chạy. Vui lòng chờ cho nó kết thúc!", ephemeral=True, delete_after=5)
    # Xử lý lỗi cụ thể cho Roulette cược phức tạp
    elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, ValueError) and "Invalid Roulette bet type" in str(error.original):
         await ctx.send(f"Loại cược Roulette không hợp lệ: `{ctx.message.content.split(' ')[-1]}`. Gõ `!help` xem ví dụ.")
    else:
        print(f"Lỗi không xác định từ lệnh '{command_name}': {error}")
        await ctx.send('Đã xảy ra lỗi. Vui lòng thử lại sau.')

def is_user_in_game(ctx):
    user_id = ctx.author.id
    if user_id in bot.blackjack_games: return False
    if user_id in bot.mines_games: return False
    if bot.guess_the_number_game and user_id in bot.guess_the_number_game.participants: return False
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
@bot.command(name='kiemtra', aliases=['balance', 'bal', 'sodu'])
async def balance_check(ctx):
    user_data = get_user_data(ctx.author.id); await ctx.send(f'🪙 {ctx.author.mention}, bạn đang có **{user_data.get("balance", 0):,}** token.' if user_data else 'Đã xảy ra lỗi khi lấy số dư của bạn.')
@bot.command(name='daily')
async def daily_reward(ctx):
    user_id = ctx.author.id; user_data = get_user_data(user_id)
    if not user_data: await ctx.send("Lỗi lấy dữ liệu user."); return
    if user_data.get('last_daily'):
        try: last_daily_time = datetime.fromisoformat(user_data['last_daily']); cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        except: last_daily_time = None
        if last_daily_time and datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc); hours_left = int(time_left.total_seconds() // 3600); minutes_left = int((time_left.total_seconds() % 3600) // 60)
            await ctx.send(f'{ctx.author.mention}, bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.'); return
    new_balance = update_balance(user_id, DAILY_REWARD)
    if new_balance is None: await ctx.send("Lỗi cập nhật số dư!"); return
    try: supabase.table('profiles').update({'last_daily': datetime.now(timezone.utc).isoformat()}).eq('user_id', user_id).execute(); await ctx.send(f'🎉 {ctx.author.mention}, bạn đã nhận được **{DAILY_REWARD}** token! Số dư mới: **{new_balance:,}** 🪙.')
    except Exception as e: await ctx.send(f'Đã xảy ra lỗi khi cập nhật thời gian: {e}')
@bot.command(name='code')
async def redeem_code(ctx, code_to_redeem: str):
    user_id = ctx.author.id; user_data = get_user_data(user_id)
    if not user_data: await ctx.send("Lỗi lấy dữ liệu user."); return
    code_to_redeem = code_to_redeem.upper()
    try: code_response = supabase.table('gift_codes').select('*').eq('code', code_to_redeem).execute()
    except Exception as e: await ctx.send(f'Lỗi khi kiểm tra code: {e}'); return
    if not code_response.data: await ctx.send(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.'); return
    if code_to_redeem in user_data.get('used_codes', []): await ctx.send(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.'); return
    reward = code_response.data[0]['reward']; new_balance = update_balance(user_id, reward)
    if new_balance is None: await ctx.send("Lỗi cập nhật số dư!"); return
    try: new_code_list = user_data.get('used_codes', []) + [code_to_redeem]; supabase.table('profiles').update({'used_codes': new_code_list}).eq('user_id', user_id).execute(); await ctx.send(f'🎁 {ctx.author.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward}** token! Số dư mới: **{new_balance:,}** 🪙.')
    except Exception as e: await ctx.send(f'Đã xảy ra lỗi khi cập nhật code đã dùng: {e}')
@bot.command(name='bangxephang', aliases=['top'])
async def leaderboard(ctx, top_n: int = 10):
    if top_n <= 0: top_n = 10
    try:
        response = supabase.table('profiles').select('user_id', 'balance').order('balance', desc=True).limit(top_n).execute()
        if not response.data: await ctx.send('Chưa có ai trong bảng xếp hạng.'); return
        embed = discord.Embed(title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆", color=discord.Color.gold()); rank_count = 1
        for user_data in response.data:
            try: user = await bot.fetch_user(user_data['user_id']) # An toàn hơn
            except discord.NotFound: user = None
            user_name = user.display_name if user else f"User ID {user_data['user_id']}"
            embed.add_field(name=f"#{rank_count}: {user_name}", value=f"**{user_data.get('balance', 0):,}** 🪙", inline=False); rank_count += 1
        await ctx.send(embed=embed)
    except Exception as e: await ctx.send(f'Lỗi khi lấy bảng xếp hạng: {e}')
@bot.command(name='chuyenxu', aliases=['give', 'transfer'])
async def transfer_tokens(ctx, recipient: discord.Member, amount: int):
    sender_id = ctx.author.id; recipient_id = recipient.id
    if sender_id == recipient_id: await ctx.send('Bạn không thể tự chuyển cho chính mình!'); return
    if amount <= 0: await ctx.send('Số tiền chuyển phải lớn hơn 0!'); return
    sender_data = get_user_data(sender_id)
    if not sender_data: await ctx.send("Lỗi lấy dữ liệu người gửi."); return
    if sender_data.get('balance', 0) < amount: await ctx.send(f'Bạn không đủ tiền. Bạn chỉ có **{sender_data.get("balance", 0):,}** 🪙.'); return
    try: update_balance(sender_id, -amount); new_recipient_balance = update_balance(recipient_id, amount); await ctx.send(f'✅ {ctx.author.mention} đã chuyển **{amount:,}** 🪙 cho {recipient.mention}!')
    except Exception as e: await ctx.send(f'Đã xảy ra lỗi trong quá trình chuyển: {e}')
@bot.command(name='profile', aliases=['stats', 'thongke'])
async def profile(ctx, member: typing.Optional[discord.Member]):
    target_user = member or ctx.author; user_data = get_user_data(target_user.id)
    if not user_data: await ctx.send(f"Không tìm thấy dữ liệu cho {target_user.mention}."); return
    balance = user_data.get('balance', 0); total_bet = user_data.get('total_bet', 0); total_won = user_data.get('total_won', 0); games_played = user_data.get('games_played', 0)
    net_profit = total_won - total_bet
    embed = discord.Embed(title=f"📊 Hồ sơ của {target_user.display_name}", color=target_user.color); embed.set_thumbnail(url=target_user.display_avatar.url)
    embed.add_field(name="💰 Số dư", value=f"**{balance:,}** 🪙", inline=True); embed.add_field(name="🎲 Số game đã chơi", value=f"{games_played:,}", inline=True)
    embed.add_field(name="📈 Tổng cược", value=f"{total_bet:,} 🪙", inline=False); embed.add_field(name="🏆 Tổng thắng", value=f"{total_won:,} 🪙", inline=False)
    embed.add_field(name="💹 Lãi/Lỗ ròng", value=f"**{net_profit:,}** 🪙", inline=False)
    await ctx.send(embed=embed)

# --- LỆNH ADMIN ---
@bot.command(name='admin_give')
@commands.has_role(ADMIN_ROLE)
async def admin_give(ctx, member: discord.Member, amount: int):
    if amount == 0: await ctx.send("Số lượng phải khác 0."); return
    user_id = member.id; new_balance = update_balance(user_id, amount)
    if new_balance is None: await ctx.send("Lỗi cập nhật số dư!"); return
    if amount > 0: await ctx.send(f"✅ Đã cộng **{amount:,}** 🪙 cho {member.mention}. Số dư mới: **{new_balance:,}** 🪙.")
    else: await ctx.send(f"✅ Đã trừ **{abs(amount):,}** 🪙 từ {member.mention}. Số dư mới: **{new_balance:,}** 🪙.")
@bot.command(name='admin_set')
@commands.has_role(ADMIN_ROLE)
async def admin_set(ctx, member: discord.Member, amount: int):
    if amount < 0: await ctx.send("Không thể set số dư âm."); return
    try: supabase.rpc('set_balance', {'user_id_input': member.id, 'amount_input': amount}).execute(); await ctx.send(f"✅ Đã set số dư của {member.mention} thành **{amount:,}** 🪙.")
    except Exception as e: await ctx.send(f"Đã xảy ra lỗi khi set balance: {e}")
@bot.command(name='admin_createcode')
@commands.has_role(ADMIN_ROLE)
async def admin_createcode(ctx, code: str, reward: int):
    if reward <= 0: await ctx.send("Phần thưởng phải lớn hơn 0."); return
    code = code.upper()
    try: supabase.table('gift_codes').insert({'code': code, 'reward': reward}).execute(); await ctx.send(f"✅ Đã tạo giftcode `{code}` trị giá **{reward:,}** 🪙.")
    except Exception as e: await ctx.send(f"Lỗi! Code `{code}` có thể đã tồn tại. ({e})")
@bot.command(name='admin_deletecode')
@commands.has_role(ADMIN_ROLE)
async def admin_deletecode(ctx, code: str):
    code = code.upper()
    try: response = supabase.table('gift_codes').delete().eq('code', code).execute()
    except Exception as e: await ctx.send(f"Đã xảy ra lỗi khi xóa code: {e}"); return
    if response.data: await ctx.send(f"✅ Đã xóa thành công giftcode `{code}`.")
    else: await ctx.send(f"Lỗi! Không tìm thấy giftcode nào tên là `{code}`.")
@bot.command(name='admin_view')
@commands.has_role(ADMIN_ROLE)
async def admin_view(ctx, member: discord.Member):
    user_data = get_user_data(member.id)
    if not user_data: await ctx.send("Không tìm thấy user."); return
    embed = discord.Embed(title=f"👀 Xem thông tin: {member.display_name}", color=member.color)
    for key, value in user_data.items():
        if key == 'used_codes' and isinstance(value, list): embed.add_field(name=key, value=f"`{'`, `'.join(value)}`" if value else "Chưa dùng code nào", inline=False)
        elif key == 'last_daily' and value:
             try: dt_object = datetime.fromisoformat(value).astimezone(VIETNAM_TZ); embed.add_field(name=key, value=f"{dt_object.strftime('%Y-%m-%d %H:%M:%S %Z')}", inline=False)
             except: embed.add_field(name=key, value=f"`{value}` (Lỗi format)", inline=False)
        elif isinstance(value, (int, float)): embed.add_field(name=key, value=f"`{value:,}`", inline=False)
        else: embed.add_field(name=key, value=f"`{value}`", inline=False)
    await ctx.send(embed=embed)
@bot.command(name='admin_resetdaily')
@commands.has_role(ADMIN_ROLE)
async def admin_resetdaily(ctx, member: discord.Member):
    try: supabase.table('profiles').update({'last_daily': None}).eq('user_id', member.id).execute(); await ctx.send(f"✅ Đã reset thời gian `!daily` cho {member.mention}.")
    except Exception as e: await ctx.send(f"Lỗi khi reset daily: {e}")
@bot.command(name='admin_announce')
@commands.has_role(ADMIN_ROLE)
async def admin_announce(ctx, channel: discord.TextChannel, *, message: str):
    try: embed = discord.Embed(title="📢 Thông Báo Từ Admin 📢", description=message, color=discord.Color.orange()); embed.set_footer(text=f"Gửi bởi {ctx.author.display_name}"); await channel.send(embed=embed); await ctx.message.add_reaction("✅")
    except Exception as e: await ctx.send(f"Lỗi khi gửi thông báo: {e}")

# --- GAME 24/7: TÀI XỈU (UI) ---
class BetModal(ui.Modal, title="Đặt cược"):
    def __init__(self, bet_type: str):
        super().__init__(); self.bet_type = bet_type
        self.amount_input = ui.TextInput(label=f"Nhập số tiền cược cho [ {bet_type.upper()} ]", placeholder="Ví dụ: 1000", style=discord.TextStyle.short)
        self.add_item(self.amount_input)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try: amount = int(self.amount_input.value)
        except ValueError: await interaction.response.send_message("Số tiền cược phải là một con số!", ephemeral=True); return
        if amount <= 0: await interaction.response.send_message("Số tiền cược phải lớn hơn 0!", ephemeral=True); return
        user_data = get_user_data(user_id)
        if not user_data: await interaction.response.send_message("Lỗi lấy dữ liệu user.", ephemeral=True); return
        if user_data.get('balance', 0) < amount: await interaction.response.send_message(f"Bạn không đủ tiền! Bạn chỉ có {user_data.get('balance', 0):,} 🪙.", ephemeral=True); return
        current_bets[user_id] = {'type': self.bet_type, 'amount': amount}
        await interaction.response.send_message(f"✅ Bạn đã cược **{amount:,}** 🪙 vào cửa **{self.bet_type.upper()}** thành công!", ephemeral=True)
class TaiXiuGameView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="Tài", style=discord.ButtonStyle.secondary, emoji="⚫", custom_id="bet_tai")
    async def bet_tai_button(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(BetModal(bet_type="tài"))
    @ui.button(label="Xỉu", style=discord.ButtonStyle.secondary, emoji="🟣", custom_id="bet_xiu")
    async def bet_xiu_button(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(BetModal(bet_type="xỉu"))
    @ui.button(label="Chẵn", style=discord.ButtonStyle.secondary, emoji="🟡", custom_id="bet_chan")
    async def bet_chan_button(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(BetModal(bet_type="chẵn"))
    @ui.button(label="Lẻ", style=discord.ButtonStyle.secondary, emoji="🔵", custom_id="bet_le")
    async def bet_le_button(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(BetModal(bet_type="lẻ"))
def get_bet_totals():
    totals = {'tài': 0, 'xỉu': 0, 'chẵn': 0, 'lẻ': 0}
    for user_id, bet in current_bets.items(): totals[bet['type']] += bet['amount']
    return totals
@tasks.loop(seconds=60.0)
async def tai_xiu_game_loop():
    global game_message, current_bets
    if not game_channel_id: return
    channel = bot.get_channel(game_channel_id)
    if not channel: print("Lỗi: Không tìm thấy kênh game!"); return
    current_bets = {}; jackpot_pool = get_jackpot_pool('taixiu'); history = get_taixiu_history()
    embed = discord.Embed(title="🎲 PHIÊN TÀI XỈU MỚI 🎲", description="Mời bạn chọn cửa. **Còn 45 giây...**", color=discord.Color.gold())
    embed.add_field(name="Tỉ lệ cược", value="• Tài - Xỉu: **x1.9**\n• Chẵn - Lẻ: **x1.9**\n• *Bộ Ba Đồng Nhất*: Nổ 10% Hũ / Nhà cái ăn", inline=False)
    embed.add_field(name="💰 HŨ TÀI XỈU 💰", value=f"**{jackpot_pool:,}** 🪙", inline=True)
    embed.add_field(name="📈 Soi cầu (gần nhất bên phải)", value=f"`{' | '.join(history)}`" if history else "Chưa có dữ liệu", inline=True)
    embed.add_field(name="Tổng Cược Hiện Tại", value="• Tài: 0 🪙\n• Xỉu: 0 🪙\n• Chẵn: 0 🪙\n• Lẻ: 0 🪙", inline=False)
    embed.set_footer(text="Nhấn nút bên dưới để đặt cược!")
    if game_message:
        try: await game_message.delete()
        except discord.NotFound: pass
    game_message = await channel.send(embed=embed, view=TaiXiuGameView())
    for i in range(4):
        await asyncio.sleep(10)
        totals = get_bet_totals()
        embed.description = f"Mời bạn chọn cửa. **Còn {45 - (i+1)*10} giây...**"
        embed.set_field_at(3, name="Tổng Cược Hiện Tại", value=f"• Tài: {totals['tài']:,} 🪙\n• Xỉu: {totals['xỉu']:,} 🪙\n• Chẵn: {totals['chẵn']:,} 🪙\n• Lẻ: {totals['lẻ']:,} 🪙", inline=False)
        try: await game_message.edit(embed=embed)
        except discord.NotFound: return
    embed.title = "🎲 ĐANG LẮC... 🎲"; embed.description = "Đã khóa cược. Chờ kết quả trong giây lát..."; embed.color = discord.Color.dark_gray()
    await game_message.edit(embed=embed, view=None); await asyncio.sleep(5)
    d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6); total = d1 + d2 + d3
    is_tai, is_xiu, is_chan, is_le, is_triple = (11 <= total <= 17), (4 <= total <= 10), (total % 2 == 0), (total % 2 != 0), (d1 == d2 == d3)
    if is_triple: result_text, result_emoji, history_entry = f"Bộ Ba Đồng Nhất ({total})!", "💣", "Bộ Ba"
    elif is_tai and is_chan: result_text, result_emoji, history_entry = f"TÀI - CHẴN ({total})", "⚫🟡", "Tài Chẵn"
    elif is_tai and is_le: result_text, result_emoji, history_entry = f"TÀI - LẺ ({total})", "⚫🔵", "Tài Lẻ"
    elif is_xiu and is_chan: result_text, result_emoji, history_entry = f"XỈU - CHẴN ({total})", "🟣🟡", "Xỉu Chẵn"
    else: result_text, result_emoji, history_entry = f"XỈU - LẺ ({total})", "🟣🔵", "Xỉu Lẻ"
    history.append(history_entry);
    if len(history) > 10: history.pop(0)
    jackpot_contrib = 0; payout_log = []; triple_jackpot_win = 0; amount_per_player = 0
    if is_triple and len(current_bets) > 0 and jackpot_pool > 0:
        triple_jackpot_win = int(jackpot_pool * 0.10)
        jackpot_contrib -= triple_jackpot_win # Trừ tiền hũ đã nổ
        amount_per_player = triple_jackpot_win // len(current_bets) # Chia đều
        if amount_per_player > 0 : payout_log.append(f"💥 **NỔ HŨ BỘ BA!** {triple_jackpot_win:,} 🪙 được chia!")
        else: triple_jackpot_win = 0 # Không đủ tiền chia thì hủy nổ

    for user_id, bet in current_bets.items():
        bet_type, amount = bet['type'], bet['amount']
        contrib = int(amount * 0.01); jackpot_contrib += contrib; winnings = 0; is_win = False
        user_winnings_from_jackpot = amount_per_player if is_triple else 0
        if not is_triple:
            if (bet_type == 'tài' and is_tai) or (bet_type == 'xỉu' and is_xiu) or (bet_type == 'chẵn' and is_chan) or (bet_type == 'lẻ' and is_le): is_win = True
        if is_win:
            winnings = int(amount * 0.9); net_gain = winnings + user_winnings_from_jackpot
            update_balance(user_id, net_gain); update_profile_stats(user_id, amount, net_gain)
            payout_log.append(f"<@{user_id}> thắng **{winnings:,}** 🪙 (cửa {bet_type}){' + **' + f'{user_winnings_from_jackpot:,}' + '** 🪙 từ hũ!' if user_winnings_from_jackpot > 0 else ''}")
        else:
            loss = amount - contrib; net_gain = -loss + user_winnings_from_jackpot
            update_balance(user_id, net_gain); update_profile_stats(user_id, amount, net_gain)
            if user_winnings_from_jackpot > 0: payout_log.append(f"<@{user_id}> nhận **{user_winnings_from_jackpot:,}** 🪙 từ hũ!")

    new_jackpot = max(0, jackpot_pool + jackpot_contrib)
    supabase.table('jackpot').update({'pool_amount': new_jackpot, 'history': history}).eq('game_name', 'taixiu').execute()
    embed_result = discord.Embed(title=f"{result_emoji} KẾT QUẢ: {result_text} {result_emoji}", color=discord.Color.green() if any(wg > 0 for wg in [winnings, user_winnings_from_jackpot]) else discord.Color.red())
    embed_result.add_field(name="Kết quả xúc xắc", value=f"**{d1} | {d2} | {d3}** (Tổng: **{total}**)", inline=False)
    embed_result.add_field(name="💰 Hũ hiện tại 💰", value=f"**{new_jackpot:,}** 🪙 ({'+' if jackpot_contrib >= 0 else ''}{jackpot_contrib:,})", inline=False)
    if not payout_log: payout_log.append("Không có ai thắng/nhận hũ ván này.")
    embed_result.add_field(name="Người thắng/Nhận Hũ", value="\n".join(payout_log[:15]), inline=False)
    embed_result.set_footer(text="Phiên mới sẽ bắt đầu sau 5 giây...")
    try: await game_message.edit(embed=embed_result, view=None); await asyncio.sleep(5)
    except discord.NotFound: print("Tin nhắn Tài Xỉu không tìm thấy để cập nhật kết quả.")
@tai_xiu_game_loop.before_loop
async def before_taixiu_loop(): await bot.wait_until_ready()
@bot.command(name='start_taixiu')
@commands.has_role(ADMIN_ROLE)
async def start_taixiu(ctx):
    global game_channel_id; game_channel_id = ctx.channel.id
    if not tai_xiu_game_loop.is_running(): tai_xiu_game_loop.start(); await ctx.send(f"✅ Đã bắt đầu Game Tài Xỉu 24/7 tại kênh <#{game_channel_id}>.")
    else: await ctx.send(f"Game đã chạy tại kênh <#{game_channel_id}> rồi.")
@bot.command(name='stop_taixiu')
@commands.has_role(ADMIN_ROLE)
async def stop_taixiu(ctx):
    global game_channel_id
    if tai_xiu_game_loop.is_running(): tai_xiu_game_loop.stop(); game_channel_id = None; await ctx.send("✅ Đã dừng Game Tài Xỉu.")
    else: await ctx.send("Game chưa chạy.")


# --- GAME THEO LỆNH (CÓ HIỆU ỨNG VÀ KHÓA) ---
# ... (Dán toàn bộ code cho !slots, !hilo, !tungxu, !xucxac, !baucua, !duangua, !quay, !baccarat từ user_17/user_19, nhớ thêm update_profile_stats) ...


# --- XỔ SỐ (LOTTERY) ---
# ... (Dán toàn bộ code cho !lottery group và lottery_draw_task từ user_17/user_19) ...


# --- ĐOÁN SỐ (GUESS THE NUMBER) ---
# ... (Dán toàn bộ code cho Class GuessTheNumberGame và lệnh !guessthenumber, !guess từ user_17/user_19) ...


# --- GAME GIAO DIỆN UI (BLACKJACK & MINES) ---
# ... (Dán toàn bộ code cho Blackjack và Mines từ user_17/user_19, bao gồm Class View, Button và lệnh chính) ...


# --- CHẠY BOT ---
if TOKEN:
    keep_alive(); bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN")
