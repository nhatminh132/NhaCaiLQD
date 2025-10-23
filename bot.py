# bot.py
# -*- coding: utf-8 -*-
"""
Single-file Casino Discord Bot (slash commands)
- Supabase-backed (profiles + taixiu_history + adjust_balance RPC)
- Tài Xỉu 4 cửa: automatic rounds 30s, live embed updated every 5s (cầu trực tiếp)
- Games: taixiu (real-time), slots, baccarat, blackjack, xucxac, baucua, duangua, roulette
- Commands: /balance, /daily, /taixiu, /cautaixiu, /top, /toptaixiu, etc.
"""
import os
import random
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import pytz

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

# Supabase client
try:
    from supabase import create_client
    HAS_SUPABASE = True
except Exception:
    HAS_SUPABASE = False

# -----------------------
# Config & init
# -----------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TOKEN:
    print("ERROR: DISCORD_TOKEN is required in .env")
    raise SystemExit(1)

supabase = None
if HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    print("Warning: Supabase not configured or supabase-py not installed. Persistence will not work.")

VIETNAM_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
STARTING_TOKENS = 100

# -----------------------
# Constants & helpers
# -----------------------
RED_NUMBERS = [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]
BLACK_NUMBERS = [2,4,6,8,10,11,13,15,17,20,22,24,26,28,29,31,33,35]
ROULETTE_PAYOUTS = {'single':35, 'dozen':2, 'column':2, 'color':1, 'evenodd':1, 'half':1}

SLOT_SYMBOLS = [('🍒', 10, 10), ('🍋', 9, 15), ('🍊', 8, 20), ('🍓', 5, 30), ('🔔', 3, 50), ('💎', 2, 100), ('7️⃣', 1, 200)]
SLOT_WHEEL = [s for s,w,p in SLOT_SYMBOLS]
SLOT_WEIGHTS = [w for s,w,p in SLOT_SYMBOLS]
SLOT_PAYOUTS = {s:p for s,w,p in SLOT_SYMBOLS}

CARD_SUITS = ['♥️','♦️','♣️','♠️']
CARD_RANKS_BACCARAT = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':0,'J':0,'Q':0,'K':0,'A':1}

def fmt_num(n:int)->str:
    return f"{n:,}"

# -----------------------
# Bot setup
# -----------------------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)
bot.users_in_animation = set()
# taixiu runtime state
bot.taixiu_state = {
    'channel_id': None,
    'bets': {},           # {user_id: {'tai':int,'xiu':int,'chan':int,'le':int}}
    'running': False,
    'locked': False,
    'embed_message_id': None
}

# Taixiu config
TAIXIU_BET_WINDOW = 30
TAIXIU_EMBED_UPDATE = 5
TAIXIU_HISTORY_DISPLAY = 20

# Emoji mapping
EMOJI_TAI = "🔴"
EMOJI_XIU = "⚪"
EMOJI_CHAN = "🟢"
EMOJI_LE = "🟣"

# -----------------------
# Database helpers
# -----------------------
def get_user_data(user_id:int)->Optional[Dict]:
    """Fetch or create profile row in Supabase. Returns dict or None on error.
       If supabase not configured, returns a volatile default dict (not persistent)."""
    if supabase is None:
        return {'user_id': user_id, 'balance': STARTING_TOKENS, 'total_bet':0, 'total_won':0, 'games_played':0}
    try:
        resp = supabase.table('profiles').select('*').eq('user_id', user_id).maybe_single().execute()
        data = resp.data
        if not data:
            supabase.table('profiles').insert({'user_id': user_id, 'balance': STARTING_TOKENS}).execute()
            return {'user_id': user_id, 'balance': STARTING_TOKENS, 'total_bet':0, 'total_won':0, 'games_played':0}
        # ensure keys
        data.setdefault('balance', STARTING_TOKENS)
        data.setdefault('total_bet', 0)
        data.setdefault('total_won', 0)
        data.setdefault('games_played', 0)
        return data
    except Exception as e:
        print("get_user_data error:", e)
        return None

