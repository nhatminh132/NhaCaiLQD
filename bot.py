# bot.py
# -*- coding: utf-8 -*-
"""
Bot Discord: casino mini (slash commands)
Bao gồm: /balance, /daily, /code, /top, /chuyenxu, /profile, admin group,
và games: /slots, /hilo, /tungxu, /xucxac, /baucua, /duangua, /quay (roulette), /baccarat
Tương thích với Supabase (nếu cấu hình biến môi trường).
"""
import os
import random
import typing
import asyncio
import re
from datetime import datetime, timedelta, date, timezone, time as dtime

import discord
from discord.ext import commands, tasks
from discord import app_commands

from dotenv import load_dotenv

# Optional: supabase (if not available thì bạn phải thay hàm DB)
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except Exception:
    HAS_SUPABASE = False

import pytz

# ---- CẤU HÌNH ----
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    print("LỖI: Cần biến môi trường DISCORD_TOKEN")
    exit(1)

# Supabase client (nếu có)
supabase = None
if HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    if HAS_SUPABASE:
        print("Chú ý: SUPABASE_URL hoặc SUPABASE_KEY không cấu hình - DB supabase sẽ không hoạt động.")
    else:
        print("Chú ý: Thư viện supabase chưa cài - DB supabase sẽ không hoạt động.")

# ---- HẰNG SỐ & CÀI ĐẶT ----
STARTING_TOKENS = 100
DAILY_REWARD = 50
DAILY_COOLDOWN_HOURS = 24
ADMIN_ROLE = "Bot Admin"
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

# Roulette
RED_NUMBERS = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
BLACK_NUMBERS = [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]
ROULETTE_PAYOUTS = {'single':35, 'split':17, 'street':11, 'corner':8, 'sixline':5, 'dozen':2, 'column':2, 'color':1, 'evenodd':1, 'half':1}

# Slots
SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL = [s for s,w,p in SLOT_SYMBOLS]
SLOT_WEIGHTS = [w for s,w,p in SLOT_SYMBOLS]
SLOT_PAYOUTS = {s:p for s,w,p in SLOT_SYMBOLS}

# Cards
CARD_SUITS = ['♥️', '♦️', '♣️', '♠️']
CARD_RANKS_BACCARAT = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':0,'J':0,'Q':0,'K':0,'A':1}
CARD_RANKS_HILO = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}

# Race
NUM_HORSES = 6
RACE_LENGTH = 20

# Globals
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# In-memory placeholders for game locks
bot.users_in_animation = set()

# -------------------------
# ---- DATABASE HELPERS ---
# -------------------------
def _ensure_profile_defaults(data: dict) -> dict:
    if data is None:
        return None
    data.setdefault('balance', STARTING_TOKENS)
    data.setdefault('last_daily', None)
    data.setdefault('used_codes', [])
    data.setdefault('total_bet', 0)
    data.setdefault('total_won', 0)
    data.setdefault('games_played', 0)
    data.setdefault('daily_streak', 0)
    data.setdefault('last_streak_date', None)
    return data

def get_user_data(user_id: int) -> typing.Optional[dict]:
    """Lấy user từ supabase; nếu không tồn tại tạo mới.
    Nếu supabase không cấu hình - dùng giả lập trả default dict (không lưu lâu dài)."""
    if supabase is None:
        # WARNING: volatile in-memory fallback (not persistent)
        return {'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': [], 'total_bet':0, 'total_won':0, 'games_played':0, 'daily_streak':0, 'last_streak_date': None}
    try:
        resp = supabase.table('profiles').select('*').eq('user_id', user_id).maybe_single().execute()
        data = resp.data
        if not data:
            # create new
            insert = supabase.table('profiles').insert({'user_id': user_id, 'balance': STARTING_TOKENS, 'last_daily': None, 'used_codes': [], 'total_bet':0, 'total_won':0, 'games_played':0, 'daily_streak':0, 'last_streak_date': None}).execute()
            return _ensure_profile_defaults(insert.data[0])
        return _ensure_profile_defaults(data)
    except Exception as e:
        print("DB get_user_data error:", e)
        return None

