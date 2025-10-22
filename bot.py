import discord
from discord.ext import commands
import json
import random
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- Tải Token và Cài đặt Bot ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Cần bật Intents trong Developer Portal
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Bắt buộc để chạy !bangxephang và !chuyenxu

# Tắt lệnh !help mặc định để dùng lệnh tùy chỉnh
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- Định nghĩa hằng số ---
DATA_FILE = 'balances.json'
CODE_FILE = 'codes.json'
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24 # Thời gian chờ !daily

# Định nghĩa các ô trên bàn Roulette
RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]
# 0 là Xanh lá

# --- Quản lý Dữ liệu (Token 🪙) ---

def load_data(filename):
    """Tải dữ liệu từ tệp JSON (balances.json hoặc codes.json)."""
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            json.dump({}, f)
        return {}
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_data(data, filename):
    """Lưu dữ liệu vào tệp JSON (balances.json hoặc codes.json)."""
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

def get_user_data(user_id):
    """Lấy dữ liệu của người dùng, tạo mới nếu chưa có."""
    data = load_data(DATA_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in data:
        # Cấu trúc dữ liệu mới cho người dùng
        data[user_id_str] = {
            'balance': STARTING_TOKENS,
            'last_daily': None, # Dùng cho !daily
            'used_codes': []      # Dùng cho !code
        }
        save_data(data, DATA_FILE)
    
    # Đảm bảo người dùng cũ cũng có các trường dữ liệu mới
    if 'last_daily' not in data[user_id_str]:
        data[user_id_str]['last_daily'] = None
    if 'used_codes' not in data[user_id_str]:
        data[user_id_str]['used_codes'] = []
        
    return data[user_id_str]

def update_balance(user_id, amount):
    """Cập nhật số dư (có thể là số âm để trừ)."""
    data = load_data(DATA_FILE)
    user_id_str = str(user_id)
    
    # Đảm bảo người dùng có tài khoản
    if user_id_str not in data:
        get_user_data(user_id) # Tạo mới nếu chưa có
        data = load_data(DATA_FILE) # Tải lại dữ liệu sau khi tạo

    data[user_id_str]['balance'] += amount
    save_data(data, DATA_FILE)
    return data[user_id_str]['balance']

# --- Sự kiện Bot ---
@bot.event
async def on_ready():
    print(f'Bot {bot.user.name} đã sẵn sàng!')
    print('------')

# --- Lệnh Tùy chỉnh !help ---
@bot.command(name='help')
async def custom_help(ctx):
    """Hiển thị bảng trợ giúp tùy chỉnh."""
    embed = discord.Embed(
        title="Trợ giúp Bot Casino 🎰",
        description="Chào mừng đến với Bot Roulette và các trò chơi khác!",
        color=discord.Color.gold()
    )
    
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

    embed.add_field(
        name="🎰 Lệnh Roulette (`!quay`)",
        value="`!quay <số_tiền> <loại_cược>`\n"
              "**Loại cược (1 ăn 1):**\n"
              "• `đỏ`, `đen`\n"
              "• `lẻ`, `chẵn`\n"
              "• `nửa1` (số 1-18)\n"
              "• `nửa2` (số 19-36)\n"
              "**Loại cược (1 ăn 2):**\n"
              "• `tá1` (số 1-12)\n"
              "• `tá2` (số 13-24)\n"
              "• `tá3` (số 25-36)\n"
              "**Loại cược (1 ăn 35):**\n"
              "• Một số cụ thể (ví dụ: `13`)",
        inline=False
    )
    
    embed.set_footer(text="Chúc bạn may mắn!")
    await ctx.send(embed=embed)


# --- Lệnh Token & Xã hội ---

@bot.command(name='kiemtra', aliases=['balance', 'bal', 'sodu'])
async def balance_check(ctx):
    """Kiểm tra số dư token 🪙."""
    user_data = get_user_data(ctx.author.id)
    bal = user_data['balance']
    await ctx.send(f'🪙 {ctx.author.mention}, bạn đang có **{bal}** token.')

@bot.command(name='daily')
async def daily_reward(ctx):
    """Nhận thưởng token hàng ngày."""
    user_id = ctx.author.id
    user_data = get_user_data(user_id)
    last_daily_str = user_data.get('last_daily')
    
    if last_daily_str:
        last_daily_time = datetime.fromisoformat(last_daily_str)
        cooldown = timedelta(hours=DAILY_COOLDOWN_HOURS)
        
        if datetime.now() < last_daily_time + cooldown:
            time_left = (last_daily_time + cooldown) - datetime.now()
            hours_left = int(time_left.total_seconds() // 3600)
            minutes_left = int((time_left.total_seconds() % 3600) // 60)
            await ctx.send(f'{ctx.author.mention}, bạn cần chờ **{hours_left} giờ {minutes_left} phút** nữa để nhận thưởng.')
            return

    # Cho phép nhận thưởng
    new_balance = update_balance(user_id, DAILY_REWARD)
    
    # Cập nhật thời gian
    data = load_data(DATA_FILE)
    data[str(user_id)]['last_daily'] = datetime.now().isoformat()
    save_data(data, DATA_FILE)
    
    await ctx.send(f'🎉 {ctx.author.mention}, bạn đã nhận được **{DAILY_REWARD}** token thưởng hàng ngày! Số dư mới: **{new_balance}** 🪙.')

@bot.command(name='code')
async def redeem_code(ctx, code_to_redeem: str):
    """Nhập giftcode để nhận thưởng."""
    user_id = ctx.author.id
    user_data = get_user_data(user_id)
    code_to_redeem = code_to_redeem.upper() # Chuyển code về chữ hoa
    
    # Tải danh sách code
    all_codes = load_data(CODE_FILE)
    
    if code_to_redeem not in all_codes:
        await ctx.send(f'Mã `{code_to_redeem}` không tồn tại hoặc đã hết hạn.')
        return
        
    if code_to_redeem in user_data['used_codes']:
        await ctx.send(f'Bạn đã sử dụng mã `{code_to_redeem}` này rồi.')
        return
        
    # Hợp lệ -> Trao thưởng
    reward = all_codes[code_to_redeem]
    new_balance = update_balance(user_id, reward)
    
    # Đánh dấu code đã dùng cho user
    data = load_data(DATA_FILE)
    data[str(user_id)]['used_codes'].append(code_to_redeem)
    save_data(data, DATA_FILE)
    
    # (Tùy chọn) Xóa code nếu muốn nó chỉ dùng 1 lần TRÊN TOÀN SERVER
    # del all_codes[code_to_redeem]
    # save_data(all_codes, CODE_FILE)
    
    await ctx.send(f'🎁 {ctx.author.mention}, bạn đã nhập thành công mã `{code_to_redeem}` và nhận được **{reward}** token! Số dư mới: **{new_balance}** 🪙.')

@bot.command(name='bangxephang', aliases=['top'])
async def leaderboard(ctx, top_n: int = 10):
    """Hiển thị 10 người giàu nhất server."""
    if top_n <= 0:
        top_n = 10
        
    data = load_data(DATA_FILE)
    if not data:
        await ctx.send('Chưa có ai trong bảng xếp hạng.')
        return

    # Sắp xếp data
    # Sắp xếp theo 'balance', xử lý trường hợp user không có 'balance'
    sorted_users = sorted(
        data.items(), 
        key=lambda item: item[1].get('balance', 0), 
        reverse=True
    )
    
    embed = discord.Embed(
        title=f"🏆 Bảng Xếp Hạng {top_n} Đại Gia 🏆",
        color=discord.Color.gold()
    )
    
    rank_count = 1
    for user_id_str, user_data in sorted_users:
        if rank_count > top_n:
            break
            
        balance = user_data.get('balance', 0)
        
        # Lấy tên người dùng
        user = ctx.guild.get_member(int(user_id_str))
        if user:
            user_name = user.display_name
        else:
            user_name = f"Người dùng (ID: ...{user_id_str[-4:]})" # Hiển thị nếu user rời server
        
        embed.add_field(
            name=f"#{rank_count}: {user_name}",
            value=f"**{balance}** 🪙",
            inline=False
        )
        rank_count += 1
        
    await ctx.send(embed=embed)

@bot.command(name='chuyenxu', aliases=['give', 'transfer'])
async def transfer_tokens(ctx, recipient: discord.Member, amount: int):
    """Chuyển token cho người dùng khác. Cú pháp: !chuyenxu @user <số_tiền>"""
    sender_id = ctx.author.id
    recipient_id = recipient.id

    if sender_id == recipient_id:
        await ctx.send('Bạn không thể tự chuyển cho chính mình!')
        return
        
    if amount <= 0:
        await ctx.send('Số tiền chuyển phải lớn hơn 0!')
        return
        
    sender_balance = get_user_data(sender_id)['balance']
    
    if sender_balance < amount:
        await ctx.send(f'Bạn không đủ tiền. Bạn chỉ có **{sender_balance}** 🪙.')
        return
        
    # Thực hiện chuyển
    update_balance(sender_id, -amount)
    new_recipient_balance = update_balance(recipient_id, amount)
    
    await ctx.send(f'✅ {ctx.author.mention} đã chuyển **{amount}** 🪙 cho {recipient.mention}!')
    await recipient.send(f'Bạn đã nhận được **{amount}** 🪙 từ {ctx.author.mention}. Số dư mới: **{new_recipient_balance}** 🪙.')
    
@transfer_tokens.error
async def transfer_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send('Cú pháp sai! `!chuyenxu @TênNgườiDùng <SốTiền>`')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Không tìm thấy người dùng đó hoặc số tiền không hợp lệ.')
    else:
        print(f"Lỗi !chuyenxu: {error}")

# --- Lệnh Trò chơi Mới ---

@bot.command(name='tungxu', aliases=['coinflip'])
async def coinflip(ctx, bet_amount: int, choice: str):
    """Cược tung đồng xu. Cú pháp: !tungxu <số_tiền> <sấp/ngửa>"""
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
        
    # Tung đồng xu
    result = random.choice(['sấp', 'ngửa'])
    
    embed = discord.Embed(
        title=f"Tung đồng xu 🪙... Kết quả là **{result.upper()}**!",
        color=discord.Color.blue()
    )

    if (choice == result) or (choice == 'sap' and result == 'sấp') or (choice == 'ngua' and result == 'ngửa'):
        # Thắng
        new_balance = update_balance(user_id, bet_amount)
        embed.description = f"🎉 Bạn đoán đúng! Bạn thắng **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        # Thua
        new_balance = update_balance(user_id, -bet_amount)
        embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()
        
    await ctx.send(embed=embed)

@bot.command(name='xucxac', aliases=['dice'])
async def dice_roll(ctx, bet_amount: int, guess: int):
    """Cược xúc xắc 1 ăn 5. Cú pháp: !xucxac <số_tiền> <số_đoán (1-6)>"""
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

    # Gieo xúc xắc
    result = random.randint(1, 6)
    
    embed = discord.Embed(
        title=f"Gieo xúc xắc 🎲... Kết quả là **{result}**!",
        color=discord.Color.dark_purple()
    )

    if guess == result:
        # Thắng (1 ăn 5 -> nhận lại vốn + 5 lần cược)
        winnings = bet_amount * 5
        new_balance = update_balance(user_id, winnings)
        embed.description = f"🎉 Chính xác! Bạn thắng **{winnings}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.green()
    else:
        # Thua
        new_balance = update_balance(user_id, -bet_amount)
        embed.description = f"😢 Bạn đoán sai! Bạn mất **{bet_amount}** token.\nSố dư mới: **{new_balance}** 🪙."
        embed.color = discord.Color.red()

    await ctx.send(embed=embed)

# --- Lệnh Roulette (ĐÃ NÂNG CẤP) ---

@bot.command(name='quay', aliases=['roulette'])
async def roulette(ctx, bet_amount: int, bet_type: str):
    """Chơi Roulette (Nâng cao). Cú pháp: !quay <số_tiền> <loại_cược>"""
    
    user_id = ctx.author.id
    balance = get_user_data(user_id)['balance']
    bet_type = bet_type.lower().strip()

    # 1. Kiểm tra tính hợp lệ của cược
    if bet_amount <= 0:
        await ctx.send('Số tiền cược phải lớn hơn 0!')
        return
    if bet_amount > balance:
        await ctx.send(f'Bạn không đủ token. Bạn chỉ có {balance} 🪙.')
        return

    # 2. Quay số
    spin_result = random.randint(0, 36)
    
    # Xác định màu sắc kết quả
    if spin_result == 0:
        spin_color = 'xanh lá 🟩'
    elif spin_result in RED_NUMBERS:
        spin_color = 'đỏ 🟥'
    else:
        spin_color = 'đen ⬛'

    # 3. Kiểm tra thắng/thua
    winnings = 0
    payout_rate = 0 # Tỷ lệ thắng (vd: 1 ăn 1, 1 ăn 2)
    is_win = False

    try:
        # Trường hợp cược vào một SỐ cụ thể (0-36)
        bet_number = int(bet_type)
        if 0 <= bet_number <= 36:
            if spin_result == bet_number:
                payout_rate = 35
                is_win = True
        else:
            await ctx.send('Cược số không hợp lệ. Chỉ cược từ `0` đến `36`.')
            return
            
    except ValueError:
        # Trường hợp cược vào LOẠI
        if bet_type in ['đỏ', 'red']:
            if spin_result in RED_NUMBERS:
                payout_rate = 1
                is_win = True
        elif bet_type in ['đen', 'black']:
            if spin_result in BLACK_NUMBERS:
                payout_rate = 1
                is_win = True
        elif bet_type in ['lẻ', 'odd']:
            if spin_result != 0 and spin_result % 2 != 0:
                payout_rate = 1
                is_win = True
        elif bet_type in ['chẵn', 'even']:
            if spin_result != 0 and spin_result % 2 == 0:
                payout_rate = 1
                is_win = True
        
        # --- Cược Nửa (1 ăn 1) ---
        elif bet_type in ['nửa1', '1-18']:
            if 1 <= spin_result <= 18:
                payout_rate = 1
                is_win = True
        elif bet_type in ['nửa2', '19-36']:
            if 19 <= spin_result <= 36:
                payout_rate = 1
                is_win = True
                
        # --- Cược Tá (1 ăn 2) ---
        elif bet_type in ['tá1', '1-12']:
            if 1 <= spin_result <= 12:
                payout_rate = 2
                is_win = True
        elif bet_type in ['tá2', '13-24']:
            if 13 <= spin_result <= 24:
                payout_rate = 2
                is_win = True
        elif bet_type in ['tá3', '25-36']:
            if 25 <= spin_result <= 36:
                payout_rate = 2
                is_win = True
                
        else:
            await ctx.send('Loại cược không hợp lệ. Gõ `!help` để xem các loại cược.')
            return

    # 4. Xây dựng tin nhắn kết quả
    result_message = f"**Kết quả quay: {spin_result} ({spin_color})**\n\n"
    result_message += f"{ctx.author.mention} đã cược **{bet_amount}** 🪙 vào **{bet_type}**.\n"

    if is_win:
        winnings = bet_amount * payout_rate
        new_balance = update_balance(user_id, winnings)
        result_message += f"🎉 **Bạn đã thắng!** (1 ăn {payout_rate})\nBạn nhận được **{winnings}** token.\n"
        embed_color = discord.Color.green()
    else:
        new_balance = update_balance(user_id, -bet_amount)
        result_message += f"😢 **Bạn đã thua!**\nBạn mất **{bet_amount}** token.\n"
        embed_color = discord.Color.red()
        
    result_message += f"Số dư mới: **{new_balance}** 🪙."

    # Gửi kết quả bằng Embed
    embed = discord.Embed(
        title="Kết Quả Roulette 🎰",
        description=result_message,
        color=embed_color
    )
    await ctx.send(embed=embed)

# --- Xử lý lỗi chung cho các lệnh trò chơi ---
@coinflip.error
@dice_roll.error
@roulette.error
async def game_error(ctx, error):
    """Xử lý lỗi nhập liệu chung cho các trò chơi."""
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f'Cú pháp sai! Gõ `!help` để xem hướng dẫn lệnh `{ctx.command.name}`.')
    elif isinstance(error, commands.BadArgument):
        await ctx.send('Số tiền cược hoặc số đoán phải là một con số hợp lệ.')
    else:
        print(f"Lỗi lệnh {ctx.command.name}: {error}") # In lỗi ra console để debug
        await ctx.send('Đã xảy ra lỗi. Vui lòng thử lại.')

# --- Chạy Bot ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("LỖI: Không tìm thấy DISCORD_TOKEN trong file .env")
