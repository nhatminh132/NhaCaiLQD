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

# Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
# (Các hằng số game khác được định nghĩa gần lệnh của chúng)
BAU_CUA_FACES = {'bầu': 'Bầu 🍐', 'bau': 'Bầu 🍐', '🍐': 'Bầu 🍐', 'cua': 'Cua 🦀', '🦀': 'Cua 🦀', 'tôm': 'Tôm 🦐', 'tom': 'Tôm 🦐', '🦐': 'Tôm 🦐', 'cá': 'Cá 🐟', 'ca': 'Cá 🐟', '🐟': 'Cá 🐟', 'gà': 'Gà 🐓', 'ga': 'Gà 🐓', '🐓': 'Gà 🐓', 'nai': 'Nai 🦌', '🦌': 'Nai 🦌'}
BAU_CUA_LIST = ['Bầu 🍐', 'Cua 🦀', 'Tôm 🦐', 'Cá 🐟', 'Gà 🐓', 'Nai 🦌']
NUM_HORSES = 6; RACE_LENGTH = 20
SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL, SLOT_WEIGHTS, SLOT_PAYOUTS = [], [], {}
for (symbol, weight, payout) in SLOT_SYMBOLS: SLOT_WHEEL.append(symbol); SLOT_WEIGHTS.append(weight); SLOT_PAYOUTS[symbol] = payout
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
# J=10, Q=10, K=10, A=11/1 (BJ), A=1 (Baccarat), A=14 (Hilo)
CARD_RANKS_VALUE = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 1}
CARD_RANKS_BJ = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}
CARD_RANKS_HILO = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}


# --- CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)

# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
def get_user_data(user_id: int) -> typing.Dict:
    try:
        response = supabase.table('profiles').select('*').eq('user_id', user_id).single().execute()
        return response.data
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
        if not current_stats: return
        new_total_bet = current_stats.get('total_bet', 0) + bet_amount
        new_total_won = current_stats.get('total_won', 0) + max(0, net_gain) # Chỉ cộng phần lời
        new_games_played = current_stats.get('games_played', 0) + 1
        supabase.table('profiles').update({'total_bet': new_total_bet, 'total_won': new_total_won, 'games_played': new_games_played}).eq('user_id', user_id).execute()
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
        current_pool = get_jackpot_pool(game_name)
        new_pool = max(0, current_pool + amount)
        supabase.table(table_name).update({'pool_amount': new_pool}).eq('game_name', game_name).execute()
        return new_pool
    except Exception as e: print(f"Lỗi khi cập nhật jackpot {game_name}: {e}"); return get_jackpot_pool(game_name)

def get_taixiu_history():
    try:
        data = supabase.table('jackpot').select('history').eq('game_name', 'taixiu').single().execute().data
        return data['history'][-10:] if data and data['history'] else []
    except Exception as e: print(f"Loi khi lay history taixiu: {e}"); return []

# --- HÀM KIỂM TRA & SỰ KIỆN BOT ---
@bot.before_invoke
async def global_check_before_command(ctx):
    # Lấy command object một cách an toàn
    command = ctx.command
    if command and command.name == 'help': return # Bỏ qua check cho lệnh help

    bucket = global_cooldown.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after: raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.default)

@bot.event
async def on_ready():
    bot.add_view(TaiXiuGameView())
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
        else: await ctx.send('Số tiền cược hoặc số đoán/số ngựa/số bom không hợp lệ.')
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(f"⏳ {ctx.author.mention}, bạn đang có một trò chơi khác đang chạy. Vui lòng chờ cho nó kết thúc!", ephemeral=True, delete_after=5)
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
    user_data = get_user_data(ctx.author.id); await ctx.send(f'🪙 {ctx.author.mention}, bạn đang có **{user_data["balance"]:,}** token.' if user_data else 'Đã xảy ra lỗi khi lấy số dư của bạn.')