def update_balance(user_id: int, amount: int) -> typing.Optional[int]:
    """Thêm/trừ balance (amount có thể âm). Trả về số dư mới hoặc None nếu lỗi."""
    if supabase is None:
        # Volatile fallback: cannot persist; just return simulated new balance
        # NOTE: This fallback is not safe: in real usage, configure Supabase.
        return None
    try:
        # Nếu bạn đã có RPC function adjust_balance, tốt. Nếu không, thực hiện đọc-ghi an toàn.
        # Thử gọi RPC đầu tiên
        try:
            resp = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
            return resp.data
        except Exception:
            # Fallback: read current, update
            resp = supabase.table('profiles').select('balance').eq('user_id', user_id).maybe_single().execute()
            cur = resp.data.get('balance', STARTING_TOKENS) if resp.data else STARTING_TOKENS
            new = max(0, cur + amount)
            supabase.table('profiles').update({'balance': new}).eq('user_id', user_id).execute()
            return new
    except Exception as e:
        print("DB update_balance error:", e)
        return None

def update_profile_stats(user_id: int, bet_amount: int, net_gain: int):
    """Cập nhật chỉ số tổng (không bắt buộc chính xác)."""
    if supabase is None: return
    try:
        # Lấy, cập nhật cục bộ rồi ghi
        resp = supabase.table('profiles').select('*').eq('user_id', user_id).maybe_single().execute()
        data = resp.data or {}
        total_bet = data.get('total_bet', 0) + bet_amount
        total_won = data.get('total_won', 0) + max(0, net_gain)
        games_played = data.get('games_played', 0) + 1
        supabase.table('profiles').update({'total_bet': total_bet, 'total_won': total_won, 'games_played': games_played}).eq('user_id', user_id).execute()
    except Exception as e:
        print("DB update_profile_stats error:", e)

# -------------------------
# ---- UTIL & HELPERS -----
# -------------------------
global_cooldown = commands.CooldownMapping.from_cooldown(30, 60.0, commands.BucketType.default)
def global_rate_limit():
    async def predicate(interaction: discord.Interaction):
        bucket = global_cooldown.get_bucket(interaction)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise app_commands.CommandOnCooldown(bucket, retry_after)
        return True
    return app_commands.check(predicate)

def is_user_not_in_game():
    async def predicate(interaction: discord.Interaction):
        uid = interaction.user.id
        if uid in bot.users_in_animation:
            raise app_commands.CheckFailure("Bạn đang trong một game khác.")
        return True
    return app_commands.check(predicate)

def fmt_num(n: int) -> str:
    return f"{n:,}"

