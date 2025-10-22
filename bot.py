import discord
from discord.ext import commands, tasks
from discord import ui # Dùng cho Nút (Buttons) và Pop-up (Modals)
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client 
import typing
import random
import asyncio
import math

# Import tệp keep_alive
from keep_alive import keep_alive 

# --- Tải Token và Cài đặt Bot ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# --- Cài đặt Supabase ---
if not SUPABASE_URL or not SUPABASE_KEY:
    print("LỖI: Không tìm thấy SUPABASE_URL hoặc SUPABASE_KEY")
    exit()

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

# --- ĐỊNH NGHĨA HẰNG SỐ ---
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24 
ADMIN_ROLE = "Bot Admin" 

# Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

# Bầu Cua
BAU_CUA_FACES = {
    'bầu': 'Bầu 🍐', 'bau': 'Bầu 🍐', '🍐': 'Bầu 🍐',
    'cua': 'Cua 🦀', '🦀': 'Cua 🦀',
    'tôm': 'Tôm 🦐', 'tom': 'Tôm 🦐', '🦐': 'Tôm 🦐',
    'cá': 'Cá 🐟', 'ca': 'Cá 🐟', '🐟': 'Cá 🐟',
    'gà': 'Gà 🐓', 'ga': 'Gà 🐓', '🐓': 'Gà 🐓',
    'nai': 'Nai 🦌', '🦌': 'Nai 🦌'
}
BAU_CUA_LIST = ['Bầu 🍐', 'Cua 🦀', 'Tôm 🦐', 'Cá 🐟', 'Gà 🐓', 'Nai 🦌']

# Đua Ngựa
NUM_HORSES = 6
RACE_LENGTH = 20

# Máy Xèng (Slots)
# (Emoji, Trọng số xuất hiện, Payout cho 3x)
SLOT_SYMBOLS = [
    ('🍒', 10, 10), # (10/38)
    ('🍋', 9, 15),  # (9/38)
    ('🍊', 8, 20),  # (8/38)
    ('🍓', 5, 30),  # (5/38)
    ('🔔', 3, 50),  # (3/38)
    ('💎', 2, 100), # (2/38)
    ('7️⃣', 1, 200)  # (1/38) -> Jackpot
]
SLOT_WHEEL, SLOT_WEIGHTS, SLOT_PAYOUTS = [], [], {}
for (symbol, weight, payout) in SLOT_SYMBOLS:
    SLOT_WHEEL.append(symbol)
    SLOT_WEIGHTS.append(weight)
    SLOT_PAYOUTS[symbol] = payout

# Cao/Thấp (Hilo) & Blackjack
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
CARD_RANKS = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 11, 'Q': 12, 'K': 13, 'A': 14 # A là 14 trong Hilo, 1 hoặc 11 trong Blackjack
}

# --- (ĐÃ CẬP NHẬT) CÀI ĐẶT RATE LIMIT TOÀN CỤC ---
# 30 lệnh, mỗi 60 giây, áp dụng cho TOÀN BỘ BOT (BucketType.default)
global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)


# --- QUẢN LÝ DỮ LIỆU (SUPABASE) ---
# (Toàn bộ các hàm get_user_data, update_balance được giữ nguyên)
def get_user_data(user_id: int) -> typing.Dict:
    """Lấy dữ liệu người dùng từ Supabase, tạo mới nếu chưa có."""
    try:
        response = supabase.table('profiles').select('*').eq('user_id', user_id).execute()
        if not response.data:
            insert_response = supabase.table('profiles').insert({
                'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': []
            }).execute()
            return insert_response.data[0]
        return response.data[0]
    except Exception as e:
        print(f"Lỗi khi get_user_data cho {user_id}: {e}")
        return None 

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    """Sử dụng RPC function 'adjust_balance' để cộng/trừ tiền."""
    try:
        response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
        return response.data
    except Exception as e:
        print(f"Lỗi khi update_balance cho {user_id}: {e}")
        get_user_data(user_id) # Thử tạo user
        try:
            response = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
            return response.data
        except Exception as e2:
            print(f"Lỗi lần 2 khi update_balance: {e2}")
            return None

# Hàm lấy Hũ và Lịch sử (cho Tài Xỉu)
def get_jackpot_data():
    try:
        data = supabase.table('jackpot').select('*').eq('game_name', 'taixiu').execute().data[0]
        return data['pool_amount'], data['history'][-10:] # Lấy 10 kết quả gần nhất
    except Exception as e:
        print(f"Loi khi lay jackpot: {e}")
        return 0, []

# --- HÀM KIỂM TRA COOLDOWN TOÀN CỤC ---
@bot.before_invoke
async def global_check_before_command(ctx):
    """Kiểm tra rate limit trước khi thực thi bất kỳ lệnh nào."""
    if ctx.command.name == 'help':
        return
    bucket = global_cooldown.get_bucket(ctx.message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        raise commands.CommandOnCooldown(bucket, retry_after, commands.BucketType.default)

# --- SỰ KIỆN BOT ---
@bot.event
async def on_ready():
    # Thêm dòng này để bot nhận diện các Nút bấm (Views) sau khi khởi động lại
    bot.add_view(TaiXiuGameView()) 
    print(f'Bot {bot.user.name} đã sẵn sàng!')
    print('------')

# --- HÀM XỬ LÝ LỖI TOÀN CỤC ---
@bot.event
async def on_command_error(ctx, error):
    """Xử lý tất cả các lỗi tập trung tại một nơi."""
    
    # 1. Lỗi Rate Limit
    if isinstance(error, commands.CommandOnCooldown):
        seconds = error.retry_after
        await ctx.send(f"⏳ Bot đang xử lý quá nhiều yêu cầu! Vui lòng thử lại sau **{seconds:.1f} giây**.", delete_after=5)
        return

    # 2. Lỗi Admin
    if isinstance(error, commands.MissingRole):
        await ctx.send(f"Rất tiếc {ctx.author.mention}, bạn không có quyền dùng lệnh này. Cần role `{ADMIN_ROLE}`.")
        return

    # 3. Lỗi nhập sai
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Cú pháp sai! Gõ `!help` để xem hướng dẫn lệnh `{ctx.command.name}`.')
        return
        
    if isinstance(error, commands.BadArgument):
        if ctx.command.name in ['admin_give', 'admin_set', 'chuyenxu']:
             await ctx.send('Không tìm thấy người dùng đó hoặc số tiền không hợp lệ.')
        else:
             await ctx.send('Số tiền cược hoặc số đoán/số ngựa không hợp lệ.')
        return
        
    # 4. Lỗi game đang diễn ra (cho game UI)
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"{ctx.author.mention}, bạn đang có một ván game khác đang chạy!", ephemeral=True)
        return

    # 5. Báo lỗi chung
    print(f"Lỗi không xác định từ lệnh '{ctx.command.name}': {error}")
    await ctx.send('Đã xảy ra lỗi. Vui lòng thử lại sau.')