@bot.command(name='daily')
async def daily_reward(ctx):
    user_id = ctx.author.id; user_data = get_user_data(user_id)
    if not user_data: await ctx.send("Lỗi lấy dữ liệu user."); return # Check user_data
    if user_data.get('last_daily'):
        try: last_daily_time = datetime.fromisoformat(user_data['last_daily']); cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        except: last_daily_time = None # Xử lý lỗi format thời gian
        if last_daily_time and datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc); hours_left = int(time_left.total_seconds() // 3600); minutes_left = int((time_left.total_seconds() % 3600) // 60)
            await ctx.send(f'{ctx.author.mention}, bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.'); return
    new_balance = update_balance(user_id, DAILY_REWARD)
    if new_balance is None: await ctx.send("Lỗi cập nhật số dư!"); return # Check update_balance
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
            user = await bot.fetch_user(user_data['user_id']) # Dùng fetch_user để an toàn hơn
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
        elif isinstance(value, (int, float)): embed.add_field(name=key, value=f"`{value:,}`", inline=False) # Format số
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
# ... (Dán toàn bộ code Tài Xỉu UI từ user_17/user_19) ...
class BetModal(ui.Modal, title="Đặt cược"): # ... (code như cũ)
    pass
class TaiXiuGameView(ui.View): # ... (code như cũ)
    pass
def get_bet_totals(): # ... (code như cũ)
    pass
@tasks.loop(seconds=60.0)
async def tai_xiu_game_loop(): # ... (code như cũ, bao gồm cả xử lý nổ hũ)
    pass
@tai_xiu_game_loop.before_loop
async def before_taixiu_loop(): await bot.wait_until_ready()
@bot.command(name='start_taixiu')
@commands.has_role(ADMIN_ROLE)
async def start_taixiu(ctx): # ... (code như cũ)
    pass
@bot.command(name='stop_taixiu')
@commands.has_role(ADMIN_ROLE)
async def stop_taixiu(ctx): # ... (code như cũ)
    pass


# --- GAME THEO LỆNH (CÓ HIỆU ỨNG VÀ KHÓA) ---
@bot.command(name='slots', aliases=['slot'])
@commands.check(is_user_in_game)
async def slots(ctx, bet_amount: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance']
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.'); return
    bot.users_in_animation.add(user_id)
    try:
        final_results = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
        embed = discord.Embed(title="🎰 Máy Xèng 🎰", description="| - | - | - |", color=discord.Color.blue())
        embed.set_footer(text=f"{ctx.author.display_name} đã cược {bet_amount:,} 🪙")
        slot_message = await ctx.send(embed=embed)
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
            embed.description += f"\n\n**💥💥💥 JACKPOT TIẾN TRIỂN!!! 💥💥💥**"
            update_jackpot_pool('slots', -jackpot_pool); update_jackpot_pool('slots', 1000) # Reset về 1000
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
        except discord.NotFound: await ctx.send(embed=embed)
    except asyncio.CancelledError: pass # Bỏ qua nếu tin nhắn bị xóa
    except Exception as e: print(f"Lỗi !slots: {e}")
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='hilo', aliases=['caothap'])
@commands.check(is_user_in_game)
async def hilo(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance']
    choice = choice.lower().strip()
    if choice not in ['cao', 'thấp', 'high', 'low']: await ctx.send('Cú pháp sai! Phải cược `cao` hoặc `thấp`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance:,} 🪙.'); return
    bot.users_in_animation.add(user_id)
    try:
        rank1 = random.choice(list(CARD_RANKS_HILO.keys())); suit1 = random.choice(CARD_SUITS); val1 = CARD_RANKS_HILO[rank1]; card1_str = f"**{rank1}{suit1}** (Giá trị: {val1})"
        embed = discord.Embed(title="⬆️ Cao hay Thấp ⬇️", color=discord.Color.blue())
        embed.add_field(name="Lá bài đầu tiên", value=card1_str, inline=False); embed.add_field(name="Bạn cược", value=f"**{bet_amount:,}** 🪙 vào **{choice.upper()}**", inline=False)
        embed.add_field(name="Lá bài tiếp theo", value="Đang rút bài...", inline=False); msg = await ctx.send(embed=embed); await asyncio.sleep(3)
        rank2 = random.choice(list(CARD_RANKS_HILO.keys())); suit2 = random.choice(CARD_SUITS); val2 = CARD_RANKS_HILO[rank2]; card2_str = f"**{rank2}{suit2}** (Giá trị: {val2})"
        embed.set_field_at(2, name="Lá bài tiếp theo", value=card2_str, inline=False)
        is_win = False
        if val2 > val1 and choice in ['cao', 'high']: is_win = True
        elif val2 < val1 and choice in ['thấp', 'low']: is_win = True
        elif val1 == val2: embed.add_field(name="Kết quả", value="Bằng nhau! Nhà cái thắng.", inline=False)
        if val1 != val2: embed.add_field(name="Kết quả", value=f"{val2} **{'LỚN HƠN' if val2 > val1 else 'NHỎ HƠN'}** {val1}", inline=False)
        payout = bet_amount if is_win else -bet_amount; new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)
        if is_win: embed.description = f"🎉 **Bạn đã thắng!**\nBạn nhận được **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except Exception as e: print(f"Lỗi !hilo: {e}")
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='tungxu', aliases=['coinflip'])
@commands.check(is_user_in_game)
async def coinflip(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        embed = discord.Embed(title="🪙 Đang tung đồng xu...", description="Đồng xu đang xoay trên không...", color=discord.Color.blue())
        msg = await ctx.send(embed=embed); await asyncio.sleep(2.5)
        result = random.choice(['sấp', 'ngửa']); is_win = (choice == result) or (choice == 'sap' and result == 'sấp') or (choice == 'ngua' and result == 'ngửa')
        payout = bet_amount if is_win else -bet_amount; new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)
        embed.title = f"Tung đồng xu 🪙... Kết quả là **{result.upper()}**!"
        if is_win: embed.description = f"🎉 Bạn đoán đúng! Bạn thắng **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except Exception as e: print(f"Lỗi !tungxu: {e}")
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='xucxac', aliases=['dice'])
@commands.check(is_user_in_game)
async def dice_roll(ctx, bet_amount: int, guess: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        embed = discord.Embed(title="🎲 Đang gieo xúc xắc...", description="Xúc xắc đang lăn...", color=discord.Color.dark_purple())
        msg = await ctx.send(embed=embed); await asyncio.sleep(2.5)
        result = random.randint(1, 6); is_win = (guess == result); winnings = bet_amount * 5 if is_win else 0
        payout = winnings if is_win else -bet_amount; new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)
        embed.title = f"Gieo xúc xắc 🎲... Kết quả là **{result}**!"
        if is_win: embed.description = f"🎉 Chính xác! Bạn thắng **{winnings:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except Exception as e: print(f"Lỗi !xucxac: {e}")
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='baucua', aliases=['bc'])
@commands.check(is_user_in_game)
async def bau_cua(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    user_choice_full = BAU_CUA_FACES.get(choice.lower().strip())
    if not user_choice_full: await ctx.send('Cú pháp sai! Phải cược vào `bầu`, `cua`, `tôm`, `cá`, `gà`, hoặc `nai`.'); return
    bot.users_in_animation.add(user_id)
    try:
        final_results = random.choices(BAU_CUA_LIST, k=3)
        embed = discord.Embed(title="🦀 Đang lắc Bầu Cua...", description="| ❔ | ❔ | ❔ |", color=discord.Color.dark_orange())
        embed.set_footer(text=f"{ctx.author.display_name} cược {bet_amount:,} 🪙 vào {user_choice_full}")
        msg = await ctx.send(embed=embed); current_display = ['❔'] * 3
        for i in range(5):
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
        hits = final_results.count(user_choice_full); is_win = (hits > 0); winnings = bet_amount * hits if is_win else 0
        payout = winnings if is_win else -bet_amount; new_balance = update_balance(user_id, payout)
        update_profile_stats(user_id, bet_amount, payout)
        embed.title = "🦀 Lắc Bầu Cua 🎲"
        if is_win: embed.description += f"\n\n🎉 **Bạn đã thắng!** Trúng {hits} lần.\nBạn nhận được **{winnings:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.green()
        else: embed.description += f"\n\n😢 **Bạn đã thua!** Bạn mất **{bet_amount:,}** token.\nSố dư mới: **{new_balance:,}** 🪙."; embed.color = discord.Color.red()
        await msg.edit(embed=embed)
    except asyncio.CancelledError: pass
    except Exception as e: print(f"Lỗi !baucua: {e}")
    finally: bot.users_in_animation.discard(user_id)

@bot.command(name='duangua', aliases=['race'])
@commands.check(is_user_in_game)
async def dua_ngua(ctx, bet_amount: int, horse_number: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game duangua với hiệu ứng)
        payout = winnings if is_win else -bet_amount
        update_profile_stats(user_id, bet_amount, payout)
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

# --- GAME MỚI THEO LỆNH ---
@bot.command(name='baccarat')
@commands.check(is_user_in_game)
async def baccarat(ctx, bet_amount: int, choice: str):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    choice = choice.lower().strip()
    if choice not in ['player', 'banker', 'tie']: await ctx.send('Cú pháp sai! Phải cược `player`, `banker`, hoặc `tie`.'); return
    bot.users_in_animation.add(user_id)
    try:
        # ... (logic game baccarat với hiệu ứng)
        update_profile_stats(user_id, bet_amount, payout) # Cập nhật stats
        # ... (hiển thị kết quả)
    finally: bot.users_in_animation.discard(user_id)

# --- XỔ SỐ (LOTTERY) ---
@bot.group(name='lottery', aliases=['xs', 'loto'], invoke_without_command=True)
async def lottery(ctx): await ctx.send("Lệnh xổ số: `!lottery buy <s1>..<s6>` hoặc `!lottery result`.")
@lottery.command(name='buy')
@commands.check(is_user_in_game)
async def lottery_buy(ctx, n1: int, n2: int, n3: int, n4: int, n5: int, n6: int):
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance'] # ... (kiểm tra input)
    numbers = sorted(list(set([n1, n2, n3, n4, n5, n6])))
    if len(numbers) != 6: await ctx.send("Phải chọn đúng 6 số khác nhau."); return
    if not all(1 <= n <= 45 for n in numbers): await ctx.send("Các số phải nằm trong khoảng từ 1 đến 45."); return
    if balance < LOTTERY_TICKET_PRICE: await ctx.send(f"Bạn không đủ tiền mua vé! Cần {LOTTERY_TICKET_PRICE} 🪙."); return
    # Trừ tiền, Lưu vé, Cập nhật stats
    new_balance = update_balance(user_id, -LOTTERY_TICKET_PRICE)
    update_profile_stats(user_id, LOTTERY_TICKET_PRICE, -LOTTERY_TICKET_PRICE)
    today = datetime.now(VIETNAM_TZ).date()
    try: supabase.table('lottery_tickets').insert({'user_id': user_id, 'numbers': numbers, 'draw_date': str(today)}).execute(); await ctx.send(f"✅ Bạn đã mua thành công vé số cho ngày {today.strftime('%d/%m/%Y')} với các số: `{' '.join(map(str, numbers))}`. Số dư: {new_balance:,} 🪙.")
    except Exception as e: await ctx.send(f"Lỗi khi lưu vé số: {e}"); update_balance(user_id, LOTTERY_TICKET_PRICE); update_profile_stats(user_id, 0, LOTTERY_TICKET_PRICE) # Hoàn tiền
@lottery.command(name='result')
async def lottery_result(ctx):
    # ... (code xem kết quả như cũ)
    pass
@tasks.loop(time=LOTTERY_DRAW_TIME)
async def lottery_draw_task():
    # ... (code quay số như cũ)
    pass

# --- ĐOÁN SỐ (GUESS THE NUMBER) ---
# (Class GuessTheNumberGame và các lệnh !guessthenumber, !guess giữ nguyên)
class GuessTheNumberGame: # ... (code như cũ)
    pass
@bot.command(name='guessthenumber', aliases=['gtn', 'doanso'])
@commands.check(is_user_in_game)
async def guess_the_number_start(ctx, bet_amount: int): # ... (code như cũ)
    pass
@bot.command(name='guess', aliases=['doan'])
async def guess_number(ctx, number: int): # ... (code như cũ)
    pass

# --- GAME GIAO DIỆN UI (BLACKJACK & MINES) ---
# (Toàn bộ code Blackjack và Mines giữ nguyên, bao gồm các Class View, Button và lệnh chính)
# ... (Dán code game Blackjack UI từ phiên bản trước) ...
# ... (Dán code game Mines UI từ phiên bản trước) ...


# --- CHẠY BOT ---
if TOKEN:
    keep_alive(); bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN")