# -------------------------
# ---- EVENTS & ERRORS ----
# -------------------------
@bot.event
async def on_ready():
    print(f"Bot ready: {bot.user} (id: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print("Sync error:", e)

@bot.event
async def on_application_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    orig = getattr(error, 'original', error)
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"⏳ Vui lòng đợi {error.retry_after:.1f}s.", ephemeral=True)
    elif isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("Bạn không có quyền dùng lệnh này.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message(str(orig), ephemeral=True)
    else:
        print("Unhandled command error:", orig)
        try:
            await interaction.response.send_message("Đã xảy ra lỗi trong lệnh.", ephemeral=True)
        except:
            pass

# -------------------------
# ---- SLASH COMMANDS -----
# -------------------------
@bot.slash_command(name="kiemtra", description="Kiểm tra số dư token của bạn.")
@global_rate_limit()
async def balance_check_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_data = get_user_data(interaction.user.id)
    if not user_data:
        await interaction.followup.send("Lỗi khi lấy dữ liệu.")
        return
    await interaction.followup.send(f'🪙 {interaction.user.mention}, bạn có **{fmt_num(user_data.get("balance",0))}** token.')

@bot.slash_command(name="daily", description="Nhận thưởng hàng ngày.")
@global_rate_limit()
@is_user_not_in_game()
async def daily_reward_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    user_data = get_user_data(uid)
    if not user_data:
        await interaction.followup.send("Lỗi DB.")
        return

    now = datetime.now(timezone.utc)
    last_daily_iso = user_data.get('last_daily')
    can_claim = True
    if last_daily_iso:
        try:
            last_dt = datetime.fromisoformat(last_daily_iso)
            if now < last_dt + timedelta(hours=DAILY_COOLDOWN_HOURS):
                remaining = (last_dt + timedelta(hours=DAILY_COOLDOWN_HOURS)) - now
                hrs = int(remaining.total_seconds()//3600)
                mins = int((remaining.total_seconds()%3600)//60)
                await interaction.followup.send(f"Bạn cần chờ {hrs} giờ {mins} phút nữa.", ephemeral=True)
                return
        except Exception:
            pass

    # Streak logic
    today_vi = datetime.now(VIETNAM_TZ).date()
    last_streak_date = user_data.get('last_streak_date')
    if last_streak_date:
        try:
            last_date = date.fromisoformat(last_streak_date)
            if last_date == today_vi:
                new_streak = user_data.get('daily_streak',0)
            elif last_date == (today_vi - timedelta(days=1)):
                new_streak = user_data.get('daily_streak',0) + 1
            else:
                new_streak = 1
        except Exception:
            new_streak = 1
    else:
        new_streak = 1
    streak_bonus = min(new_streak * 10, 100)
    total_reward = DAILY_REWARD + streak_bonus

    new_bal = update_balance(uid, total_reward)
    if new_bal is None:
        await interaction.followup.send("Lỗi cập nhật số dư.", ephemeral=True)
        return
    # cập nhật last_daily, streak
    if supabase:
        try:
            supabase.table('profiles').update({'last_daily': now.isoformat(), 'daily_streak': new_streak, 'last_streak_date': str(today_vi)}).eq('user_id', uid).execute()
        except:
            pass

    await interaction.followup.send(f"🎉 {interaction.user.mention}, bạn nhận **{fmt_num(total_reward)}** token! (Streak: {new_streak} ngày). Số dư mới: **{fmt_num(new_bal)}**.")

@bot.slash_command(name="code", description="Đổi giftcode.")
@app_commands.describe(code_to_redeem="Mã bạn muốn nhập")
@global_rate_limit()
@is_user_not_in_game()
async def redeem_code_slash(interaction: discord.Interaction, code_to_redeem: str):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    user_data = get_user_data(uid)
    if not user_data:
        await interaction.followup.send("Lỗi DB.")
        return
    code = code_to_redeem.strip().upper()
    if supabase is None:
        await interaction.followup.send("Chức năng giftcode cần Supabase.", ephemeral=True)
        return
    try:
        resp = supabase.table('gift_codes').select('*').eq('code', code).maybe_single().execute()
        if not resp.data:
            await interaction.followup.send("Mã không tồn tại hoặc hết hạn.", ephemeral=True); return
        if code in user_data.get('used_codes', []):
            await interaction.followup.send("Bạn đã dùng mã này rồi.", ephemeral=True); return
        reward = resp.data['reward']
        newbal = update_balance(uid, reward)
        if newbal is None:
            await interaction.followup.send("Lỗi cập nhật số dư.", ephemeral=True); return
        # Update used_codes
        used = user_data.get('used_codes', []) + [code]
        supabase.table('profiles').update({'used_codes': used}).eq('user_id', uid).execute()
        await interaction.followup.send(f"🎁 Nhận thành công **{fmt_num(reward)}** token! Số dư mới: **{fmt_num(newbal)}**.")
    except Exception as e:
        print("Redeem code error:", e)
        await interaction.followup.send("Lỗi khi nhập code.", ephemeral=True)

@bot.slash_command(name="top", description="Xem bảng xếp hạng (top N).")
@app_commands.describe(top_n="Số lượng muốn xem")
@global_rate_limit()
async def leaderboard_slash(interaction: discord.Interaction, top_n: int = 10):
    await interaction.response.defer()
    if supabase is None:
        await interaction.followup.send("Chức năng cần Supabase.", ephemeral=True); return
    top_n = max(1, min(top_n, 25))
    try:
        resp = supabase.table('profiles').select('user_id', 'balance').order('balance', desc=True).limit(top_n).execute()
        if not resp.data:
            await interaction.followup.send("Chưa có dữ liệu.", ephemeral=True); return
        embed = discord.Embed(title=f"🏆 Top {top_n} Đại Gia", color=discord.Color.gold())
        rank = 1
        for row in resp.data:
            embed.add_field(name=f"#{rank} - <@{row['user_id']}>", value=f"**{fmt_num(row.get('balance',0))}** 🪙", inline=False)
            rank += 1
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Leaderboard error:", e)
        await interaction.followup.send("Lỗi lấy bảng xếp hạng.", ephemeral=True)

@bot.slash_command(name="chuyenxu", description="Chuyển token cho người khác.")
@app_commands.describe(recipient="Người nhận", amount="Số token")
@global_rate_limit()
@is_user_not_in_game()
async def transfer_tokens_slash(interaction: discord.Interaction, recipient: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    sender = interaction.user
    if recipient.id == sender.id:
        await interaction.followup.send("Bạn không thể tự chuyển cho mình.", ephemeral=True); return
    if amount <= 0:
        await interaction.followup.send("Số tiền phải > 0.", ephemeral=True); return
    sender_data = get_user_data(sender.id)
    if not sender_data:
        await interaction.followup.send("Lỗi DB.", ephemeral=True); return
    if sender_data.get('balance',0) < amount:
        await interaction.followup.send(f"Bạn không đủ tiền (còn {fmt_num(sender_data.get('balance',0))}).", ephemeral=True); return
    sb = update_balance(sender.id, -amount)
    if sb is None:
        await interaction.followup.send("Lỗi trừ tiền.", ephemeral=True); return
    rb = update_balance(recipient.id, amount)
    if rb is None:
        # try rollback
        update_balance(sender.id, amount)
        await interaction.followup.send("Lỗi cộng tiền người nhận. Giao dịch hủy.", ephemeral=True); return
    await interaction.followup.send(f"✅ Đã chuyển **{fmt_num(amount)}** 🪙 cho {recipient.mention}.", ephemeral=True)

@bot.slash_command(name="profile", description="Xem hồ sơ bạn hoặc thành viên khác.")
@app_commands.describe(member="Thành viên (để trống = bạn)")
@global_rate_limit()
async def profile_slash(interaction: discord.Interaction, member: typing.Optional[discord.Member] = None):
    await interaction.response.defer()
    target = member or interaction.user
    data = get_user_data(target.id)
    if not data:
        await interaction.followup.send("Không tìm thấy dữ liệu.", ephemeral=True); return
    bal = data.get('balance',0)
    embed = discord.Embed(title=f"📊 Hồ sơ {target.display_name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="💰 Số dư", value=f"**{fmt_num(bal)}** 🪙", inline=True)
    embed.add_field(name="🔥 Chuỗi Daily", value=f"{data.get('daily_streak',0)} ngày", inline=True)
    embed.add_field(name="🎲 Game đã chơi", value=f"{fmt_num(data.get('games_played',0))}", inline=False)
    embed.add_field(name="📈 Tổng cược", value=f"{fmt_num(data.get('total_bet',0))} 🪙", inline=False)
    embed.add_field(name="🏆 Tổng thắng", value=f"{fmt_num(data.get('total_won',0))} 🪙", inline=False)
    await interaction.followup.send(embed=embed)

# -------------------------
# ---- ADMIN COMMANDS -----
# -------------------------
admin_group = app_commands.Group(name="admin", description="Lệnh admin", guild_only=True)

@admin_group.command(name="give", description="Cộng/trừ token cho người dùng.")
@app_commands.describe(member="Thành viên", amount="Số token (+/-)")
@global_rate_limit()
async def admin_give_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    # Check role
    has = any(r.name == ADMIN_ROLE for r in interaction.user.roles)
    if not has:
        await interaction.response.send_message("Bạn không có quyền Admin.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    nb = update_balance(member.id, amount)
    if nb is None:
        await interaction.followup.send("Lỗi cập nhật số dư.", ephemeral=True); return
    await interaction.followup.send(f"✅ Đã cập nhật {member.mention} lên **{fmt_num(nb)}** 🪙.", ephemeral=True)

@admin_group.command(name="set", description="Set số dư chính xác cho user.")
@app_commands.describe(member="Thành viên", amount="Số dư đặt")
@global_rate_limit()
async def admin_set_slash(interaction: discord.Interaction, member: discord.Member, amount: int):
    has = any(r.name == ADMIN_ROLE for r in interaction.user.roles)
    if not has:
        await interaction.response.send_message("Bạn không có quyền Admin.", ephemeral=True); return
    if supabase is None:
        await interaction.response.send_message("Cần Supabase để set balance.", ephemeral=True); return
    await interaction.response.defer(ephemeral=True)
    try:
        supabase.rpc('set_balance', {'user_id_input': member.id, 'amount_input': amount}).execute()
        await interaction.followup.send(f"✅ Đã set {member.mention} = **{fmt_num(amount)}** 🪙", ephemeral=True)
    except Exception as e:
        print("admin set error:", e)
        await interaction.followup.send("Lỗi khi set balance.", ephemeral=True)

bot.tree.add_command(admin_group)

# -------------------------
# ---- GAMES: SLOTS ------
# -------------------------
@bot.slash_command(name="slots", description="Chơi máy xèng.")
@app_commands.describe(bet_amount="Số token cược")
@global_rate_limit()
@is_user_not_in_game()
async def slots_slash(interaction: discord.Interaction, bet_amount: int):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user:
        await interaction.response.send_message("Lỗi DB.", ephemeral=True); return
    if bet_amount <= 0:
        await interaction.response.send_message("Cược phải > 0.", ephemeral=True); return
    if user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Bạn không đủ token.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        result = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
        embed = discord.Embed(title="🎰 Máy Xèng 🎰", description="| - | - | - |", color=discord.Color.blue())
        embed.set_footer(text=f"{interaction.user.display_name} cược {fmt_num(bet_amount)} 🪙")
        msg = await interaction.followup.send(embed=embed, wait=True)

        # Animation
        await asyncio.sleep(1.2)
        embed.description = f"| {result[0]} | - | - |"; await msg.edit(embed=embed)
        await asyncio.sleep(1.2)
        embed.description = f"| {result[0]} | {result[1]} | - |"; await msg.edit(embed=embed)
        await asyncio.sleep(1.2)
        embed.description = f"| {result[0]} | {result[1]} | {result[2]} |"; await msg.edit(embed=embed)

        winnings = 0
        if result[0] == result[1] == result[2]:
            if result[0] == '7️⃣':
                # jackpot: simple fixed
                winnings = bet_amount * SLOT_PAYOUTS[result[0]] * 10
            else:
                winnings = bet_amount * SLOT_PAYOUTS[result[0]]
        elif result[0] == result[1] or result[1] == result[2]:
            winnings = bet_amount  # 1:1 for any pair

        payout = winnings if winnings > 0 else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)

        if winnings > 0:
            embed.color = discord.Color.green()
            embed.description += f"\n\n🎉 Bạn thắng **{fmt_num(winnings)}** 🪙!\nSố dư mới: **{fmt_num(newbal)}** 🪙"
        else:
            embed.color = discord.Color.red()
            embed.description += f"\n\n😢 Bạn thua **{fmt_num(bet_amount)}** 🪙.\nSố dư mới: **{fmt_num(newbal)}** 🪙"
        await msg.edit(embed=embed)

    except Exception as e:
        print("Slots error:", e)
        try:
            await interaction.followup.send("Lỗi khi chơi Slots.", ephemeral=True)
        except:
            pass
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- GAME: HILO (Cao/Thấp) ----
# -------------------------
@bot.slash_command(name="hilo", description="Đoán lá bài tiếp theo cao hay thấp.")
@app_commands.describe(bet_amount="Số token", choice="Cao/Thấp")
@app_commands.choices(choice=[app_commands.Choice(name="Cao", value="cao"), app_commands.Choice(name="Thấp", value="thấp")])
@global_rate_limit()
@is_user_not_in_game()
async def hilo_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user:
        await interaction.response.send_message("Lỗi DB.", ephemeral=True); return
    if bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Số tiền không hợp lệ hoặc không đủ.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        rank1 = random.choice(list(CARD_RANKS_HILO.keys())); suit1 = random.choice(CARD_SUITS); val1 = CARD_RANKS_HILO[rank1]
        rank2 = random.choice(list(CARD_RANKS_HILO.keys())); suit2 = random.choice(CARD_SUITS); val2 = CARD_RANKS_HILO[rank2]

        embed = discord.Embed(title="⬆️ Cao hay Thấp ⬇️", color=discord.Color.blue())
        embed.add_field(name="Lá 1", value=f"**{rank1}{suit1}** (Giá trị: {val1})", inline=False)
        embed.add_field(name="Bạn cược", value=f"**{fmt_num(bet_amount)}** vào **{choice.upper()}**", inline=False)
        embed.add_field(name="Lá 2", value=f"**{rank2}{suit2}** (Giá trị: {val2})", inline=False)

        is_win = False
        if val2 > val1 and choice == 'cao': is_win = True
        if val2 < val1 and choice == 'thấp': is_win = True
        # tie => lose
        payout = bet_amount if is_win else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)

        if is_win:
            embed.color = discord.Color.green()
            embed.description = f"🎉 Bạn thắng! Số dư mới: **{fmt_num(newbal)}**"
        else:
            embed.color = discord.Color.red()
            embed.description = f"😢 Bạn thua. Số dư mới: **{fmt_num(newbal)}**"
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print("Hilo error:", e)
        await interaction.response.send_message("Lỗi khi chơi Hilo.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- COINFLIP ----
# -------------------------
@bot.slash_command(name="tungxu", description="Tung xu (sấp/ngửa).")
@app_commands.describe(bet_amount="Số token", choice="Sấp/Ngửa")
@app_commands.choices(choice=[app_commands.Choice(name="Sấp", value="sấp"), app_commands.Choice(name="Ngửa", value="ngửa")])
@global_rate_limit()
@is_user_not_in_game()
async def coinflip_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        res = random.choice(['sấp','ngửa'])
        is_win = (res == choice)
        payout = bet_amount if is_win else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)
        title = f"🪙 Kết quả: {res.upper()}!"
        embed = discord.Embed(title=title, color=(discord.Color.green() if is_win else discord.Color.red()))
        if is_win:
            embed.description = f"🎉 Bạn đoán đúng! +{fmt_num(bet_amount)} 🪙\nSố dư: **{fmt_num(newbal)}**"
        else:
            embed.description = f"😢 Bạn đoán sai. -{fmt_num(bet_amount)} 🪙\nSố dư: **{fmt_num(newbal)}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Coinflip error:", e)
        await interaction.followup.send("Lỗi tung xu.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- DICE (XÚC XẮC) ----
# -------------------------
@bot.slash_command(name="xucxac", description="Đoán xúc xắc (1-6). Thắng 1 ăn 5.")
@app_commands.describe(bet_amount="Số token", guess="Số (1-6)")
@global_rate_limit()
@is_user_not_in_game()
async def dice_roll_slash(interaction: discord.Interaction, bet_amount: int, guess: app_commands.Range[int,1,6]):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        res = random.randint(1,6)
        is_win = (res == guess)
        winnings = bet_amount * 5 if is_win else 0
        payout = winnings if is_win else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)
        embed = discord.Embed(title=f"🎲 Gieo xúc xắc... Kết quả: {res}", color=(discord.Color.green() if is_win else discord.Color.red()))
        if is_win:
            embed.description = f"🎉 Bạn đoán đúng! Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        else:
            embed.description = f"😢 Bạn đoán sai. Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Dice error:", e)
        await interaction.followup.send("Lỗi khi gieo xúc xắc.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- BẦU CUA ----
# -------------------------
BAU_CUA_MAP = {'bầu':'Bầu 🍐','bau':'Bầu 🍐','🍐':'Bầu 🍐','cua':'Cua 🦀','🦀':'Cua 🦀','tôm':'Tôm 🦐','tom':'Tôm 🦐','🦐':'Tôm 🦐','cá':'Cá 🐟','ca':'Cá 🐟','🐟':'Cá 🐟','gà':'Gà 🐓','ga':'Gà 🐓','🐓':'Gà 🐓','nai':'Nai 🦌','🦌':'Nai 🦌'}
BAU_CUA_LIST = ['Bầu 🍐','Cua 🦀','Tôm 🦐','Cá 🐟','Gà 🐓','Nai 🦌']

@bot.slash_command(name="baucua", description="Chơi Bầu Cua.")
@app_commands.describe(bet_amount="Số token", choice="Lựa chọn")
@global_rate_limit()
@is_user_not_in_game()
async def bau_cua_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return
    normalized = BAU_CUA_MAP.get(choice.lower().strip())
    if not normalized:
        await interaction.response.send_message("Lựa chọn không hợp lệ.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        results = random.choices(BAU_CUA_LIST, k=3)
        hits = results.count(normalized)
        winnings = bet_amount * hits if hits>0 else 0
        payout = winnings if wins:= (hits>0) else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)
        embed = discord.Embed(title="🦀 Bầu Cua", description=f"| {results[0]} | {results[1]} | {results[2]} |", color=(discord.Color.green() if wins else discord.Color.red()))
        if wins:
            embed.add_field(name="🎉 Kết quả", value=f"Trúng {hits} lần — Bạn nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(newbal)}**")
        else:
            embed.add_field(name="😢 Kết quả", value=f"Bạn mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(newbal)}**")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Bau cua error:", e)
        await interaction.followup.send("Lỗi Bầu Cua.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- ĐUA NGỰA ----
# -------------------------
def get_race_track(positions):
    s = ""
    for i in range(NUM_HORSES):
        pos = min(positions[i], RACE_LENGTH)
        finish = '🏆' if positions[i] >= RACE_LENGTH else '🏁'
        s += f"🐎 {i+1}: {'─'*pos}{finish}\n"
    return s

@bot.slash_command(name="duangua", description="Đua ngựa (1-6). Thắng 1 ăn 4.")
@app_commands.describe(bet_amount="Số token", horse_number="Ngựa (1-6)")
@global_rate_limit()
@is_user_not_in_game()
async def dua_ngua_slash(interaction: discord.Interaction, bet_amount: int, horse_number: app_commands.Range[int,1,NUM_HORSES]):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        positions = [0]*NUM_HORSES
        embed = discord.Embed(title="🐎 Đua ngựa bắt đầu!", description=get_race_track(positions), color=discord.Color.blue())
        embed.set_footer(text=f"{interaction.user.display_name} cược {fmt_num(bet_amount)} vào ngựa {horse_number}")
        msg = await interaction.followup.send(embed=embed, wait=True)

        winner = None
        while winner is None:
            await asyncio.sleep(1.5)
            for i in range(NUM_HORSES):
                if positions[i] < RACE_LENGTH:
                    positions[i] += random.randint(1,3)
                    if positions[i] >= RACE_LENGTH and winner is None:
                        winner = i+1
            embed.description = get_race_track(positions)
            try:
                await msg.edit(embed=embed)
            except discord.NotFound:
                raise asyncio.CancelledError("Message deleted")

        is_win = (winner == horse_number)
        winnings = bet_amount*4 if is_win else 0
        payout = winnings if is_win else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)
        embed.title = f"🏁 Ngựa chiến thắng: {winner}"
        if is_win:
            embed.color = discord.Color.green()
            embed.description += f"\n\n🎉 Bạn thắng! Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        else:
            embed.color = discord.Color.red()
            embed.description += f"\n\n😢 Bạn thua. Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        await msg.edit(embed=embed)
    except asyncio.CancelledError:
        await interaction.followup.send("Trò chơi bị hủy.", ephemeral=True)
    except Exception as e:
        print("Race error:", e)
        await interaction.followup.send("Lỗi đua ngựa.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- ROULETTE (PARSE + PLAY) ----
# -------------------------
def parse_roulette_bet(bet_type_str: str):
    s = bet_type_str.lower().strip()
    if s.isdigit():
        n = int(s)
        if 0 <= n <= 36:
            return {'category':'single','numbers':[n]}
    if s in ['đỏ','red']:
        return {'category':'color','numbers':RED_NUMBERS}
    if s in ['đen','black']:
        return {'category':'color','numbers':BLACK_NUMBERS}
    if s in ['lẻ','odd']:
        return {'category':'evenodd','numbers':[n for n in range(1,37) if n%2!=0]}
    if s in ['chẵn','even']:
        return {'category':'evenodd','numbers':[n for n in range(1,37) if n%2==0]}
    if s in ['nửa1','1-18','1-18']:
        return {'category':'half','numbers':list(range(1,19))}
    if s in ['nửa2','19-36','19-36']:
        return {'category':'half','numbers':list(range(19,37))}
    if s in ['tá1','1-12']:
        return {'category':'dozen','numbers':list(range(1,13))}
    if s in ['tá2','13-24']:
        return {'category':'dozen','numbers':list(range(13,25))}
    if s in ['tá3','25-36']:
        return {'category':'dozen','numbers':list(range(25,37))}
    if s in ['cột1','col1']:
        return {'category':'column','numbers':[n for n in range(1,37) if n%3==1]}
    if s in ['cột2','col2']:
        return {'category':'column','numbers':[n for n in range(1,37) if n%3==2]}
    if s in ['cột3','col3']:
        return {'category':'column','numbers':[n for n in range(1,37) if n%3==0]}
    # complex regex for split/street/corner/sixline
    split = re.match(r"split-(\d{1,2})-(\d{1,2})", s)
    if split:
        a,b = int(split.group(1)), int(split.group(2))
        if 1<=a<=36 and 1<=b<=36 and a!=b:
            return {'category':'split','numbers':[a,b]}
    street = re.match(r"street-(\d{1,2})-(\d{1,2})-(\d{1,2})", s)
    if street:
        nums = list(map(int, street.groups()))
        if all(1<=n<=36 for n in nums):
            return {'category':'street','numbers':nums}
    corner = re.match(r"corner-(\d{1,2})-(\d{1,2})-(\d{1,2})-(\d{1,2})", s)
    if corner:
        nums = list(map(int, corner.groups()))
        if len(set(nums))==4 and all(1<=n<=36 for n in nums):
            return {'category':'corner','numbers':nums}
    six = re.match(r"sixline-(\d{1,2})-(\d{1,2})", s)
    if six:
        a,b = int(six.group(1)), int(six.group(2))
        if 1<=a<=31 and b==a+5:
            return {'category':'sixline','numbers':list(range(a,b+1))}
    raise ValueError(f"Invalid Roulette bet type: {bet_type_str}")

@bot.slash_command(name="quay", description="Chơi Roulette.")
@app_commands.describe(bet_amount="Số token", bet_type="Loại cược (số, đỏ, đen, tá1, col1, split-x-y, etc.)")
@global_rate_limit()
@is_user_not_in_game()
async def roulette_slash(interaction: discord.Interaction, bet_amount: int, bet_type: str):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <=0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return
    try:
        parsed = parse_roulette_bet(bet_type)
    except ValueError as e:
        await interaction.response.send_message(str(e), ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        spin = random.randint(0,36)
        color = 'xanh lá' if spin==0 else ('đỏ' if spin in RED_NUMBERS else 'đen')
        is_win = spin in parsed['numbers']
        payout_rate = ROULETTE_PAYOUTS.get(parsed['category'], 0) if is_win else 0
        winnings = bet_amount * payout_rate if is_win else 0
        payout = winnings if is_win else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)

        embed = discord.Embed(title="🎡 Roulette", color=(discord.Color.green() if is_win else discord.Color.red()))
        embed.add_field(name="Kết quả", value=f"Số: **{spin}** ({color})", inline=False)
        embed.add_field(name="Cược của bạn", value=f"**{bet_type}** — {fmt_num(bet_amount)} 🪙", inline=False)
        if is_win:
            embed.description = f"🎉 Bạn thắng! 1 ăn {payout_rate}. Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        else:
            embed.description = f"😢 Bạn thua. Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Roulette error:", e)
        await interaction.followup.send("Lỗi Roulette.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- BACCARAT (Hoàn thiện) ----
# -------------------------
def create_baccarat_deck():
    deck = []
    for s in CARD_SUITS:
        for rank, val in CARD_RANKS_BACCARAT.items():
            deck.append({'rank':rank,'suit':s,'value':val})
    random.shuffle(deck)
    return deck

def calculate_baccarat_score(hand):
    return sum(card['value'] for card in hand) % 10

def banker_should_draw(banker_score, player_drew_third, player_third_value):
    if not player_drew_third:
        return banker_score <= 5
    if banker_score <= 2:
        return True
    if banker_score == 3:
        return player_third_value != 8
    if banker_score == 4:
        return player_third_value in [2,3,4,5,6,7]
    if banker_score == 5:
        return player_third_value in [4,5,6,7]
    if banker_score == 6:
        return player_third_value in [6,7]
    return False

@bot.slash_command(name="baccarat", description="Chơi Baccarat. Cược Player/Banker/Tie.")
@app_commands.describe(bet_amount="Số token", choice="Player/Banker/Tie")
@app_commands.choices(choice=[app_commands.Choice(name="Player",value="player"), app_commands.Choice(name="Banker",value="banker"), app_commands.Choice(name="Tie",value="tie")])
@global_rate_limit()
@is_user_not_in_game()
async def baccarat_slash(interaction: discord.Interaction, bet_amount: int, choice: str):
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.response.send_message("Không đủ tiền hoặc tham số sai.", ephemeral=True); return

    bot.users_in_animation.add(uid)
    await interaction.response.defer()
    try:
        deck = create_baccarat_deck()
        player = [deck.pop(), deck.pop()]
        banker = [deck.pop(), deck.pop()]
        pscore = calculate_baccarat_score(player)
        bscore = calculate_baccarat_score(banker)
        player_drew = False
        player_third_val = None

        # Natural
        if pscore >=8 or bscore >=8:
            pass
        else:
            if pscore <=5:
                third = deck.pop()
                player.append(third)
                player_drew = True
                player_third_val = third['value']
                pscore = calculate_baccarat_score(player)
            if banker_should_draw(bscore, player_drew, player_third_val if player_third_val is not None else -1):
                banker.append(deck.pop())
                bscore = calculate_baccarat_score(banker)

        if pscore > bscore:
            winner = 'player'
        elif bscore > pscore:
            winner = 'banker'
        else:
            winner = 'tie'

        multiplier = 0.0
        if choice == 'player':
            multiplier = 1.0 if winner=='player' else -1.0
        elif choice == 'banker':
            multiplier = 0.95 if winner=='banker' else -1.0
        elif choice == 'tie':
            multiplier = 8.0 if winner=='tie' else -1.0
        else:
            multiplier = -1.0

        payout = int(bet_amount * multiplier) if multiplier >=0 else -bet_amount
        newbal = update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)

        p_cards = ", ".join([f"{c['rank']}{c['suit']}" for c in player])
        b_cards = ", ".join([f"{c['rank']}{c['suit']}" for c in banker])
        embed = discord.Embed(title="🃏 Baccarat - Kết quả", color=(discord.Color.green() if payout>0 else discord.Color.red()))
        embed.add_field(name="Player", value=f"{p_cards} (Điểm: {pscore})", inline=False)
        embed.add_field(name="Banker", value=f"{b_cards} (Điểm: {bscore})", inline=False)
        if payout>0:
            embed.description = f"🎉 Bạn thắng **{fmt_num(payout)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        else:
            embed.description = f"😢 Bạn thua **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(newbal)}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("Baccarat error:", e)
        await interaction.followup.send("Lỗi Baccarat.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# -------------------------
# ---- RUN BOT ----------
# -------------------------
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print("Cannot start bot:", e)