def update_balance(user_id:int, amount:int)->Optional[int]:
    """Atomically adjust balance by calling RPC adjust_balance. Returns new balance or None."""
    if supabase is None:
        print("update_balance: supabase not configured")
        return None
    try:
        res = supabase.rpc('adjust_balance', {'user_id_input': user_id, 'amount_input': amount}).execute()
        return res.data
    except Exception as e:
        print("update_balance error:", e)
        return None

def update_profile_stats(user_id:int, bet_amount:int, net_gain:int):
    """Update aggregates in profiles."""
    if supabase is None:
        return
    try:
        resp = supabase.table('profiles').select('*').eq('user_id', user_id).maybe_single().execute()
        data = resp.data or {}
        total_bet = data.get('total_bet', 0) + bet_amount
        total_won = data.get('total_won', 0) + max(0, net_gain)
        games_played = data.get('games_played', 0) + 1
        supabase.table('profiles').update({'total_bet': total_bet, 'total_won': total_won, 'games_played': games_played}).eq('user_id', user_id).execute()
    except Exception as e:
        print("update_profile_stats error:", e)

async def save_taixiu_result(dice:List[int], total:int):
    if supabase is None:
        return
    try:
        supabase.table('taixiu_history').insert({
            'dice': dice,
            'total': total,
            'result_tai': total >= 11,
            'result_chan': (total % 2 == 0)
        }).execute()
    except Exception as e:
        print("save_taixiu_result error:", e)

async def load_taixiu_history(limit:int=20)->List[Dict]:
    if supabase is None:
        return []
    try:
        resp = supabase.table('taixiu_history').select('*').order('id', desc=True).limit(limit).execute()
        return resp.data or []
    except Exception as e:
        print("load_taixiu_history error:", e)
        return []

# -----------------------
# Taixiu utilities & embed updater
# -----------------------
def taixiu_outcome_to_emojis(total:int):
    e1 = EMOJI_TAI if total >= 11 else EMOJI_XIU
    e2 = EMOJI_CHAN if total % 2 == 0 else EMOJI_LE
    return e1, e2

@tasks.loop(seconds=TAIXIU_EMBED_UPDATE)
async def taixiu_embed_updater():
    state = bot.taixiu_state
    channel_id = state.get('channel_id')
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if channel is None:
        return

    # ensure an embed message exists (create if missing)
    try:
        message = None
        if state.get('embed_message_id'):
            try:
                message = await channel.fetch_message(state['embed_message_id'])
            except discord.NotFound:
                message = None
        if message is None:
            embed = discord.Embed(title="📊 Bảng cầu Tài Xỉu (live)", description="Đang khởi tạo...", color=discord.Color.purple())
            embed.set_footer(text=f"Auto cập nhật mỗi {TAIXIU_EMBED_UPDATE}s • Ván mỗi {TAIXIU_BET_WINDOW}s")
            m = await channel.send(embed=embed)
            state['embed_message_id'] = m.id
            message = m

        # build rows from history
        history = await load_taixiu_history(limit=TAIXIU_HISTORY_DISPLAY)
        history = list(reversed(history))  # oldest -> newest
        tai_xiu_row = ""
        chan_le_row = ""
        for row in history:
            total = row.get('total', 0)
            e1,e2 = taixiu_outcome_to_emojis(total)
            tai_xiu_row += e1
            chan_le_row += e2
        if not tai_xiu_row:
            tai_xiu_row = "Chưa có ván nào."
            chan_le_row = "Chưa có ván nào."

        # bets summary
        bets_summary = {'tai':0,'xiu':0,'chan':0,'le':0}
        for uid, bets in state['bets'].items():
            for k in bets_summary.keys():
                bets_summary[k] += bets.get(k, 0)

        bets_desc = (
            f"**Cược hiện tại:** Tài {fmt_num(bets_summary['tai'])} 🪙 | Xỉu {fmt_num(bets_summary['xiu'])} 🪙 | "
            f"Chẵn {fmt_num(bets_summary['chan'])} 🪙 | Lẻ {fmt_num(bets_summary['le'])} 🪙\n"
            f"**Trạng thái:** {'Đang mở cược' if not state['locked'] else 'Đã khóa cược'}"
        )

        embed = discord.Embed(title="📊 Bảng cầu Tài Xỉu (live)", color=discord.Color.purple())
        embed.add_field(name="Tài / Xỉu (trái→phải: cũ→mới)", value=tai_xiu_row, inline=False)
        embed.add_field(name="Chẵn / Lẻ", value=chan_le_row, inline=False)
        embed.add_field(name="📌 Thông tin", value=bets_desc, inline=False)
        embed.set_footer(text=f"Cập nhật mỗi {TAIXIU_EMBED_UPDATE}s • Mỗi ván {TAIXIU_BET_WINDOW}s")

        await message.edit(embed=embed)
    except Exception as e:
        print("taixiu_embed_updater error:", e)

