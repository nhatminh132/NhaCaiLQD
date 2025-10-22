import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client # Mới
import typing # Mới

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

# --- Định nghĩa hằng số ---
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24 

# Định nghĩa các ô trên bàn Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

# --- Quản lý Dữ liệu (Supabase) ---

def get_user_data(user_id: int) -> typing.Dict:
    """
    Lấy dữ liệu người dùng từ Supabase.
    Nếu chưa có, tự động tạo mới.
    """
    try:
        # 1. Thử lấy dữ liệu
        response = supabase.table('profiles').select('*').eq('user_id', user_id).execute()
        
        # 2. Nếu không tìm thấy (lần đầu chơi)
        if not response.data:
            print(f"Tạo profile mới cho user {user_id}")
            insert_response = supabase.table('profiles').insert({
                'user_id': user_id,
                'balance': STARTING_TOKENS,
                'last_daily': None,
                'used_codes': []
            }).execute()
            return insert_response.data[0]
            
        # 3. Nếu tìm thấy, trả về
        return response.data[0]

    except Exception as e:
        print(f"Lỗi khi get_user_data cho {user_id}: {e}")
        return None # Trả về None nếu có lỗi nghiêm trọng

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    """
    Sử dụng RPC function 'adjust_balance' để cộng/trừ tiền.
    Đây là cách an toàn, tránh race condition.
    Trả về số dư MỚI.
    """
    try:
        # Gọi hàm 'adjust_balance' đã tạo trong SQL
        response = supabase.rpc('adjust_balance', {
            'user_id_input': user_id,
            'amount_input': amount
        }).execute()
        
        return response.data # Trả về số dư mới
    except Exception as e:
        print(f"Lỗi khi update_balance cho {user_id}: {e}")
        # Nếu lỗi, có thể người dùng chưa có trong DB. Thử tạo
        get_user_data(user_id)
        # Thử lại 1 lần nữa
        try:
            response = supabase.rpc('adjust_balance', {
                'user_id_input': user_id,
                'amount_input': amount
            }).execute()
            return response.data
        except Exception as e2:
            print(f"Lỗi lần 2 khi update_balance: {e2}")
            return None


# --- Sự kiện Bot ---
@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} đã sẵn sàng!')
    print('------')

# --- Lệnh Tùy chỉnh !help ---
@bot.command(name='help')
async def custom_help(ctx):
    # (Giữ nguyên lệnh !help của bạn, không cần thay đổi)
    embed = discord.Embed(
        title="Trợ giúp Bot Casino 🎰 (Phiên bản Supabase)",
        description="Chào mừng đến với Bot Roulette và các trò chơi khác!",
        color=discord.Color.gold()
    )
    # ... (Copy/paste nội dung lệnh !help cũ của bạn vào đây) ...
    embed.add_field(
        name="🪙 Lệnh Cơ bản", 
        value="`!help` - Hiển thị bảng trợ giúp này.\n"
              "`!kiemtra` - (aliases: `!bal`, `!sodu`) Xem số dư token.\n"
              "`!daily` - Nhận thưởng token hàng ngày.\n"
              "`!code <mã>` - Nhập giftcode nhận thưởng.\n"
              "`!chuyenxu @user <số_tiền>` - Chuyển token cho người khác.\n"
              "`!bangxephang` - (aliases: `!top`) Xem 10 người giàu nhất.",
        inline=False
    )
    
    embed.add_field(
        name="🎲 Trò chơi",
        value="`!tungxu <số_tiền> <sấp/ngửa>` - (aliases: `!coinflip`) Cược 50/50.\n"
              "`!xucxac <số_tiền> <số_đoán>` - (aliases: `!dice`) Cược đoán số (1-6), thắng 1 ăn 5.",
        inline=False
    )
    # ...
    await ctx.send(embed=embed)