# --- HÀM KIỂM TRA GAME ĐANG CHẠY (CHO GAME UI) ---
def is_user_in_game(ctx):
    """Check xem user có đang chơi Blackjack hoặc Mines không."""
    if ctx.author.id in bot.blackjack_games:
        return False # Đang chơi game
    if ctx.author.id in bot.mines_games:
        return False # Đang chơi game
    return True # Không chơi game, cho phép chạy lệnh


# --- LỆNH !HELP (ĐÃ CẬP NHẬT) ---
@bot.command(name='help')
async def custom_help(ctx):
    embed = discord.Embed(title="Trợ giúp Bot Casino 🎰", color=discord.Color.gold())
    
    embed.add_field(name="🪙 Lệnh Cơ bản", 
        value="`!help` - Hiển thị bảng trợ giúp này.\n"
              "`!kiemtra` - (aliases: `!bal`, `!sodu`) Xem số dư token.\n"
              "`!daily` - Nhận thưởng token hàng ngày.\n"
              "`!code <mã>` - Nhập giftcode nhận thưởng.\n"
              "`!chuyenxu @user <số_tiền>` - Chuyển token cho người khác.\n"
              "`!bangxephang` - (aliases: `!top`) Xem 10 người giàu nhất.",
        inline=False)
    
    embed.add_field(name="🎲 Trò chơi (Gõ lệnh)",
        value="`!slots <số_tiền>` - Chơi máy xèng.\n"
              "`!hilo <số_tiền> <cao/thấp>` - Đoán lá bài tiếp theo.\n"
              "`!tungxu <số_tiền> <sấp/ngửa>` - Cược 50/50.\n"
              "`!xucxac <số_tiền> <số_đoán>` - Đoán số (1-6), thắng 1 ăn 5.\n"
              "`!baucua <số_tiền> <linh_vật>` - Cược Bầu Cua Tôm Cá.\n"
              "`!duangua <số_tiền> <số_ngựa>` - Cược đua ngựa (1-6), thắng 1 ăn 4.",
        inline=False)
        
    embed.add_field(name="🃏 Trò chơi (Giao diện UI)",
        value="`!blackjack <số_tiền>` - (aliases: `!bj`) Chơi Xì dách với bot.\n"
              "`!mines <số_tiền> <số_bom>` - Chơi Dò Mìn (tối đa 24 bom).",
        inline=False)
        
    embed.add_field(name="🎮 Game 24/7 (Dùng Nút)",
        value="Tìm kênh có game **Tài Xỉu** và dùng **Nút (Buttons)** để cược.",
        inline=False)

    embed.add_field(name="🛠️ Lệnh Admin", 
        value="`!admin_give @user <số_tiền>` - Cộng/Trừ token.\n"
              "`!admin_set @user <số_tiền>` - Đặt chính xác số token.\n"
              "`!admin_createcode <code> <reward>` - Tạo giftcode.\n"
              "`!admin_deletecode <code>` - Xóa giftcode.\n"
              "`!start_taixiu` - Bắt đầu game Tài Xỉu 24/7 ở kênh này.\n"
              "`!stop_taixiu` - Dừng game Tài Xỉu.",
        inline=False)
    
    embed.set_footer(text="Chúc bạn may mắn!")
    await ctx.send(embed=embed)


# --- LỆNH CƠ BẢN VÀ XÃ HỘI ---
# (Tất cả các lệnh !kiemtra, !daily, !code, !bangxephang, !chuyenxu giữ nguyên)
@bot.command(name='kiemtra', aliases=['balance', 'bal', 'sodu'])
async def balance_check(ctx):
    user_data = get_user_data(ctx.author.id)
    if user_data:
        await ctx.send(f'🪙 {ctx.author.mention}, bạn đang có **{user_data["balance"]}** token.')
    else:
        await ctx.send('Đã xảy ra lỗi khi lấy số dư của bạn.')