# -----------------------
# Taixiu round runner
# -----------------------
async def taixiu_round_runner_once(channel:discord.TextChannel):
    state = bot.taixiu_state
    # announce
    try:
        await channel.send(f"🕐 Ván Tài Xỉu mới bắt đầu! Bạn có **{TAIXIU_BET_WINDOW} giây** đặt cược bằng `/taixiu`.")
    except Exception:
        pass

    state['locked'] = False
    await asyncio.sleep(TAIXIU_BET_WINDOW)
    state['locked'] = True

    # roll
    dice = [random.randint(1,6) for _ in range(3)]
    total = sum(dice)
    result_tai = total >= 11
    result_chan = (total % 2 == 0)

    # persist
    await save_taixiu_result(dice, total)

    # payouts
    for uid, bets in list(state['bets'].items()):
        total_bet = sum(bets.get(s,0) for s in ['tai','xiu','chan','le'])
        total_win = 0
        for side, amt in bets.items():
            if amt <= 0:
                continue
            win = (
                (side == 'tai' and result_tai) or
                (side == 'xiu' and not result_tai) or
                (side == 'chan' and result_chan) or
                (side == 'le' and not result_chan)
            )
            if win:
                total_win += amt * 2
        net = total_win - total_bet
        if net != 0:
            update_balance(uid, net)
        update_profile_stats(uid, total_bet, net)

    # result embed (single message)
    e1,e2 = taixiu_outcome_to_emojis(total)
    result_text = f"🎲 {dice[0]} + {dice[1]} + {dice[2]} = **{total}** điểm\nKết quả: **{'TÀI' if result_tai else 'XỈU'} {e1} - {'CHẴN' if result_chan else 'LẺ'} {e2}**"
    embed = discord.Embed(title="💥 Kết quả ván Tài Xỉu", description=result_text, color=discord.Color.green())
    try:
        await channel.send(embed=embed)
    except Exception:
        pass

    # reset bets
    state['bets'] = {}

async def taixiu_loop():
    state = bot.taixiu_state
    if state.get('channel_id') is None:
        return
    channel = bot.get_channel(state['channel_id'])
    if channel is None:
        return
    # ensure embed updater running
    if not taixiu_embed_updater.is_running():
        taixiu_embed_updater.start()
    while state.get('channel_id') == channel.id:
        await taixiu_round_runner_once(channel)
        await asyncio.sleep(1)
    if taixiu_embed_updater.is_running():
        taixiu_embed_updater.cancel()

# -----------------------
# Slash commands
# -----------------------
@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as e:
        print("Sync error:", e)
    print(f"Bot ready: {bot.user} (id: {bot.user.id})")