# --- Lệnh Token & Xã hội (ĐÃ CẬP NHẬT) ---

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
        # Chuyển đổi chuỗi ISO (Supabase trả về) thành datetime object
        # Supabase trả về dạng "2023-10-27T10:00:00+00:00"
        last_daily_time = datetime.fromisoformat(user_data['last_daily'])
        cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        
        # So sánh với múi giờ UTC
        if datetime.now(timezone.utc) < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now(timezone.utc)
            hours_left = int(time_left.total_seconds() // 3600)
            minutes_left = int((time_left.total_seconds() % 3600) // 60)
            await ctx.send(f'{ctx.author.mention}, bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa.')
            return

    # Cho phép nhận thưởng (Dùng RPC)
    new_balance = update_balance(user_id, DAILY_REWARD)
    
    # Cập nhật thời gian
    try:
        supabase.table('profiles').update({
            'last_daily': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).execute()
        
        await ctx.send(f'🎉 {ctx.author.mention}, bạn đã nhận được **{DAILY_REWARD}** token! Số dư mới: **{new_balance}** 🪙.')
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi khi cập nhật thời gian: {e}')

@bot.command(name='code')
async def redeem_code(ctx, code_to_redeem: str):
    user_id = ctx.author.id
    user_data = get_user_data(user_id)
    code_to_redeem = code_to_redeem.upper()
    
    # 1. Kiểm tra code có tồn tại trong DB không
    try:
        code_response = supabase.table('gift_codes').select('*').eq('code', code_to_redeem).execute()
        if not code_response.data:
            await ctx.send(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.')
            return
    except Exception as e:
        await ctx.send(f'Lỗi khi kiểm tra code: {e}')
        return
        
    # 2. Kiểm tra user đã dùng code này chưa (trong mảng 'used_codes')
    if code_to_redeem in user_data['used_codes']:
        await ctx.send(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.')
        return
        
    # 3. Hợp lệ -> Trao thưởng
    reward = code_response.data[0]['reward']
    new_balance = update_balance(user_id, reward)
    
    # 4. Thêm code này vào danh sách đã dùng của user
    try:
        new_code_list = user_data['used_codes'] + [code_to_redeem]
        supabase.table('profiles').update({
            'used_codes': new_code_list
        }).eq('user_id', user_id).execute()
        
        await ctx.send(f'🎁 {ctx.author.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward}** token! Số dư mới: **{new_balance}** 🪙.')
        
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi khi cập nhật code đã dùng: {e}')

@bot.command(name='bangxephang', aliases=['top'])
async def leaderboard(ctx, top_n: int = 10):
    if top_n <= 0:
        top_n = 10
        
    try:
        # Lấy top 10 người, sắp xếp theo 'balance'
        response = supabase.table('profiles').select('user_id', 'balance') \
            .order('balance', desc=True) \
            .limit(top_n) \
            .execute()
            
        if not response.data:
            await ctx.send('Chưa có ai trong bảng xếp hạng.')
            return

        embed = discord.Embed(
            title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆",
            color=discord.Color.gold()
        )
        
        rank_count = 1
        for user_data in response.data:
            user = ctx.guild.get_member(user_data['user_id'])
            if user:
                user_name = user.display_name
            else:
                user_name = f"Người dùng (ID: ...{str(user_data['user_id'])[-4:]})"
            
            embed.add_field(
                name=f"#{rank_count}: {user_name}",
                value=f"**{user_data['balance']}** 🪙",
                inline=False
            )
            rank_count += 1
            
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f'Lỗi khi lấy bảng xếp hạng: {e}')

@bot.command(name='chuyenxu', aliases=['give', 'transfer'])
async def transfer_tokens(ctx, recipient: discord.Member, amount: int):
    sender_id = ctx.author.id
    recipient_id = recipient.id

    if sender_id == recipient_id:
        await ctx.send('Bạn không thể tự chuyển cho chính mình!')
        return
    if amount <= 0:
        await ctx.send('Số tiền chuyển phải lớn hơn 0!')
        return
        
    sender_data = get_user_data(sender_id)
    
    if sender_data['balance'] < amount:
        await ctx.send(f'Bạn không đủ tiền. Bạn chỉ có **{sender_data["balance"]}** 🪙.')
        return
        
    # Thực hiện chuyển (2 lần gọi RPC)
    # Đây không phải là một "transaction" hoàn hảo, nhưng đủ tốt cho bot này
    try:
        update_balance(sender_id, -amount) # Trừ tiền người gửi
        new_recipient_balance = update_balance(recipient_id, amount) # Cộng tiền người nhận
        
        await ctx.send(f'✅ {ctx.author.mention} đã chuyển **{amount}** 🪙 cho {recipient.mention}!')
        # (Tùy chọn) Gửi DM cho người nhận
        # await recipient.send(f'Bạn đã nhận được **{amount}** 🪙 từ {ctx.author.mention}. Số dư mới: **{new_recipient_balance}** 🪙.')
    except Exception as e:
        await ctx.send(f'Đã xảy ra lỗi trong quá trình chuyển: {e}')
    
@transfer_tokens.error
async def transfer_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Cú pháp sai! `!chuyenxu @TênNgườiDùng <SốTiền>`')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Không tìm thấy người dùng đó hoặc số tiền không hợp lệ.')
    else:
        print(f"Lỗi !chuyenxu: {error}")

# --- Lệnh Trò chơi Mới (ĐÃ CẬP NHẬT) ---

@bot.command(name='tungxu', aliases=['coinflip'])
async def coinflip(ctx, bet_amount: int, choice: str):
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    choice = choice.lower().strip()

    if choice not in ['sấp', 'ngửa', 'sap', 'ngua']:
        await ctx.send('Cú pháp sai! Phải cược `sấp` hoặc `ngửa`.')
        return
    if bet_amount <= 0:
        await ctx.send('Số tiền cược phải lớn hơn 0!')
        return
    if bet_amount > balance:
        await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.')
        return
        
    result = random.choice(['sấp', 'ngửa'])
    embed = discord.Embed(title=f"Tung đồng xu 🪙... Kết quả là **{result.upper()}**!")

    if (choice == result) or (choice == 'sap' and result == 'sấp') or (choice == 'ngua' and result == 'ngửa'):
        new_balance = update_balance(user_id, bet_amount) # Thắng
        embed.description = f"🎉 Bạn đoán đúng! Bạn thắng **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount) # Thua
        embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()
        
    await ctx.send(embed=embed)

@bot.command(name='xucxac', aliases=['dice'])
async def dice_roll(ctx, bet_amount: int, guess: int):
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']

    if not 1 <= guess <= 6:
        await ctx.send('Cú pháp sai! Phải đoán một số từ `1` đến `6`.')
        return
    if bet_amount <= 0:
        await ctx.send('Số tiền cược phải lớn hơn 0!')
        return
    if bet_amount > balance:
        await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.')
        return

    result = random.randint(1, 6)
    embed = discord.Embed(title=f"Gieo xúc xắc 🎲... Kết quả là **{result}**!")

    if guess == result:
        winnings = bet_amount * 5 # 1 ăn 5
        new_balance = update_balance(user_id, winnings)
        embed.description = f"🎉 Chính xác! Bạn thắng **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount) # Thua
        embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()

    await ctx.send(embed=embed)

# --- Lệnh Roulette (ĐÃ CẬP NHẬT) ---

@bot.command(name='quay', aliases=['roulette'])
async def roulette(ctx, bet_amount: int, bet_type: str):
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    bet_type = bet_type.lower().strip()

    if bet_amount <= 0: await ctx.send('Số tiền cược phải lớn hơn 0!'); return
    if bet_amount > balance: await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.'); return

    spin_result = random.randint(0, 36)
    spin_color = 'xanh lá 🟩' if spin_result == 0 else ('đỏ 🟥' if spin_result in RED_NUMBERS else 'đen ⬛')

    winnings = 0
    payout_rate = 0 
    is_win = False
    
    # (Phần logic game này giữ nguyên, không cần đổi)
    try:
        bet_number = int(bet_type)
        if 0 <= bet_number <= 36:
            if spin_result == bet_number: payout_rate = 35; is_win = True
        else: await ctx.send('Cược số không hợp lệ. Chỉ cược từ `0` đến `36`.'); return
    except ValueError:
        if bet_type in ['đỏ', 'red']:
            if spin_result in RED_NUMBERS: payout_rate = 1; is_win = True
        elif bet_type in ['đen', 'black']:
            if spin_result in BLACK_NUMBERS: payout_rate = 1; is_win = True
        elif bet_type in ['lẻ', 'odd']:
            if spin_result != 0 and spin_result % 2 != 0: payout_rate = 1; is_win = True
        elif bet_type in ['chẵn', 'even']:
            if spin_result != 0 and spin_result % 2 == 0: payout_rate = 1; is_win = True
        elif bet_type in ['nửa1', '1-18']:
            if 1 <= spin_result <= 18: payout_rate = 1; is_win = True
        elif bet_type in ['nửa2', '19-36']:
            if 19 <= spin_result <= 36: payout_rate = 1; is_win = True
        elif bet_type in ['tá1', '1-12']:
            if 1 <= spin_result <= 12: payout_rate = 2; is_win = True
        elif bet_type in ['tá2', '13-24']:
            if 13 <= spin_result <= 24: payout_rate = 2; is_win = True
        elif bet_type in ['tá3', '25-36']:
            if 25 <= spin_result <= 36: payout_rate = 2; is_win = True
        else: await ctx.send('Loại cược không hợp lệ. Gõ `!help` để xem các loại cược.'); return

    # Xây dựng tin nhắn kết quả
    result_message = f"**Kết quả quay: {spin_result} ({spin_color})**\n\n"
    result_message += f"{ctx.author.mention} đã cược **{bet_amount}** 🪙 vào **{bet_type}**.\n"

    if is_win:
        winnings = bet_amount * payout_rate
        new_balance = update_balance(user_id, winnings) # Cộng tiền
        result_message += f"🎉 **Bạn đã thắng!** (1 ăn {payout_rate})\nBạn nhận được **{winnings}** token.\n"
        embed_color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount) # Trừ tiền
        result_message += f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount}** token.\n"
        embed_color = discord.Color.red()
        
    result_message += f"Số dư mới: **{new_balance}** 🪙."
    
    embed = discord.Embed(title="Kết Quả Roulette 🎰", description=result_message, color=embed_color)
    await ctx.send(embed=embed)

# --- Xử lý lỗi chung ---
@coinflip.error
@dice_roll.error
@roulette.error
async def game_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Cú pháp sai! Gõ `!help` để xem hướng dẫn lệnh `{ctx.command.name}`.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Số tiền cược hoặc số đoán phải là một con số hợp lệ.')
    else:
        print(f"Lỗi lệnh {ctx.command.name}: {error}")
        await ctx.send('Đã xảy ra lỗi. Vui lòng thử lại.')

# --- Chạy Bot ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN trong file .env hoặc Secrets")