@bot.command(name='daily')
async def daily_reward(ctx):
    user_id = ctx.author.id
    user_data = get_user_data(user_id)
    if user_data.get('last_daily'):
        last_daily_time = datetime.fromisoformat(user_data['last_daily'])
        cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        if datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc)
            hours_left = int(time_left.total_seconds() // 3600)
            minutes_left = int((time_left.total_seconds() % 3600) // 60)
            await ctx.send(f'{ctx.author.mention}, bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.')
            return
    new_balance = update_balance(user_id, DAILY_REWARD)
    try:
        supabase.table('profiles').update({'last_daily': datetime.now(timezone.utc).isoformat()}).eq('user_id', user_id).execute()
        await ctx.send(f'🎉 {ctx.author.mention}, bạn đã nhận được **{DAILY_REWARD}** token! Số dư mới: **{new_balance}** 🪙.')
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi khi cập nhật thời gian: {e}')

@bot.command(name='code')
async def redeem_code(ctx, code_to_redeem: str):
    user_id = ctx.author.id
    user_data = get_user_data(user_id)
    code_to_redeem = code_to_redeem.upper()
    try:
        code_response = supabase.table('gift_codes').select('*').eq('code', code_to_redeem).execute()
        if not code_response.data:
            await ctx.send(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.')
            return
    except Exception as e:
        await ctx.send(f'Lỗi khi kiểm tra code: {e}'); return
    if code_to_redeem in user_data['used_codes']:
        await ctx.send(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.'); return
    reward = code_response.data[0]['reward']
    new_balance = update_balance(user_id, reward)
    try:
        new_code_list = user_data['used_codes'] + [code_to_redeem]
        supabase.table('profiles').update({'used_codes': new_code_list}).eq('user_id', user_id).execute()
        await ctx.send(f'🎁 {ctx.author.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward}** token! Số dư mới: **{new_balance}** 🪙.')
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi khi cập nhật code đã dùng: {e}')

@bot.command(name='bangxephang', aliases=['top'])
async def leaderboard(ctx, top_n: int = 10):
    if top_n <= 0: top_n = 10
    try:
        response = supabase.table('profiles').select('user_id', 'balance').order('balance', desc=True).limit(top_n).execute()
        if not response.data:
            await ctx.send('Chưa có ai trong bảng xếp hạng.'); return
        embed = discord.Embed(title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆", color=discord.Color.gold())
        rank_count = 1
        for user_data in response.data:
            user = ctx.guild.get_member(user_data['user_id'])
            user_name = user.display_name if user else f"Người dùng (ID: ...{str(user_data['user_id'])[-4:]})"
            embed.add_field(name=f"#{rank_count}: {user_name}", value=f"**{user_data['balance']}** 🪙", inline=False)
            rank_count += 1
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f'Lỗi khi lấy bảng xếp hạng: {e}')

@bot.command(name='chuyenxu', aliases=['give', 'transfer'])
async def transfer_tokens(ctx, recipient: discord.Member, amount: int):
    sender_id = ctx.author.id
    recipient_id = recipient.id
    if sender_id == recipient_id:
        await ctx.send('Bạn không thể tự chuyển cho chính mình!'); return
    if amount <= 0:
        await ctx.send('Số tiền chuyển phải lớn hơn 0!'); return
    sender_data = get_user_data(sender_id)
    if sender_data['balance'] < amount:
        await ctx.send(f'Bạn không đủ tiền. Bạn chỉ có **{sender_data["balance"]}** 🪙.'); return
    try:
        update_balance(sender_id, -amount) 
        new_recipient_balance = update_balance(recipient_id, amount) 
        await ctx.send(f'✅ {ctx.author.mention} đã chuyển **{amount}** 🪙 cho {recipient.mention}!')
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi trong quá trình chuyển: {e}')
    

# --- LỆNH ADMIN ---
# (Tất cả các lệnh admin_give, admin_set, admin_createcode, admin_deletecode giữ nguyên)
@bot.command(name='admin_give')
@commands.has_role(ADMIN_ROLE)
async def admin_give(ctx, member: discord.Member, amount: int):
    if amount == 0: await ctx.send("Số lượng phải khác 0."); return
    user_id = member.id
    new_balance = update_balance(user_id, amount)
    if amount > 0:
        await ctx.send(f"✅ Đã cộng **{amount}** 🪙 cho {member.mention}. Số dư mới: **{new_balance}** 🪙.")
    else:
        await ctx.send(f"✅ Đã trừ **{abs(amount)}** 🪙 từ {member.mention}. Số dư mới: **{new_balance}** 🪙.")

@bot.command(name='admin_set')
@commands.has_role(ADMIN_ROLE)
async def admin_set(ctx, member: discord.Member, amount: int):
    if amount < 0: await ctx.send("Không thể set số dư âm."); return
    try:
        supabase.rpc('set_balance', {'user_id_input': member.id, 'amount_input': amount}).execute()
        await ctx.send(f"✅ Đã set số dư của {member.mention} thành **{amount}** 🪙.")
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi khi set balance: {e}")

@bot.command(name='admin_createcode')
@commands.has_role(ADMIN_ROLE)
async def admin_createcode(ctx, code: str, reward: int):
    if reward <= 0: await ctx.send("Phần thưởng phải lớn hơn 0."); return
    code = code.upper()
    try:
        supabase.table('gift_codes').insert({'code': code, 'reward': reward}).execute()
        await ctx.send(f"✅ Đã tạo giftcode `{code}` trị giá **{reward}** 🪙.")
    except Exception as e:
        await ctx.send(f"Lỗi! Code `{code}` có thể đã tồn tại. ({e})")

@bot.command(name='admin_deletecode')
@commands.has_role(ADMIN_ROLE)
async def admin_deletecode(ctx, code: str):
    code = code.upper()
    try:
        response = supabase.table('gift_codes').delete().eq('code', code).execute()
        if response.data: 
            await ctx.send(f"✅ Đã xóa thành công giftcode `{code}`.")
        else:
            await ctx.send(f"Lỗi! Không tìm thấy giftcode nào tên là `{code}`.")
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi khi xóa code: {e}")

# --- GAME 24/7: TÀI XỈU (UI) ---
# (Toàn bộ logic của game Tài Xỉu 24/7: BetModal, TaiXiuGameView, tai_xiu_game_loop, start/stop_taixiu giữ nguyên)

class BetModal(ui.Modal, title="Đặt cược"):
    def __init__(self, bet_type: str):
        super().__init__()
        self.bet_type = bet_type
        self.amount_input = ui.TextInput(label=f"Nhập số tiền cược cho [ {bet_type.upper()} ]", placeholder="Ví dụ: 1000", style=discord.TextStyle.short)
        self.add_item(self.amount_input)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try: amount = int(self.amount_input.value)
        except ValueError: await interaction.response.send_message("Số tiền cược phải là một con số!", ephemeral=True); return
        if amount <= 0: await interaction.response.send_message("Số tiền cược phải lớn hơn 0!", ephemeral=True); return
        user_data = get_user_data(user_id)
        if user_data['balance'] < amount:
            await interaction.response.send_message(f"Bạn không đủ tiền! Bạn chỉ có {user_data['balance']} 🪙.", ephemeral=True); return
        current_bets[user_id] = {'type': self.bet_type, 'amount': amount}
        await interaction.response.send_message(f"✅ Bạn đã cược **{amount}** 🪙 vào cửa **{self.bet_type.upper()}** thành công!", ephemeral=True)

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
    current_bets = {}; jackpot_pool, history = get_jackpot_data()
    embed = discord.Embed(title="🎲 PHIÊN TÀI XỈU MỚI 🎲", description="Mời bạn chọn cửa. **Còn 45 giây...**", color=discord.Color.gold())
    embed.add_field(name="Tỉ lệ cược", value="• Tài - Xỉu: **x1.9**\n• Chẵn - Lẻ: **x1.9**\n• *Bộ Ba Đồng Nhất*: Nhà cái ăn (trừ Hũ)", inline=False)
    embed.add_field(name="💰 HŨ TÀI XỈU 💰", value=f"**{jackpot_pool:,}** 🪙", inline=True)
    embed.add_field(name="📈 Soi cầu (gần nhất bên phải)", value=f"`{' | '.join(history)}`" if history else "Chưa có dữ liệu", inline=True)
    embed.add_field(name="Tổng Cược Hiện Tại", value="• Tài: 0 🪙\n• Xỉu: 0 🪙\n• Chẵn: 0 🪙\n• Lẻ: 0 🪙", inline=False)
    embed.set_footer(text="Nhấn nút bên dưới để đặt cược!")
    if game_message: await game_message.delete()
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
    jackpot_contrib = 0; payout_log = []
    for user_id, bet in current_bets.items():
        bet_type, amount = bet['type'], bet['amount']
        contrib = int(amount * 0.01); jackpot_contrib += contrib; winnings = 0; is_win = False
        if not is_triple:
            if (bet_type == 'tài' and is_tai) or (bet_type == 'xỉu' and is_xiu) or (bet_type == 'chẵn' and is_chan) or (bet_type == 'lẻ' and is_le): is_win = True
        if is_win:
            winnings = int(amount * 0.9); update_balance(user_id, winnings)
            payout_log.append(f"<@{user_id}> thắng **{winnings:,}** 🪙 (cửa {bet_type})")
        else: update_balance(user_id, -(amount - contrib))
    new_jackpot = jackpot_pool + jackpot_contrib
    supabase.table('jackpot').update({'pool_amount': new_jackpot, 'history': history}).eq('game_name', 'taixiu').execute()
    embed_result = discord.Embed(title=f"{result_emoji} KẾT QUẢ: {result_text} {result_emoji}", color=discord.Color.green() if payout_log else discord.Color.red())
    embed_result.add_field(name="Kết quả xúc xắc", value=f"**{d1} | {d2} | {d3}** (Tổng: **{total}**)", inline=False)
    embed_result.add_field(name="💰 Hũ hiện tại 💰", value=f"**{new_jackpot:,}** 🪙 (+{jackpot_contrib:,})", inline=False)
    embed_result.add_field(name="Người thắng", value="\n".join(payout_log[:15]) if payout_log else "Không có ai thắng ván này.", inline=False)
    embed_result.set_footer(text="Phiên mới sẽ bắt đầu sau 5 giây...")
    await game_message.edit(embed=embed_result, view=None); await asyncio.sleep(5)

@tai_xiu_game_loop.before_loop
async def before_taixiu_loop(): await bot.wait_until_ready()

@bot.command(name='start_taixiu')
@commands.has_role(ADMIN_ROLE)
async def start_taixiu(ctx):
    global game_channel_id; game_channel_id = ctx.channel.id
    if not tai_xiu_game_loop.is_running():
        tai_xiu_game_loop.start(); await ctx.send(f"✅ Đã bắt đầu Game Tài Xỉu 24/7 tại kênh <#{game_channel_id}>.")
    else: await ctx.send(f"Game đã chạy tại kênh <#{game_channel_id}> rồi.")

@bot.command(name='stop_taixiu')
@commands.has_role(ADMIN_ROLE)
async def stop_taixiu(ctx):
    global game_channel_id
    if tai_xiu_game_loop.is_running():
        tai_xiu_game_loop.stop(); game_channel_id = None; await ctx.send("✅ Đã dừng Game Tài Xỉu.")
    else: await ctx.send("Game chưa chạy.")


# --- GAME THEO LỆNH (COMMAND-BASED) ---

@bot.command(name='slots', aliases=['slot'])
@commands.check(is_user_in_game) # Check xem có đang chơi game UI không
async def slots(ctx, bet_amount: int):
    """Chơi máy xèng."""
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    
    # Quay 3 cột
    results = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
    slot_str = f"| {results[0]} | {results[1]} | {results[2]} |"
    
    embed = discord.Embed(title="🎰 Máy Xèng 🎰", description=slot_str, color=discord.Color.dark_orange())
    
    winnings = 0
    if results[0] == results[1] == results[2]:
        # 3x giống nhau
        payout = SLOT_PAYOUTS[results[0]]
        winnings = bet_amount * payout
        embed.description += f"\n\n**JACKPOT!** Bạn trúng 3x {results[0]} (1 ăn {payout})!"
    elif results[0] == results[1] or results[1] == results[2]:
        # 2x giống nhau
        winnings = bet_amount * 1 # 1 ăn 1
        embed.description += f"\n\nBạn trúng 2x {results[1]} (1 ăn 1)!"

    if winnings > 0:
        new_balance = update_balance(user_id, winnings)
        embed.description += f"\n🎉 Bạn thắng **{winnings}** 🪙!\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        embed.description += f"\n\n😢 Chúc may mắn lần sau.\nBạn mất **{bet_amount}** 🪙.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()
        
    await ctx.send(embed=embed)

@bot.command(name='hilo', aliases=['caothap'])
@commands.check(is_user_in_game)
async def hilo(ctx, bet_amount: int, choice: str):
    """Chơi Cao hay Thấp (Higher or Lower)."""
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    choice = choice.lower().strip()
    
    if choice not in ['cao', 'thấp', 'high', 'low']:
        await ctx.send('Cú pháp sai! Phải cược `cao` hoặc `thấp`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return

    # Rút 2 lá bài
    rank1, suit1 = random.choice(list(CARD_RANKS.items()))
    rank2, suit2 = random.choice(list(CARD_RANKS.items()))
    val1, val2 = CARD_RANKS[rank1], CARD_RANKS[rank2]
    
    card1_str = f"**{rank1}{suit1}** (Giá trị: {val1})"
    card2_str = f"**{rank2}{suit2}** (Giá trị: {val2})"
    
    embed = discord.Embed(title="⬆️ Cao hay Thấp ⬇️", color=discord.Color.blue())
    embed.add_field(name="Lá bài đầu tiên", value=card1_str, inline=False)
    embed.add_field(name="Bạn cược", value=f"**{bet_amount}** 🪙 vào **{choice.upper()}**", inline=False)
    embed.add_field(name="Lá bài tiếp theo", value=card2_str, inline=False)

    is_win = False
    if val2 > val1 and choice in ['cao', 'high']:
        is_win = True
    elif val2 < val1 and choice in ['thấp', 'low']:
        is_win = True
    elif val1 == val2:
        # Hòa thì thua
        is_win = False
        embed.add_field(name="Kết quả", value="Bằng nhau! Nhà cái thắng.", inline=False)
        
    if val1 != val2:
         embed.add_field(name="Kết quả", value=f"{val2} **{'LỚN HƠN' if val2 > val1 else 'NHỎ HƠN'}** {val1}", inline=False)

    if is_win:
        winnings = bet_amount # 1 ăn 1
        new_balance = update_balance(user_id, winnings)
        embed.description = f"🎉 **Bạn đã thắng!**\nBạn nhận được **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        embed.description = f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()

    await ctx.send(embed=embed)

@bot.command(name='tungxu', aliases=['coinflip'])
@commands.check(is_user_in_game)
async def coinflip(ctx, bet_amount: int, choice: str):
    # (Giữ nguyên lệnh !tungxu)
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance']
    choice = choice.lower().strip()
    if choice not in ['sấp', 'ngửa', 'sap', 'ngua']: await ctx.send('Cú pháp sai! Phải cược `sấp` hoặc `ngửa`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    result = random.choice(['sấp', 'ngửa'])
    embed = discord.Embed(title=f"Tung đồng xu 🪙... Kết quả là **{result.upper()}**!")
    if (choice == result) or (choice == 'sap' and result == 'sấp') or (choice == 'ngua' and result == 'ngửa'):
        new_balance = update_balance(user_id, bet_amount); embed.description = f"🎉 Bạn đoán đúng! Bạn thắng **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount); embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.red()
    await ctx.send(embed=embed)

@bot.command(name='xucxac', aliases=['dice'])
@commands.check(is_user_in_game)
async def dice_roll(ctx, bet_amount: int, guess: int):
    # (Giữ nguyên lệnh !xucxac)
    user_id, balance = ctx.author.id, get_user_data(ctx.author.id)['balance']
    if not 1 <= guess <= 6: await ctx.send('Cú pháp sai! Phải đoán một số từ `1` đến `6`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    result = random.randint(1, 6)
    embed = discord.Embed(title=f"Gieo xúc xắc 🎲... Kết quả là **{result}**!")
    if guess == result:
        winnings = bet_amount * 5; new_balance = update_balance(user_id, winnings)
        embed.description = f"🎉 Chính xác! Bạn thắng **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.red()
    await ctx.send(embed=embed)

@bot.command(name='baucua', aliases=['bc'])
@commands.check(is_user_in_game)
async def bau_cua(ctx, bet_amount: int, choice: str):
    # (Lệnh !baucua đã được cung cấp ở lượt trước)
    user_id, balance = ctx.author.id, get_user_data(user_id)['balance']
    choice_clean = choice.lower().strip()
    user_choice_full = BAU_CUA_FACES.get(choice_clean)
    if not user_choice_full: await ctx.send('Cú pháp sai! Phải cược vào `bầu`, `cua`, `tôm`, `cá`, `gà`, hoặc `nai`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    results = random.choices(BAU_CUA_LIST, k=3)
    hits = results.count(user_choice_full)
    results_str = f"Kết quả: **{results[0]} | {results[1]} | {results[2]}**"
    embed = discord.Embed(title="🦀 Lắc Bầu Cua 🎲", description=f"{results_str}\n\n{ctx.author.mention} cược **{bet_amount}** 🪙 vào **{user_choice_full}**.")
    if hits > 0:
        winnings = bet_amount * hits; new_balance = update_balance(user_id, winnings)
        embed.description += f"\n🎉 **Bạn đã thắng!** Trúng {hits} lần.\nBạn nhận được **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        embed.description += f"\n😢 **Bạn đã thua!** Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."; embed.color = discord.Color.red()
    await ctx.send(embed=embed)

@bot.command(name='duangua', aliases=['race'])
@commands.check(is_user_in_game)
async def dua_ngua(ctx, bet_amount: int, horse_number: int):
    # (Lệnh !duangua đã được cung cấp ở lượt trước)
    user_id, balance = ctx.author.id, get_user_data(user_id)['balance']
    if not 1 <= horse_number <= NUM_HORSES: await ctx.send(f'Cú pháp sai! Phải cược vào ngựa số `1` đến `{NUM_HORSES}`.'); return
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    positions = [0] * NUM_HORSES
    def get_race_track(positions):
        track = ""
        for i in range(NUM_HORSES):
            pos_clamped = min(positions[i], RACE_LENGTH) 
            track += f"🐎 {i+1}: {'-' * (pos_clamped - 1)}{'🏆' if pos_clamped == RACE_LENGTH else '🏁'}\n"
        return track
    embed = discord.Embed(title="🐎 Cuộc Đua Bắt Đầu! 🐎", description=get_race_track(positions), color=discord.Color.blue())
    embed.set_footer(text=f"{ctx.author.display_name} cược {bet_amount} 🪙 vào ngựa số {horse_number}.")
    race_msg = await ctx.send(embed=embed)
    winner = None
    while winner is None:
        await asyncio.sleep(2)
        for i in range(NUM_HORSES):
            if winner is None: # Chỉ ngựa nào chưa thắng mới được chạy
                positions[i] += random.randint(1, 3)
                if positions[i] >= RACE_LENGTH:
                    positions[i] = RACE_LENGTH # Chốt vị trí
                    winner = i + 1 
        embed.description = get_race_track(positions)
        try: await race_msg.edit(embed=embed)
        except discord.NotFound: return
        if winner: break
    is_win = (winner == horse_number)
    result_title = f"🐎 Ngựa số {winner} đã chiến thắng! 🏆"
    result_description = get_race_track(positions)
    if is_win:
        winnings = bet_amount * 4; new_balance = update_balance(user_id, winnings)
        result_description += f"\n\n🎉 **Bạn đã thắng!** Ngựa số {horse_number} đã về nhất!\nBạn nhận được **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        result_description += f"\n\n😢 **Bạn đã thua!** Ngựa của bạn (số {horse_number}) đã không thắng.\nBạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()
    embed.title = result_title; embed.description = result_description
    try: await race_msg.edit(embed=embed)
    except discord.NotFound: await ctx.send(embed=embed)


# --- GAME GIAO DIỆN UI (MỚI) ---

# --- BLACKJACK (XÌ DÁCH) ---
def create_deck():
    """Tạo một bộ bài 52 lá đã xáo trộn."""
    deck = []
    for suit in CARD_SUITS:
        for rank in CARD_RANKS.keys():
            if rank == 'A': # Blackjack A là 11 hoặc 1
                deck.append({'rank': rank, 'suit': suit, 'value': 11})
            else:
                deck.append({'rank': rank, 'suit': suit, 'value': CARD_RANKS[rank] if CARD_RANKS[rank] < 11 else 10})
    random.shuffle(deck)
    return deck

def calculate_score(hand):
    """Tính điểm, xử lý A (Át)"""
    score = sum(card['value'] for card in hand)
    aces = sum(1 for card in hand if card['rank'] == 'A')
    while score > 21 and aces:
        score -= 10 # Chuyển A từ 11 -> 1
        aces -= 1
    return score

def hand_to_string(hand):
    """Chuyển list bài thành chuỗi text."""
    return " | ".join(f"**{c['rank']}{c['suit']}**" for c in hand)

class BlackjackView(ui.View):
    def __init__(self, author_id, game):
        super().__init__(timeout=300.0) # 5 phút
        self.author_id = author_id
        self.game = game # Tham chiếu đến dict game state

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Chỉ người chơi mới được bấm nút
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Đây không phải ván bài của bạn!", ephemeral=True)
            return False
        return True
        
    async def on_timeout(self):
        if self.author_id in bot.blackjack_games: # Nếu game vẫn còn
            game = bot.blackjack_games.pop(self.author_id)
            embed = game['embed']
            embed.title = "🃏 Xì Dách (Hết giờ) 🃏"
            embed.description = "Bạn đã không phản hồi. Ván bài bị hủy."
            embed.color = discord.Color.dark_grey()
            for item in self.children: item.disabled = True
            await game['message'].edit(embed=embed, view=self)

    async def end_game(self, interaction: discord.Interaction, result_text: str, payout: int):
        """Hàm dọn dẹp và kết thúc game."""
        user_id = self.author_id
        
        # Cập nhật số dư
        new_balance = update_balance(user_id, payout)
        
        # Cập nhật Embed
        embed = self.game['embed']
        embed.title = f"🃏 Xì Dách ({result_text}) 🃏"
        embed.color = discord.Color.green() if payout > 0 else (discord.Color.red() if payout < 0 else discord.Color.light_grey())
        
        # Hiển thị bài của Dealer
        dealer_score = calculate_score(self.game['dealer_hand'])
        embed.set_field_at(0, name=f"Bài Dealer ({dealer_score})", value=hand_to_string(self.game['dealer_hand']), inline=False)
        
        # Hiển thị kết quả
        if payout > 0:
            embed.description = f"🎉 **Bạn thắng {payout} 🪙!**\nSố dư mới: **{new_balance}** 🪙."
        elif payout < 0:
            embed.description = f"😢 **Bạn thua {abs(payout)} 🪙!**\nSố dư mới: **{new_balance}** 🪙."
        else:
            embed.description = f"⚖️ **Hòa (Push)!**\nBạn được hoàn tiền. Số dư: **{new_balance}** 🪙."
            
        # Tắt nút
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Xóa game khỏi state
        bot.blackjack_games.pop(user_id, None)

    @ui.button(label="Rút (Hit)", style=discord.ButtonStyle.primary, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: ui.Button):
        game = self.game
        
        # Rút bài
        game['player_hand'].append(game['deck'].pop())
        player_score = calculate_score(game['player_hand'])
        
        # Cập nhật Embed
        embed = game['embed']
        embed.set_field_at(1, name=f"Bài của bạn ({player_score})", value=hand_to_string(game['player_hand']), inline=False)
        
        if player_score > 21:
            # Quắc (Bust)
            await self.end_game(interaction, "Bạn bị Quắc!", -game['bet'])
        else:
            # Vô hiệu hóa nút Gấp đôi sau khi rút
            self.children[2].disabled = True # Nút Double
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Dằn (Stand)", style=discord.ButtonStyle.secondary, emoji="🛑")
    async def stand(self, interaction: discord.Interaction, button: ui.Button):
        game = self.game
        
        # Lượt của Dealer
        dealer_hand = game['dealer_hand']
        dealer_score = calculate_score(dealer_hand)
        
        while dealer_score < 17:
            dealer_hand.append(game['deck'].pop())
            dealer_score = calculate_score(dealer_hand)
            
        player_score = calculate_score(game['player_hand'])

        # So sánh
        if dealer_score > 21:
            await self.end_game(interaction, "Dealer bị Quắc!", game['bet']) # Thắng 1:1
        elif dealer_score > player_score:
            await self.end_game(interaction, "Dealer thắng!", -game['bet']) # Thua
        elif player_score > dealer_score:
            await self.end_game(interaction, "Bạn thắng!", game['bet']) # Thắng 1:1
        else:
            await self.end_game(interaction, "Hòa!", 0) # Hòa

    @ui.button(label="Gấp đôi (Double)", style=discord.ButtonStyle.success, emoji="✖️2")
    async def double(self, interaction: discord.Interaction, button: ui.Button):
        game = self.game
        user_id = self.author_id
        
        # Kiểm tra xem đủ tiền gấp đôi không
        if get_user_data(user_id)['balance'] < game['bet'] * 2:
            await interaction.response.send_message("Bạn không đủ tiền để Gấp đôi!", ephemeral=True)
            return
            
        # Gấp đôi cược
        game['bet'] *= 2
        
        # Rút 1 lá BẮT BUỘC
        game['player_hand'].append(game['deck'].pop())
        player_score = calculate_score(game['player_hand'])
        
        # Cập nhật Embed
        embed = game['embed']
        embed.set_field_at(1, name=f"Bài của bạn ({player_score})", value=hand_to_string(game['player_hand']), inline=False)
        embed.set_footer(text=f"ĐÃ GẤP ĐÔI! Cược: {game['bet']} 🪙")

        if player_score > 21:
            # Quắc -> Kết thúc game ngay
            await self.end_game(interaction, "Bạn bị Quắc!", -game['bet'])
        else:
            # Tự động Dằn (Stand)
            await self.stand(interaction, button)

@bot.command(name='blackjack', aliases=['bj'])
@commands.check(is_user_in_game) # Check xem có đang chơi game UI không
async def blackjack(ctx, bet_amount: int):
    """Chơi Xì Dách (Blackjack) với bot."""
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    
    # Khởi tạo game
    deck = create_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    player_score = calculate_score(player_hand)
    dealer_score = calculate_score(dealer_hand) # Tính điểm ban đầu
    
    # Tạo Embed
    embed = discord.Embed(title="🃏 Xì Dách 🃏", description="Chọn hành động của bạn.", color=discord.Color.blue())
    # Chỉ hiện 1 lá của dealer
    embed.add_field(name=f"Bài Dealer (?)", value=f"**{dealer_hand[0]['rank']}{dealer_hand[0]['suit']}** | **[ ? ]**", inline=False)
    embed.add_field(name=f"Bài của bạn ({player_score})", value=hand_to_string(player_hand), inline=False)
    embed.set_footer(text=f"Tiền cược: {bet_amount} 🪙")
    
    # Tạo View (Nút bấm)
    view = BlackjackView(user_id, None)
    
    # Xử lý Blackjack (Thắng 1.5x)
    if player_score == 21:
        # Thắng ngay
        winnings = int(bet_amount * 1.5)
        new_balance = update_balance(user_id, winnings)
        embed.title = "🃏 BLACKJACK! 🃏"
        embed.description = f"🎉 **Bạn thắng {winnings} 🪙!**\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.gold()
        embed.set_field_at(0, name=f"Bài Dealer ({dealer_score})", value=hand_to_string(dealer_hand), inline=False)
        for item in view.children: item.disabled = True # Tắt nút
        await ctx.send(embed=embed, view=view)
        return
        
    # Gửi tin nhắn và lưu state
    message = await ctx.send(embed=embed, view=view)
    
    # Lưu state
    game_state = {
        'bet': bet_amount,
        'deck': deck,
        'player_hand': player_hand,
        'dealer_hand': dealer_hand,
        'message': message,
        'embed': embed
    }
    bot.blackjack_games[user_id] = game_state
    view.game = game_state # Cập nhật tham chiếu


# --- MINES (DÒ MÌN) ---

# Hàm tính tổ hợp C(n, k) để tính tỷ lệ
def combinations(n, k):
    if k < 0 or k > n: return 0
    return math.factorial(n) // (math.factorial(k) * math.factorial(n - k))

# Hàm tính Payout cho Dò Mìn
def calculate_mines_payout(gems_revealed, total_bombs):
    total_cells = 25
    # Payout = (C(25, gems) / C(25 - bombs, gems)) * 0.95 (95% Payout)
    numerator = combinations(total_cells, gems_revealed)
    denominator = combinations(total_cells - total_bombs, gems_revealed)
    if denominator == 0: return 1.0 # Trường hợp chia cho 0
    return (numerator / denominator) * 0.95

class MinesButton(ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=x) # \u200b là ký tự trống
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        # Chỉ người chơi mới được bấm
        if interaction.user.id not in bot.mines_games:
            await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        if interaction.user.id != self.view.author_id:
            await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return

        game = bot.mines_games[interaction.user.id]
        
        # Kiểm tra xem lật trúng gì
        index = self.x * 5 + self.y
        if game['grid'][index] == '💣':
            # --- TRÚNG BOM ---
            self.style = discord.ButtonStyle.danger
            self.label = '💣'
            self.disabled = True
            
            # Cập nhật số dư
            new_balance = update_balance(interaction.user.id, -game['bet'])
            
            embed = game['embed']
            embed.title = "💥 BÙM! BẠN ĐÃ THUA! 💥"
            embed.description = f"Bạn lật trúng bom!\nBạn mất **{game['bet']}** 🪙.\nSố dư mới: **{new_balance}** 🪙."
            embed.color = discord.Color.red()
            
            # Tắt game
            self.view.stop_game(show_solution=True)
            await interaction.response.edit_message(embed=embed, view=self.view)
            bot.mines_games.pop(interaction.user.id, None)

        else:
            # --- TRÚNG KIM CƯƠNG ---
            self.style = discord.ButtonStyle.success
            self.label = '💎'
            self.disabled = True
            
            game['revealed_count'] += 1
            
            # Tính Payout mới
            payout = calculate_mines_payout(game['revealed_count'], game['bomb_count'])
            game['current_payout'] = payout
            winnings = int(game['bet'] * (payout - 1)) # Tiền lời
            
            embed = game['embed']
            embed.description = f"Tìm thấy **{game['revealed_count']}** 💎. Lật tiếp hoặc Rút tiền!"
            # Cập nhật nút Cashout
            self.view.children[-1].label = f"Rút tiền ({payout:.2f}x | {winnings} 🪙)"
            
            # Kiểm tra xem thắng tuyệt đối chưa
            if game['revealed_count'] == (25 - game['bomb_count']):
                # Thắng tuyệt đối
                new_balance = update_balance(interaction.user.id, winnings)
                embed.title = "🎉 BẠN ĐÃ THẮNG TUYỆT ĐỐI! 🎉"
                embed.description = f"Bạn đã tìm thấy tất cả {game['revealed_count']} 💎!\nBạn thắng **{winnings}** 🪙.\nSố dư mới: **{new_balance}** 🪙."
                embed.color = discord.Color.gold()
                self.view.stop_game(show_solution=False) # Không cần show, vì đã lật hết
                await interaction.response.edit_message(embed=embed, view=self.view)
                bot.mines_games.pop(interaction.user.id, None)
            else:
                # Vẫn tiếp tục
                await interaction.response.edit_message(embed=embed, view=self.view)

class MinesCashoutButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Rút tiền (1.00x)", row=4)
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id not in bot.mines_games:
            await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
        if interaction.user.id != self.view.author_id:
            await interaction.response.send_message("Đây không phải game của bạn!", ephemeral=True); return
            
        game = bot.mines_games[interaction.user.id]
        
        # Nếu chưa lật ô nào
        if game['revealed_count'] == 0:
            await interaction.response.send_message("Bạn phải lật ít nhất 1 ô!", ephemeral=True)
            return
            
        # Tính tiền thắng
        winnings = int(game['bet'] * (game['current_payout'] - 1)) # Tiền lời
        new_balance = update_balance(interaction.user.id, winnings)
        
        embed = game['embed']
        embed.title = "✅ RÚT TIỀN THÀNH CÔNG ✅"
        embed.description = f"Bạn rút tiền tại **{game['current_payout']:.2f}x**.\nBạn thắng **{winnings}** 🪙.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
        
        # Tắt game
        self.view.stop_game(show_solution=True)
        await interaction.response.edit_message(embed=embed, view=self.view)
        bot.mines_games.pop(interaction.user.id, None)

class MinesView(ui.View):
    def __init__(self, author_id, game):
        super().__init__(timeout=300.0) # 5 phút
        self.author_id = author_id
        
        # Tạo 25 nút (5x5)
        for x in range(4): # Chỉ 4 hàng đầu
            for y in range(5):
                self.add_item(MinesButton(x, y))
        # Hàng cuối cùng (4 nút + 1 nút cashout)
        for y in range(4): 
             self.add_item(MinesButton(4, y))
        self.add_item(MinesCashoutButton()) # Nút thứ 25
        
        # Hàm này để tham chiếu ngược lại game state
        # (cần thiết cho các nút bấm)
        self.game = game

    async def on_timeout(self):
        if self.author_id in bot.mines_games:
            game = bot.mines_games.pop(self.author_id)
            embed = game['embed']
            embed.title = "💣 Dò Mìn (Hết giờ) 💣"
            embed.description = "Bạn đã không phản hồi. Ván game bị hủy. Bạn không mất tiền."
            embed.color = discord.Color.dark_grey()
            self.stop_game(show_solution=False)
            await game['message'].edit(embed=embed, view=self)

    def stop_game(self, show_solution: bool):
        """Tắt tất cả các nút và hiện đáp án."""
        game = self.game
        for i, item in enumerate(self.children):
            item.disabled = True
            if show_solution and isinstance(item, MinesButton):
                if game['grid'][i] == '💣':
                    item.label = '💣'
                    item.style = discord.ButtonStyle.danger
                elif game['grid'][i] == '💎':
                     item.label = '💎'
                     # Giữ style success nếu đã lật, secondary nếu chưa lật
                     if item.style != discord.ButtonStyle.success:
                        item.style = discord.ButtonStyle.secondary

@bot.command(name='mines', aliases=['domin'])
@commands.check(is_user_in_game) # Check xem có đang chơi game UI không
async def mines(ctx, bet_amount: int, bomb_count: int):
    """Chơi Dò Mìn."""
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    
    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return
    if not 1 <= bomb_count <= 24:
        await ctx.send("Số bom phải từ 1 đến 24."); return
        
    # Tạo game grid
    grid = ['💣'] * bomb_count + ['💎'] * (25 - bomb_count)
    random.shuffle(grid)
    
    embed = discord.Embed(title=f"💣 Dò Mìn ({bomb_count} bom) 💣",
                          description="Lật các ô để tìm kim cương 💎. Đừng trúng bom 💣!",
                          color=discord.Color.blue())
    embed.add_field(name="Tiền cược", value=f"**{bet_amount}** 🪙")
    embed.add_field(name="Hệ số", value="1.00x")
    embed.add_field(name="Tiền thắng", value="0 🪙")
    
    game_state = {
        'bet': bet_amount,
        'bomb_count': bomb_count,
        'grid': grid,
        'revealed_count': 0,
        'current_payout': 1.0,
        'message': None, # Sẽ cập nhật
        'embed': embed
    }
    
    view = MinesView(user_id, game_state)
    message = await ctx.send(embed=embed, view=view)
    
    # Cập nhật state
    game_state['message'] = message
    bot.mines_games[user_id] = game_state

# --- CHẠY BOT ---
if TOKEN:
    # Gọi hàm keep_alive để chạy web server
    keep_alive() 
    # Chạy bot Discord
    bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN trong file .env hoặc Secrets")