# /balance
@bot.tree.command(name="balance", description="Xem số dư token của bạn")
async def balance_cmd(interaction:discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user = get_user_data(interaction.user.id)
    if not user:
        await interaction.followup.send("Lỗi khi lấy dữ liệu.", ephemeral=True); return
    await interaction.followup.send(f"💰 {interaction.user.mention}, số dư: **{fmt_num(user.get('balance',0))}** 🪙", ephemeral=True)

# /daily
@bot.tree.command(name="daily", description="Nhận thưởng hàng ngày (+50)")
async def daily_cmd(interaction:discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user:
        await interaction.followup.send("Lỗi DB.", ephemeral=True); return
    last_daily = user.get('last_daily')
    now = datetime.now(timezone.utc)
    if last_daily:
        try:
            last_dt = datetime.fromisoformat(last_daily)
            if (now - last_dt).total_seconds() < 24*3600:
                remaining = 24*3600 - (now - last_dt).total_seconds()
                hrs = int(remaining//3600); mins = int((remaining%3600)//60)
                await interaction.followup.send(f"Bạn đã nhận daily rồi. Thử lại sau {hrs} giờ {mins} phút.", ephemeral=True)
                return
        except Exception:
            pass
    reward = 50
    newbal = update_balance(uid, reward)
    try:
        if supabase:
            supabase.table('profiles').update({'last_daily': now.isoformat()}).eq('user_id', uid).execute()
    except:
        pass
    await interaction.followup.send(f"🎉 Bạn nhận **{fmt_num(reward)}** token! Số dư: **{fmt_num(newbal)}**", ephemeral=True)

# /taixiu
@bot.tree.command(name="taixiu", description="Cược Tài/Xỉu/Chẵn/Lẻ (ván tự động 30s, cầu live)")
@app_commands.describe(bet_amount="Số token", choice="Cửa (Tài/Xỉu/Chẵn/Lẻ)")
@app_commands.choices(choice=[
    app_commands.Choice(name="Tài", value="tai"),
    app_commands.Choice(name="Xỉu", value="xiu"),
    app_commands.Choice(name="Chẵn", value="chan"),
    app_commands.Choice(name="Lẻ", value="le"),
])
async def taixiu_cmd(interaction:discord.Interaction, bet_amount:int, choice:str):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user:
        await interaction.followup.send("Lỗi DB.", ephemeral=True); return
    balance = user.get('balance',0)
    if bet_amount <= 0:
        await interaction.followup.send("Số tiền cược phải > 0.", ephemeral=True); return
    if balance < bet_amount:
        await interaction.followup.send(f"Bạn không đủ token. Số dư: **{fmt_num(balance)}** 🪙", ephemeral=True); return

    state = bot.taixiu_state
    if state.get('channel_id') is None:
        state['channel_id'] = interaction.channel_id
        if not state.get('running'):
            state['running'] = True
            asyncio.create_task(taixiu_loop())

    if state.get('locked'):
        await interaction.followup.send("Ván hiện tại đã khóa cược, chờ ván tiếp theo.", ephemeral=True); return

    if uid not in state['bets']:
        state['bets'][uid] = {'tai':0,'xiu':0,'chan':0,'le':0}
    state['bets'][uid][choice] += bet_amount

    newbal = update_balance(uid, -bet_amount)
    if newbal is None:
        await interaction.followup.send("Lỗi cập nhật số dư (DB).", ephemeral=True); return

    await interaction.followup.send(f"✅ Bạn cược **{fmt_num(bet_amount)}** 🪙 vào **{choice.upper()}**. Số dư còn lại: **{fmt_num(newbal)}** 🪙", ephemeral=True)

# /cautaixiu
@bot.tree.command(name="cautaixiu", description="Xem cầu Tài Xỉu (20 ván gần nhất)")
async def cautaixiu_cmd(interaction:discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    hist = await load_taixiu_history(limit=20)
    if not hist:
        await interaction.followup.send("Chưa có lịch sử.", ephemeral=True); return
    hist = list(reversed(hist))
    tai_xiu_row = ""
    chan_le_row = ""
    for row in hist:
        total = row.get('total',0)
        e1,e2 = taixiu_outcome_to_emojis(total)
        tai_xiu_row += e1
        chan_le_row += e2
    embed = discord.Embed(title="📜 Cầu Tài Xỉu (20 ván gần nhất)", color=discord.Color.blue())
    embed.add_field(name="Tài / Xỉu", value=tai_xiu_row, inline=False)
    embed.add_field(name="Chẵn / Lẻ", value=chan_le_row, inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)

# /top (leaderboard by balance)
@bot.tree.command(name="top", description="Xem bảng xếp hạng theo số dư (top N)")
@app_commands.describe(top_n="Số lượng (mặc định 10)")
async def top_cmd(interaction:discord.Interaction, top_n:int=10):
    await interaction.response.defer()
    if supabase is None:
        await interaction.followup.send("Bảng xếp hạng cần Supabase.", ephemeral=True); return
    top_n = max(1, min(50, top_n))
    try:
        resp = supabase.table('profiles').select('user_id','balance').order('balance', desc=True).limit(top_n).execute()
        rows = resp.data or []
        if not rows:
            await interaction.followup.send("Chưa có dữ liệu.", ephemeral=True); return
        embed = discord.Embed(title=f"🏆 Top {top_n} theo số dư", color=discord.Color.gold())
        for i,row in enumerate(rows, start=1):
            uid = row.get('user_id')
            bal = row.get('balance',0)
            embed.add_field(name=f"#{i} — <@{uid}>", value=f"**{fmt_num(bal)}** 🪙", inline=False)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("top_cmd error:", e)
        await interaction.followup.send("Lỗi lấy dữ liệu bảng xếp hạng.", ephemeral=True)

# /toptaixiu (top by total_won)
@bot.tree.command(name="toptaixiu", description="Bảng xếp hạng Tài Xỉu (theo tổng thắng từ profiles.total_won)")
@app_commands.describe(top_n="Số lượng (mặc định 10)")
async def toptaixiu_cmd(interaction:discord.Interaction, top_n:int=10):
    await interaction.response.defer()
    if supabase is None:
        await interaction.followup.send("Cần Supabase để xem bảng xếp hạng.", ephemeral=True); return
    top_n = max(1, min(50, top_n))
    try:
        resp = supabase.table('profiles').select('user_id','total_won').order('total_won', desc=True).limit(top_n).execute()
        rows = resp.data or []
        if not rows:
            await interaction.followup.send("Chưa có dữ liệu.", ephemeral=True); return
        embed = discord.Embed(title=f"🏆 Top {top_n} theo tổng thắng (all-games)", color=discord.Color.gold())
        for i,row in enumerate(rows, start=1):
            uid = row.get('user_id'); tw = row.get('total_won',0)
            embed.add_field(name=f"#{i} — <@{uid}>", value=f"**{fmt_num(tw)}** 🪙", inline=False)
        embed.set_footer(text="Lưu ý: total_won là tổng thắng trên profiles (tất cả game). Nếu bạn muốn chỉ riêng Tài Xỉu, cần track per-game stats.")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("toptaixiu error:", e)
        await interaction.followup.send("Lỗi lấy dữ liệu bảng xếp hạng.", ephemeral=True)

# /slots
@bot.tree.command(name="slots", description="Chơi máy xèng (non-real-time)")
@app_commands.describe(bet_amount="Số token")
async def slots_cmd(interaction:discord.Interaction, bet_amount:int):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount <= 0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        result = random.choices(SLOT_WHEEL, weights=SLOT_WEIGHTS, k=3)
        winnings = 0
        if result[0] == result[1] == result[2]:
            winnings = bet_amount * SLOT_PAYOUTS.get(result[0], 1)
        elif result[0] == result[1] or result[1] == result[2]:
            winnings = bet_amount  # pair pays 1:1
        if winnings > 0:
            update_balance(uid, winnings)
            update_profile_stats(uid, bet_amount, winnings)
            embed = discord.Embed(title="🎰 Slots - Kết quả", description=f"| {result[0]} | {result[1]} | {result[2]} |", color=discord.Color.green())
            embed.add_field(name="Bạn thắng", value=f"Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**")
        else:
            update_profile_stats(uid, bet_amount, -bet_amount)
            embed = discord.Embed(title="🎰 Slots - Kết quả", description=f"| {result[0]} | {result[1]} | {result[2]} |", color=discord.Color.red())
            embed.add_field(name="Bạn thua", value=f"Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**")
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("slots error:", e)
        await interaction.followup.send("Lỗi khi chơi Slots.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /baccarat
def create_baccarat_deck():
    deck=[]
    for s in CARD_SUITS:
        for r,v in CARD_RANKS_BACCARAT.items():
            deck.append({'rank':r,'suit':s,'value':v})
    random.shuffle(deck); return deck

def calc_baccarat(hand):
    return sum(c['value'] for c in hand) % 10

def banker_should_draw(bscore, player_drew, player_third_val):
    if not player_drew: return bscore <= 5
    if bscore <= 2: return True
    if bscore == 3: return player_third_val != 8
    if bscore == 4: return player_third_val in [2,3,4,5,6,7]
    if bscore == 5: return player_third_val in [4,5,6,7]
    if bscore == 6: return player_third_val in [6,7]
    return False

@bot.tree.command(name="baccarat", description="Chơi Baccarat: Player/Banker/Tie")
@app_commands.describe(bet_amount="Số token", choice="Player/Banker/Tie")
@app_commands.choices(choice=[
    app_commands.Choice(name="Player", value="player"),
    app_commands.Choice(name="Banker", value="banker"),
    app_commands.Choice(name="Tie", value="tie"),
])
async def baccarat_cmd(interaction:discord.Interaction, bet_amount:int, choice:str):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        deck = create_baccarat_deck()
        player = [deck.pop(), deck.pop()]
        banker = [deck.pop(), deck.pop()]
        ps = calc_baccarat(player); bs = calc_baccarat(banker)
        player_drew=False; player_third_val=None
        if ps < 8 and bs < 8:
            if ps <=5:
                third = deck.pop(); player.append(third); player_drew=True; player_third_val=third['value']; ps = calc_baccarat(player)
            if banker_should_draw(bs, player_drew, player_third_val if player_third_val is not None else -1):
                banker.append(deck.pop()); bs = calc_baccarat(banker)
        if ps > bs: winner='player'
        elif bs > ps: winner='banker'
        else: winner='tie'
        multiplier = 0.0
        if choice == 'player':
            multiplier = 1.0 if winner=='player' else -1.0
        elif choice == 'banker':
            multiplier = 0.95 if winner=='banker' else -1.0
        elif choice == 'tie':
            multiplier = 8.0 if winner=='tie' else -1.0
        payout = int(bet_amount * multiplier) if multiplier >= 0 else -bet_amount
        if payout > 0:
            update_balance(uid, payout)
        update_profile_stats(uid, bet_amount, payout)
        pcards = ", ".join([f"{c['rank']}{c['suit']}" for c in player])
        bcards = ", ".join([f"{c['rank']}{c['suit']}" for c in banker])
        embed = discord.Embed(title="🃏 Baccarat - Kết quả", color=(discord.Color.green() if payout>0 else discord.Color.red()))
        embed.add_field(name="Player", value=f"{pcards} — Điểm: {ps}", inline=False)
        embed.add_field(name="Banker", value=f"{bcards} — Điểm: {bs}", inline=False)
        if payout>0:
            embed.description = f"🎉 Bạn thắng **{fmt_num(payout)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        else:
            embed.description = f"😢 Bạn thua **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("baccarat error:", e)
        await interaction.followup.send("Lỗi Baccarat.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /blackjack (minimal)
@bot.tree.command(name="blackjack", description="Chơi Blackjack (bản giản lược)")
@app_commands.describe(bet_amount="Số token")
async def blackjack_cmd(interaction:discord.Interaction, bet_amount:int):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        ranks = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
        values = {**{str(i):i for i in range(2,11)}, 'J':10,'Q':10,'K':10,'A':11}
        def draw(n): return [random.choice(ranks) for _ in range(n)]
        user_cards = draw(2); dealer_cards = draw(2)
        user_val = sum(values[c] for c in user_cards)
        dealer_val = sum(values[c] for c in dealer_cards)
        if user_val > 21: result = 'lose'
        elif dealer_val > 21: result = 'win'
        elif user_val > dealer_val: result = 'win'
        elif user_val < dealer_val: result = 'lose'
        else: result = 'push'
        if result == 'win':
            win = bet_amount * 2
            update_balance(uid, win)
            update_profile_stats(uid, bet_amount, bet_amount)
            msg = f"🎉 Bạn thắng! Nhận **{fmt_num(bet_amount)}** (net)."
        elif result == 'push':
            update_balance(uid, bet_amount)
            update_profile_stats(uid, bet_amount, 0)
            msg = "🔁 Hòa — tiền cược trả lại."
        else:
            update_profile_stats(uid, bet_amount, -bet_amount)
            msg = f"😢 Bạn thua và mất **{fmt_num(bet_amount)}**."
        embed = discord.Embed(title="🂡 Blackjack (đơn giản)", color=(discord.Color.green() if result=='win' else discord.Color.red() if result=='lose' else discord.Color.greyple()))
        embed.add_field(name="Bạn", value=f"{', '.join(user_cards)} = {user_val}", inline=False)
        embed.add_field(name="Dealer", value=f"{', '.join(dealer_cards)} = {dealer_val}", inline=False)
        embed.description = msg + f"\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("blackjack error:", e)
        await interaction.followup.send("Lỗi Blackjack.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /xucxac
@bot.tree.command(name="xucxac", description="Đoán xúc xắc (1-6). Thắng 1 ăn 5.")
@app_commands.describe(bet_amount="Số token", guess="Số (1-6)")
async def xucxac_cmd(interaction:discord.Interaction, bet_amount:int, guess:app_commands.Range[int,1,6]):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        res = random.randint(1,6)
        if res == guess:
            winnings = bet_amount * 5
            update_balance(uid, winnings)
            update_profile_stats(uid, bet_amount, winnings)
            embed = discord.Embed(title=f"🎲 Kết quả: {res}", color=discord.Color.green())
            embed.description = f"🎉 Bạn đoán đúng! Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        else:
            update_profile_stats(uid, bet_amount, -bet_amount)
            embed = discord.Embed(title=f"🎲 Kết quả: {res}", color=discord.Color.red())
            embed.description = f"😢 Bạn đoán sai. Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("xucxac error:", e)
        await interaction.followup.send("Lỗi xúc xắc.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /baucua
@bot.tree.command(name="baucua", description="Chơi Bầu Cua (đặt 1 cửa).")
@app_commands.describe(bet_amount="Số token", choice="Bầu/Cua/Tôm/Cá/Gà/Nai")
@app_commands.choices(choice=[
    app_commands.Choice(name="Bầu", value="bau"),
    app_commands.Choice(name="Cua", value="cua"),
    app_commands.Choice(name="Tôm", value="tom"),
    app_commands.Choice(name="Cá", value="ca"),
    app_commands.Choice(name="Gà", value="ga"),
    app_commands.Choice(name="Nai", value="nai"),
])
async def baucua_cmd(interaction:discord.Interaction, bet_amount:int, choice:str):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    mapping = {'bau':'Bầu','cua':'Cua','tom':'Tôm','ca':'Cá','ga':'Gà','nai':'Nai'}
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount or choice not in mapping:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        faces = list(mapping.values())
        rolls = [random.choice(faces) for _ in range(3)]
        hits = rolls.count(mapping[choice])
        if hits > 0:
            winnings = bet_amount * hits
            update_balance(uid, winnings)
            update_profile_stats(uid, bet_amount, winnings)
            embed = discord.Embed(title="🦀 Bầu Cua - Kết quả", color=discord.Color.green())
            embed.description = f"| {rolls[0]} | {rolls[1]} | {rolls[2]} |\n🎉 Trúng {hits} lần — Nhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        else:
            update_profile_stats(uid, bet_amount, -bet_amount)
            embed = discord.Embed(title="🦀 Bầu Cua - Kết quả", color=discord.Color.red())
            embed.description = f"| {rolls[0]} | {rolls[1]} | {rolls[2]} |\n😢 Bạn thua — Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print("baucua error:", e)
        await interaction.followup.send("Lỗi Bầu Cua.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /duangua
@bot.tree.command(name="duangua", description="Cược đua ngựa (1-6), thắng 1 ăn 4.")
@app_commands.describe(bet_amount="Số token", horse_number="Ngựa (1-6)")
async def duangua_cmd(interaction:discord.Interaction, bet_amount:int, horse_number:app_commands.Range[int,1,6]):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    bot.users_in_animation.add(uid)
    try:
        update_balance(uid, -bet_amount)
        positions = [0]*6
        embed = discord.Embed(title="🐎 Đua ngựa bắt đầu!", description="", color=discord.Color.blue())
        msg = await interaction.followup.send(embed=embed)
        winner=None
        while winner is None:
            await asyncio.sleep(1.2)
            for i in range(6):
                if positions[i] < 20:
                    positions[i] += random.randint(1,3)
                    if positions[i] >= 20 and winner is None:
                        winner = i+1
            desc=""
            for i,pos in enumerate(positions):
                finish = '🏁' if pos < 20 else '🏆'
                desc += f"🐎 {i+1}: {'─'*min(pos,20)}{finish}\n"
            embed.description = desc
            try:
                await msg.edit(embed=embed)
            except discord.NotFound:
                break
        if winner == horse_number:
            winnings = bet_amount * 4
            update_balance(uid, winnings)
            update_profile_stats(uid, bet_amount, winnings)
            embed.title = f"🏁 Ngựa {winner} chiến thắng!"
            embed.color = discord.Color.green()
            embed.description += f"\n\n🎉 Bạn thắng **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        else:
            update_profile_stats(uid, bet_amount, -bet_amount)
            embed.title = f"🏁 Ngựa {winner} chiến thắng!"
            embed.color = discord.Color.red()
            embed.description += f"\n\n😢 Bạn thua — Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
        try:
            await msg.edit(embed=embed)
        except:
            await interaction.followup.send(embed=embed)
    except Exception as e:
        print("duangua error:", e)
        await interaction.followup.send("Lỗi đua ngựa.", ephemeral=True)
    finally:
        bot.users_in_animation.discard(uid)

# /roulette
def parse_roulette_bet(s:str):
    t = s.lower().strip()
    if t.isdigit():
        n=int(t)
        if 0<=n<=36: return {'category':'single','numbers':[n]}
    if t in ['đỏ','red']: return {'category':'color','numbers':RED_NUMBERS}
    if t in ['đen','black']: return {'category':'color','numbers':BLACK_NUMBERS}
    if t in ['lẻ','odd']: return {'category':'evenodd','numbers':[n for n in range(1,37) if n%2!=0]}
    if t in ['chẵn','even']: return {'category':'evenodd','numbers':[n for n in range(1,37) if n%2==0]}
    if t in ['1-18','nửa1']: return {'category':'half','numbers':list(range(1,19))}
    if t in ['19-36','nửa2']: return {'category':'half','numbers':list(range(19,37))}
    if t in ['1-12','tá1']: return {'category':'dozen','numbers':list(range(1,13))}
    if t in ['13-24','tá2']: return {'category':'dozen','numbers':list(range(13,25))}
    if t in ['25-36','tá3']: return {'category':'dozen','numbers':list(range(25,37))}
    raise ValueError("Loại cược Roulette không hợp lệ")

@bot.tree.command(name="roulette", description="Chơi Roulette (số, đỏ/đen, tá, nửa, chẵn/lẻ).")
@app_commands.describe(bet_amount="Số token", bet_type="Loại cược (ví dụ: 7, đỏ, tá1, 1-18, chẵn)")
async def roulette_cmd(interaction:discord.Interaction, bet_amount:int, bet_type:str):
    await interaction.response.defer()
    uid = interaction.user.id
    user = get_user_data(uid)
    if not user or bet_amount<=0 or user.get('balance',0) < bet_amount:
        await interaction.followup.send("Không đủ token hoặc tham số sai.", ephemeral=True); return
    try:
        parsed = parse_roulette_bet(bet_type)
    except Exception as e:
        await interaction.followup.send(str(e), ephemeral=True); return
    update_balance(uid, -bet_amount)
    spin = random.randint(0,36)
    color = 'xanh lá' if spin==0 else ('đỏ' if spin in RED_NUMBERS else 'đen')
    is_win = spin in parsed['numbers']
    payout_rate = ROULETTE_PAYOUTS.get(parsed['category'], 0) if is_win else 0
    winnings = bet_amount * payout_rate if is_win else 0
    if winnings>0:
        update_balance(uid, winnings)
    update_profile_stats(uid, bet_amount, (winnings if winnings>0 else -bet_amount))
    embed = discord.Embed(title="🎡 Roulette", color=(discord.Color.green() if is_win else discord.Color.red()))
    embed.add_field(name="Kết quả", value=f"Số: **{spin}** ({color})", inline=False)
    if is_win:
        embed.description = f"🎉 Bạn thắng! 1 ăn {payout_rate}\nNhận **{fmt_num(winnings)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
    else:
        embed.description = f"😢 Bạn thua. Mất **{fmt_num(bet_amount)}** 🪙\nSố dư: **{fmt_num(get_user_data(uid).get('balance',0))}**"
    await interaction.followup.send(embed=embed)

# -----------------------
# Run
# -----------------------
if __name__ == "__main__":
    bot.run(TOKEN)
