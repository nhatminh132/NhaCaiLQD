import discord
from discord import app_commands, ui
from discord.ext import tasks # Import Tác vụ nền
import sqlite3
import os
import requests
import json
from datetime import datetime, timedelta, date
from keep_alive import keep_alive # Đảm bảo bạn đã tạo file keep_alive.py

# --- 1. CÀI ĐẶT CƠ SỞ DỮ LIỆU (v6.0) ---

def init_db():
    """Khởi tạo cơ sở dữ liệu và thêm các bảng/cột mới nếu cần."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Bảng users
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 100,
        last_daily TEXT DEFAULT "1970-01-01T00:00:00",
        wins INTEGER NOT NULL DEFAULT 0,
        losses INTEGER NOT NULL DEFAULT 0,
        profit_loss INTEGER NOT NULL DEFAULT 0
    )
    ''')
    
    # Bảng matches
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL,
        api_match_id INTEGER UNIQUE,
        status TEXT NOT NULL DEFAULT 'open' 
    )
    ''')
    
    # Bảng bets
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        match_id TEXT NOT NULL,
        team_bet_on TEXT NOT NULL,
        amount INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(match_id) REFERENCES matches(match_id)
    )
    ''')

    # Bảng Watchlist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS watched_leagues (
        league_id INTEGER PRIMARY KEY,
        league_name TEXT NOT NULL
    )
    ''')
    
    # Bảng Settings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Bảng Role Tiers
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS role_tiers (
        role_id INTEGER PRIMARY KEY,
        min_tokens INTEGER NOT NULL UNIQUE,
        guild_id INTEGER NOT NULL
    )
    ''')
    
    # Bảng Challenges
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS challenges (
        challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        challenger_id INTEGER NOT NULL,
        opponent_id INTEGER NOT NULL,
        challenger_bet_on TEXT NOT NULL,
        opponent_bet_on TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        message_id INTEGER,
        FOREIGN KEY(match_id) REFERENCES matches(match_id)
    )
    ''')

    # Nâng cấp Bảng Cũ
    def add_column_if_not_exists(table, column, definition):
        try:
            cursor.execute(f'SELECT {column} FROM {table} LIMIT 1')
        except sqlite3.OperationalError:
            print(f"Đang thêm cột {column} vào bảng {table}...")
            cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

    add_column_if_not_exists('users', 'last_daily', 'TEXT DEFAULT "1970-01-01T00:00:00"')
    add_column_if_not_exists('users', 'wins', 'INTEGER NOT NULL DEFAULT 0')
    add_column_if_not_exists('users', 'losses', 'INTEGER NOT NULL DEFAULT 0')
    add_column_if_not_exists('users', 'profit_loss', 'INTEGER NOT NULL DEFAULT 0')
    add_column_if_not_exists('matches', 'api_match_id', 'INTEGER UNIQUE')
    try: cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_api_match_id ON matches (api_match_id)')
    except sqlite3.OperationalError: pass

    conn.commit()
    conn.close()
    print("Khởi tạo/Nâng cấp cơ sở dữ liệu (v6.0) thành công.")

# --- 2. CÁC HÀM TRỢ GIÚP (Nằm bên ngoài class) ---
def get_balance(user_id):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone(); conn.close()
    return result[0] if result else None

def update_balance(user_id, amount, is_relative=True):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    if is_relative:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def register_user(user_id, starting_balance=100):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (user_id, balance, last_daily) VALUES (?, ?, ?)", (user_id, starting_balance, "1970-01-01T00:00:00"))
        conn.commit(); conn.close(); return True
    except sqlite3.IntegrityError:
        conn.close(); return False

def get_setting(key, default=None):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default

def set_setting(key, value):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit(); conn.close()

def get_int_setting(key, default):
    value = get_setting(key, default)
    try: return int(value)
    except (ValueError, TypeError): return default

# --- 3. CÀI ĐẶT BOT DISCORD (Phiên bản 6.0) ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True # Bắt buộc

class BettingBot(discord.Client):
    
    # --- BÊN TRONG CLASS BETTINGBOT ---
    
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        init_db() # Khởi tạo DB trước
        
        # Thêm các View cố định (cho Challenge)
        self.add_view(ChallengeView())
        
        # Khởi động các vòng lặp
        self.auto_find_task.start()
        self.update_roles_task.start()
        
        await self.tree.sync()
        print(f"Đã đồng bộ {len(await self.tree.fetch_commands())} lệnh.")
        print("Vòng lặp tự động tìm kèo đã khởi động.")
        print("Vòng lặp tự động cập nhật role đã khởi động.")

    # --- VÒNG LẶP TỰ ĐỘNG TÌM KÈO (BÊN TRONG CLASS) ---
    @tasks.loop(hours=6)
    async def auto_find_task(self):
        print(f"[{datetime.now()}] Đang chạy tác vụ tự động tìm kèo...")
        channel_id = get_setting('autofind_channel_id')
        if not channel_id:
            print("Tác vụ tự động: Kênh autofind chưa được cài đặt. Bỏ qua."); return
            
        try: channel = await self.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden):
            print(f"Tác vụ tự động: Không thể tìm thấy kênh {channel_id}. Tắt vòng lặp."); set_setting('autofind_channel_id', None); return
            
        conn = sqlite3.connect('database.db'); cursor = conn.cursor()
        cursor.execute("SELECT league_id FROM watched_leagues"); leagues = cursor.fetchall()
        if not leagues: print("Tác vụ tự động: Watchlist trống."); conn.close(); return
        if not RAPIDAPI_KEY: print("Tác vụ tự động: Thiếu RAPIDAPI_KEY."); conn.close(); return

        today_str = date.today().isoformat()
        current_season = datetime.now().year
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"}
        url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
        new_matches_found = 0
        
        for (league_id,) in leagues:
            querystring = {"league": str(league_id), "season": str(current_season), "date": today_str}
            try:
                response = requests.get(url, headers=headers, params=querystring, timeout=10)
                response.raise_for_status(); data = response.json()
                if not data['response']: continue
                for fixture in data['response']:
                    api_id = fixture['fixture']['id']
                    cursor.execute("SELECT match_id FROM matches WHERE api_match_id = ?", (api_id,))
                    if cursor.fetchone() is not None: continue 
                    team_a, team_b = fixture['teams']['home']['name'], fixture['teams']['away']['name']
                    internal_id = f"auto_{api_id}"
                    await internal_create_match_for_autofind(channel, internal_id, team_a, team_b, api_id)
                    new_matches_found += 1
            except Exception as e: print(f"Tác vụ tự động: Lỗi khi lấy giải {league_id}: {e}")
        
        print(f"Tác vụ tự động: Đã hoàn thành. Thêm được {new_matches_found} kèo mới.")
        conn.close()

    @auto_find_task.before_loop
    async def before_auto_find_task(self):
        frequency_hours = get_int_setting('autofind_frequency', 6)
        if self.auto_find_task.hours != frequency_hours:
            self.auto_find_task.change_interval(hours=frequency_hours)
            print(f"Tần suất tự động tìm kèo được cập nhật là: {frequency_hours} giờ.")
        await self.wait_until_ready()

    # --- VÒNG LẶP CẬP NHẬT ROLE (BÊN TRONG CLASS) ---
    @tasks.loop(minutes=30)
    async def update_roles_task(self):
        print(f"[{datetime.now()}] Đang chạy tác vụ cập nhật role...")
        conn = sqlite3.connect('database.db'); cursor = conn.cursor()
        
        for guild in self.guilds:
            cursor.execute("SELECT role_id, min_tokens FROM role_tiers WHERE guild_id = ? ORDER BY min_tokens DESC", (guild.id,))
            tiers = cursor.fetchall()
            if not tiers: continue
            
            tier_roles = {}
            all_tier_role_ids = set()
            for role_id, min_tokens in tiers:
                role = guild.get_role(role_id)
                if role:
                    tier_roles[min_tokens] = role
                    all_tier_role_ids.add(role_id)
                else:
                    print(f"Cảnh báo: Không tìm thấy Role ID {role_id} ở Guild {guild.name}.")
            
            if not tier_roles: continue

            cursor.execute("SELECT user_id, balance FROM users")
            all_users = cursor.fetchall()
            
            for user_id, balance in all_users:
                try:
                    member = guild.get_member(user_id)
                    if not member: continue
                    
                    correct_role = None
                    for min_tokens, role in tier_roles.items():
                        if balance >= min_tokens:
                            correct_role = role
                            break
                    
                    if not correct_role: continue

                    current_role_ids = {role.id for role in member.roles}
                    roles_to_add = []
                    roles_to_remove = []

                    if correct_role.id not in current_role_ids:
                        roles_to_add.append(correct_role)
                    
                    for r_id in all_tier_role_ids:
                        if r_id != correct_role.id and r_id in current_role_ids:
                            role_to_remove = guild.get_role(r_id)
                            if role_to_remove:
                                roles_to_remove.append(role_to_remove)
                    
                    if roles_to_add or roles_to_remove:
                        await member.add_roles(*roles_to_add, reason="Cập nhật role token")
                        await member.remove_roles(*roles_to_remove, reason="Cập nhật role token")
                        
                except discord.Forbidden:
                    print(f"Lỗi: Không có quyền (Forbidden) để quản lý role cho {user_id} ở {guild.name}.")
                except Exception as e:
                    print(f"Lỗi khi cập nhật role cho {user_id}: {e}")
        
        conn.close()
        print("Tác vụ cập nhật role đã hoàn thành.")

    @update_roles_task.before_loop
    async def before_update_roles_task(self):
        await self.wait_until_ready()

# --- (KẾT THÚC CLASS) ---

# --- KHỞI TẠO BOT (BÊN NGOÀI CLASS) ---
client = BettingBot(intents=intents)
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY')

# --- 4. HÀM LOGIC LÕI (BÊN NGOÀI CLASS) ---

async def internal_create_match(interaction: discord.Interaction, internal_id: str, team_a: str, team_b: str, api_id: int):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO matches (match_id, team_a, team_b, api_match_id, status) VALUES (?, ?, ?, ?, 'open')", 
                       (internal_id, team_a, team_b, api_id))
        conn.commit()
        embed = discord.Embed(title=" kèo mới! 🏟️", description=f"Trận đấu **{team_a}** vs **{team_b}** đã được mở!", color=discord.Color.green())
        embed.add_field(name="Match ID (Nội bộ)", value=f"`{internal_id}`", inline=True)
        embed.add_field(name="Match ID (API)", value=f"`{api_id}`", inline=True)
        embed.add_field(name="Cách cược", value=f"Dùng `/bet id: {internal_id} đội: {team_a}` (hoặc `{team_b}`, hoặc `HÒA`) `tiền: 50`", inline=False)
        if interaction.response.is_done(): await interaction.followup.send(embed=embed)
        else: await interaction.response.send_message(embed=embed)
    except sqlite3.IntegrityError: await interaction.followup.send(f'Lỗi: Match ID `{internal_id}` hoặc API ID `{api_id}` đã tồn tại.', ephemeral=True)
    except Exception as e: await interaction.followup.send(f'Đã xảy ra lỗi: {e}', ephemeral=True)
    finally: conn.close()

async def internal_create_match_for_autofind(channel: discord.TextChannel, internal_id: str, team_a: str, team_b: str, api_id: int):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO matches (match_id, team_a, team_b, api_match_id, status) VALUES (?, ?, ?, ?, 'open')", 
                       (internal_id, team_a, team_b, api_id))
        conn.commit()
        embed = discord.Embed(title=" TỰ ĐỘNG LÊN KÈO! 🏟️", description=f"Trận đấu **{team_a}** vs **{team_b}** đã được mở!", color=discord.Color.blue())
        embed.add_field(name="Match ID (Nội bộ)", value=f"`{internal_id}`", inline=True)
        embed.add_field(name="Match ID (API)", value=f"`{api_id}`", inline=True)
        embed.add_field(name="Cách cược", value=f"Dùng `/bet id: {internal_id} đội: {team_a}` (hoặc `{team_b}`, hoặc `HÒA`) `tiền: 50`", inline=False)
        await channel.send(embed=embed)
    except sqlite3.IntegrityError: print(f"Tác vụ tự động: Lỗi trùng lặp api_id {api_id}. Bỏ qua.")
    except Exception as e: print(f"Tác vụ tự động: Lỗi khi tạo kèo {internal_id}: {e}")
    finally: conn.close()

async def internal_resolve_logic(interaction_response_method, match_id: str, winner_team_name: str):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT status, team_a, team_b FROM matches WHERE match_id = ?", (match_id,))
    match_data = cursor.fetchone()
    if match_data is None: await interaction_response_method(f'Lỗi: Trận `{match_id}` không tồn tại.', ephemeral=True); conn.close(); return
    status, team_a, team_b = match_data
    if status == 'closed' or status == 'cancelled': await interaction_response_method(f'Trận `{match_id}` đã chốt/hủy.', ephemeral=True); conn.close(); return
    cursor.execute("UPDATE matches SET status = 'closed' WHERE match_id = ?", (match_id,)); conn.commit()
    winner_name_lower = winner_team_name.lower()
    team_a_lower, team_b_lower = team_a.lower(), team_b.lower()
    winning_pool_name, losing_pool_1_name, losing_pool_2_name = None, None, None
    if winner_name_lower == 'hòa' or winner_name_lower == 'draw':
        winning_pool_name, losing_pool_1_name, losing_pool_2_name = 'hòa', team_a_lower, team_b_lower
    elif winner_name_lower in team_a_lower:
        winning_pool_name, losing_pool_1_name, losing_pool_2_name = team_a_lower, team_b_lower, 'hòa'
    elif winner_name_lower in team_b_lower:
        winning_pool_name, losing_pool_1_name, losing_pool_2_name = team_b_lower, team_a_lower, 'hòa'
    else:
        await interaction_response_method(f"⚠️ Tên đội thắng (`{winner_team_name}`) không khớp. Dùng `/edit_match` rồi `/resolve_match`.")
        cursor.execute("UPDATE matches SET status = 'locked' WHERE match_id = ?", (match_id,)); conn.commit(); conn.close(); return
    def update_stats(user_id, is_win, profit_loss):
        if is_win:
            cursor.execute("UPDATE users SET wins = wins + 1, profit_loss = profit_loss + ? WHERE user_id = ?", (profit_loss, user_id))
        else:
            cursor.execute("UPDATE users SET losses = losses + 1, profit_loss = profit_loss + ? WHERE user_id = ?", (profit_loss, user_id))
    cursor.execute("SELECT user_id, amount FROM bets WHERE match_id = ? AND team_bet_on = ?", (match_id, winning_pool_name)); winning_bets = cursor.fetchall()
    cursor.execute("SELECT user_id, amount FROM bets WHERE match_id = ? AND team_bet_on = ?", (match_id, losing_pool_1_name)); losing_bets_1 = cursor.fetchall()
    cursor.execute("SELECT user_id, amount FROM bets WHERE match_id = ? AND team_bet_on = ?", (match_id, losing_pool_2_name)); losing_bets_2 = cursor.fetchall()
    total_winning_pot, total_losing_pot_1, total_losing_pot_2 = sum(b[1] for b in winning_bets), sum(b[1] for b in losing_bets_1), sum(b[1] for b in losing_bets_2)
    total_losing_pot, total_pot = total_losing_pot_1 + total_losing_pot_2, total_winning_pot + total_losing_pot
    response_msg = f"🏆 Kết quả trận `{match_id}` ({team_a} vs {team_b}): **{winner_team_name.upper()}** thắng! 🏆\n"
    response_msg += f"Tổng tiền cược pool: {total_pot} (Thắng: {total_winning_pot}, Thua: {total_losing_pot}).\n"
    if total_winning_pot == 0:
        response_msg += f"\nKhông ai cược {winning_pool_name}. {total_losing_pot} token thuộc về nhà cái!"
        for user_id, amount in (losing_bets_1 + losing_bets_2): update_stats(user_id, is_win=False, profit_loss=-amount)
    elif total_losing_pot == 0:
        response_msg += f"\nKhông ai cược thua. Phe {winning_pool_name} được hoàn tiền.\n"
        for user_id, amount in winning_bets:
            update_balance(user_id, amount); user = await client.fetch_user(user_id); response_msg += f"- {user.mention} nhận lại {amount} token.\n"
    else:
        response_msg += "--- Trả thưởng cho phe thắng ---\n"; payout_rate = total_pot / total_winning_pot
        for user_id, amount in winning_bets:
            payout, profit = int(amount * payout_rate), int(amount * payout_rate) - amount
            update_balance(user_id, payout); update_stats(user_id, is_win=True, profit_loss=profit)
            user = await client.fetch_user(user_id); response_msg += f"- {user.mention} (cược {amount}) nhận **{payout} token** (lời {profit}!).\n"
        response_msg += "\n--- Phe thua ---\n"
        for user_id, amount in (losing_bets_1 + losing_bets_2):
            update_stats(user_id, is_win=False, profit_loss=-amount)
            user = await client.fetch_user(user_id); response_msg += f"- {user.mention} mất {amount} token.\n"
    response_msg += "\n--- Kết quả Thách đấu 1v1 ---\n"
    cursor.execute("SELECT challenge_id, challenger_id, opponent_id, challenger_bet_on, opponent_bet_on, amount FROM challenges WHERE match_id = ? AND status = 'accepted'", (match_id,))
    challenges = cursor.fetchall()
    if not challenges: response_msg += "Không có thách đấu 1v1 nào cho trận này.\n"
    else:
        for chal in challenges:
            chal_id, p1_id, p2_id, p1_bet, p2_bet, amount = chal
            p1 = await client.fetch_user(p1_id); p2 = await client.fetch_user(p2_id)
            winner_id, loser_id, winner_name, loser_name = None, None, None, None
            if winning_pool_name == p1_bet: winner_id, loser_id, winner_name, loser_name = p1_id, p2_id, p1.mention, p2.mention
            elif winning_pool_name == p2_bet: winner_id, loser_id, winner_name, loser_name = p2_id, p1_id, p2.mention, p1.mention
            if winner_id:
                payout = amount * 2
                update_balance(winner_id, payout); update_stats(winner_id, is_win=True, profit_loss=amount); update_stats(loser_id, is_win=False, profit_loss=-amount)
                response_msg += f"🔥 {winner_name} thắng {loser_name} và nhận **{payout} token**!\n"
            else:
                update_balance(p1_id, amount); update_balance(p2_id, amount)
                response_msg += f"🤝 Kèo 1v1 giữa {p1.mention} và {p2.mention} kết thúc HÒA! Cả hai được hoàn lại {amount} token.\n"
            cursor.execute("UPDATE challenges SET status = 'resolved' WHERE challenge_id = ?", (chal_id,))
    conn.commit(); conn.close()
    await interaction_response_method(response_msg)

# --- 5. CÁC LỚP UI (BÊN NGOÀI CLASS) ---
class MatchInternalIDModal(ui.Modal, title='Nhập ID Nội bộ cho Kèo'):
    def __init__(self, selected_match_data: dict): super().__init__(); self.selected_match_data = selected_match_data
    internal_id = ui.TextInput(label='ID nội bộ (ví dụ: vnth1)', required=True, style=discord.TextStyle.short)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        await internal_create_match(interaction, self.internal_id.value, self.selected_match_data['team_a'], self.selected_match_data['team_b'], self.selected_match_data['api_id'])
class MatchSelect(ui.Select):
    def __init__(self, matches_data: list):
        options = [discord.SelectOption(label=m['label'], description=m['description'], value=m['value']) for m in matches_data]
        super().__init__(placeholder='Chọn một trận đấu từ danh sách...', options=options)
        self.matches_data_dict = {match['value']: match for match in matches_data}
    async def callback(self, interaction: discord.Interaction):
        modal = MatchInternalIDModal(selected_match_data=self.matches_data_dict[self.values[0]])
        await interaction.response.send_modal(modal)
class MatchSelectView(ui.View):
    def __init__(self, matches_data: list):
        super().__init__(timeout=180); self.add_item(MatchSelect(matches_data))
class SettingsModal(ui.Modal, title='Cài đặt chung cho Bot'):
    def __init__(self):
        super().__init__()
        self.daily_amount = ui.TextInput(label="Token thưởng /daily", default=get_int_setting('daily_amount', 10), style=discord.TextStyle.short)
        self.starting_balance = ui.TextInput(label="Token khởi điểm /register", default=get_int_setting('starting_balance', 100), style=discord.TextStyle.short)
        self.autofind_frequency = ui.TextInput(label="Tần suất AutoFind (giờ)", default=get_int_setting('autofind_frequency', 6), style=discord.TextStyle.short)
        self.add_item(self.daily_amount); self.add_item(self.starting_balance); self.add_item(self.autofind_frequency)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            daily, starting, frequency = int(self.daily_amount.value), int(self.starting_balance.value), int(self.autofind_frequency.value)
            set_setting('daily_amount', daily); set_setting('starting_balance', starting); set_setting('autofind_frequency', frequency)
            client.auto_find_task.change_interval(hours=frequency)
            await interaction.response.send_message("✅ Cài đặt đã được cập nhật!", ephemeral=True)
        except ValueError: await interaction.response.send_message("Lỗi: Vui lòng chỉ nhập số nguyên.", ephemeral=True)
class ChallengeView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="Chấp nhận (Accept)", style=discord.ButtonStyle.green, custom_id="challenge_accept")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        conn = sqlite3.connect('database.db'); cursor = conn.cursor()
        cursor.execute("SELECT * FROM challenges WHERE message_id = ? AND status = 'pending'", (interaction.message.id,))
        challenge = cursor.fetchone()
        if not challenge: await interaction.response.send_message("Kèo thách đấu này đã hết hạn/xử lý.", ephemeral=True); conn.close(); return
        opponent_id, amount = challenge[3], challenge[6]
        if interaction.user.id != opponent_id: await interaction.response.send_message("Bạn không phải là người được thách đấu!", ephemeral=True); conn.close(); return
        opponent_balance = get_balance(opponent_id)
        if opponent_balance < amount: await interaction.response.send_message(f"Bạn không đủ {amount} token.", ephemeral=True); conn.close(); return
        challenger_id = challenge[2]; challenger_balance = get_balance(challenger_id)
        if challenger_balance < amount:
            cursor.execute("UPDATE challenges SET status = 'cancelled' WHERE challenge_id = ?", (challenge[0],)); conn.commit(); conn.close()
            await interaction.message.edit(content=f"Kèo thách đấu đã bị hủy (người thách đấu không đủ token).", view=None)
            await interaction.response.send_message("Kèo đã bị hủy do người thách đấu hết tiền.", ephemeral=True); return
        update_balance(challenger_id, -amount); update_balance(opponent_id, -amount)
        cursor.execute("UPDATE challenges SET status = 'accepted' WHERE challenge_id = ?", (challenge[0],)); conn.commit(); conn.close()
        button.disabled = True; self.children[1].disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(f"✅ {interaction.user.mention} đã chấp nhận kèo! Đã trừ {amount} token của cả hai.")
    @ui.button(label="Từ chối (Decline)", style=discord.ButtonStyle.red, custom_id="challenge_decline")
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        conn = sqlite3.connect('database.db'); cursor = conn.cursor()
        cursor.execute("SELECT opponent_id FROM challenges WHERE message_id = ? AND status = 'pending'", (interaction.message.id,))
        challenge = cursor.fetchone()
        if not challenge: await interaction.response.send_message("Kèo thách đấu này đã hết hạn/xử lý.", ephemeral=True); conn.close(); return
        opponent_id = challenge[0]
        if interaction.user.id != opponent_id: await interaction.response.send_message("Bạn không phải là người được thách đấu!", ephemeral=True); conn.close(); return
        cursor.execute("UPDATE challenges SET status = 'declined' WHERE message_id = ?", (interaction.message.id,)); conn.commit(); conn.close()
        button.disabled = True; self.children[0].disabled = True
        await interaction.message.edit(content=f"Kèo thách đấu đã bị từ chối bởi {interaction.user.mention}.", view=None)
        await interaction.response.send_message("Bạn đã từ chối kèo.", ephemeral=True)

# --- 6. HÀM API HELPER (BÊN NGOÀI CLASS) ---
def get_team_id(team_name: str) -> int | None:
    if not RAPIDAPI_KEY: return None
    url = "https://api-football-v1.p.rapidapi.com/v3/teams"; querystring = {"search": team_name}; headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"}
    try: response = requests.get(url, headers=headers, params=querystring, timeout=10); response.raise_for_status(); data = response.json()
    except Exception: return None
    if data['response']: return data['response'][0]['team']['id']
    return None
def find_future_fixtures(team_a_id: int, team_b_id: int) -> list:
    if not RAPIDAPI_KEY: return []
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"; current_season = datetime.now().year
    querystring = {"team": str(team_a_id), "season": str(current_season)}; headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"}
    found_matches = []
    try: response = requests.get(url, headers=headers, params=querystring, timeout=10); response.raise_for_status(); data = response.json()
    except Exception: return []
    if not data['response']: return []
    for fixture in data['response']:
        opponent_id = None
        if fixture['teams']['home']['id'] == team_a_id: opponent_id = fixture['teams']['away']['id']
        elif fixture['teams']['away']['id'] == team_a_id: opponent_id = fixture['teams']['home']['id']
        if opponent_id == team_b_id and fixture['fixture']['status']['short'] in ['NS', 'TBD', 'PST']:
            found_matches.append(fixture)
    return found_matches
def get_upcoming_fixtures_from_watchlist(days_ahead=3):
    if not RAPIDAPI_KEY: return []
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT league_id, league_name FROM watched_leagues"); leagues = cursor.fetchall(); conn.close()
    if not leagues: return "Watchlist trống."
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"}
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"; current_season = datetime.now().year
    date_from = date.today().isoformat(); date_to = (date.today() + timedelta(days=days_ahead)).isoformat()
    all_fixtures = []
    for league_id, league_name in leagues:
        querystring = {"league": str(league_id), "season": str(current_season), "from": date_from, "to": date_to, "status": "NS"}
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=10); response.raise_for_status(); data = response.json()
            if not data['response']: continue
            for fixture in data['response']: fixture['league_name'] = league_name; all_fixtures.append(fixture)
        except Exception as e: print(f"Lỗi khi lấy /upcoming cho giải {league_id}: {e}")
    all_fixtures.sort(key=lambda f: f['fixture']['timestamp'])
    return all_fixtures

# --- 7. CÁC LỆNH (COMMANDS) (BÊN NGOÀI CLASS) ---

# --- Nhóm Lệnh User ---
@client.tree.command(name="register", description="Đăng ký tài khoản để nhận token bắt đầu.")
async def register(interaction: discord.Interaction):
    starting_balance = get_int_setting('starting_balance', 100)
    if register_user(interaction.user.id, starting_balance):
        await interaction.response.send_message(f'🎉 Chào mừng {interaction.user.mention}! Bạn đã nhận được {starting_balance} token.', ephemeral=True)
    else: await interaction.response.send_message('Bạn đã đăng ký rồi.', ephemeral=True)

@client.tree.command(name="balance", description="Xem số token hiện tại của bạn.")
async def balance(interaction: discord.Interaction):
    user_balance = get_balance(interaction.user.id)
    if user_balance is None: await interaction.response.send_message('Bạn chưa đăng ký! Dùng lệnh `/register` trước nhé.', ephemeral=True)
    else: await interaction.response.send_message(f'💰 Số token của bạn là: **{user_balance}** token.', ephemeral=True)

@client.tree.command(name="bet", description="Đặt cược cho một đội (hoặc HÒA).")
@app_commands.describe(id="ID nội bộ của trận đấu (ví dụ: vnvsth)", đội="Tên đội bạn cược (hoặc gõ 'HÒA')", tiền="Số token bạn muốn cược")
async def bet(interaction: discord.Interaction, id: str, đội: str, tiền: int):
    user_id = interaction.user.id
    if tiền <= 0: await interaction.response.send_message('Số tiền cược phải lớn hơn 0.', ephemeral=True); return
    user_balance = get_balance(user_id)
    if user_balance is None: await interaction.response.send_message('Bạn chưa đăng ký! Dùng lệnh `/register` trước nhé.', ephemeral=True); return
    if user_balance < tiền: await interaction.response.send_message(f'Bạn không đủ token! Bạn chỉ có {user_balance} token.', ephemeral=True); return
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT team_a, team_b, status FROM matches WHERE match_id = ?", (id,))
    match = cursor.fetchone()
    if match is None: await interaction.response.send_message(f'Trận đấu với ID `{id}` không tồn tại.', ephemeral=True); conn.close(); return
    team_a, team_b, status = match
    if status == 'locked': await interaction.response.send_message(f'Trận đấu `{id}` đã khóa cược.', ephemeral=True); conn.close(); return
    if status == 'closed' or status == 'cancelled': await interaction.response.send_message(f'Trận đấu `{id}` đã kết thúc hoặc bị hủy.', ephemeral=True); conn.close(); return
    team_bet_on = None; đội_lower = đội.lower()
    if đội_lower == team_a.lower(): team_bet_on = team_a.lower()
    elif đội_lower == team_b.lower(): team_bet_on = team_b.lower()
    elif đội_lower == 'hòa' or đội_lower == 'draw': team_bet_on = 'hòa'
    else: await interaction.response.send_message(f"Tên cược không hợp lệ. Vui lòng chọn `{team_a}`, `{team_b}`, hoặc `HÒA`.", ephemeral=True); conn.close(); return
    try:
        update_balance(user_id, -tiền)
        cursor.execute("INSERT INTO bets (user_id, match_id, team_bet_on, amount) VALUES (?, ?, ?, ?)", (user_id, id, team_bet_on, tiền))
        conn.commit(); conn.close()
        await interaction.response.send_message(f'✅ {interaction.user.mention} đã cược **{tiền} token** cho **{đội.upper()}** trong trận `{id}`!')
    except Exception as e: conn.close(); await interaction.response.send_message(f'Đã xảy ra lỗi khi đặt cược: {e}', ephemeral=True)

@client.tree.command(name="daily", description="Nhận token thưởng mỗi 24 giờ.")
async def daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    daily_amount = get_int_setting('daily_amount', 10)
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT last_daily, balance FROM users WHERE user_id = ?", (user_id,)); result = cursor.fetchone()
    if result is None: await interaction.response.send_message('Bạn chưa đăng ký! Dùng lệnh `/register` trước nhé.', ephemeral=True); conn.close(); return
    last_daily_str, balance = result; last_daily_dt = datetime.fromisoformat(last_daily_str)
    if datetime.now() - last_daily_dt < timedelta(hours=24):
        cooldown_ends = last_daily_dt + timedelta(hours=24)
        await interaction.response.send_message(f'Bạn đã nhận thưởng hôm nay. Quay lại sau <t:{int(cooldown_ends.timestamp())}:R>.', ephemeral=True)
    else:
        new_balance = balance + daily_amount
        cursor.execute("UPDATE users SET balance = ?, last_daily = ? WHERE user_id = ?", (new_balance, datetime.now().isoformat(), user_id)); conn.commit()
        await interaction.response.send_message(f'🎉 Bạn đã nhận được **{daily_amount} token**! Số dư mới: {new_balance} token.')
    conn.close()

@client.tree.command(name="transfer", description="Chuyển token cho người dùng khác.")
@app_commands.describe(người_nhận="Người bạn muốn chuyển token", số_tiền="Số token muốn chuyển")
async def transfer(interaction: discord.Interaction, người_nhận: discord.Member, số_tiền: int):
    sender_id, receiver_id = interaction.user.id, người_nhận.id
    if sender_id == receiver_id: await interaction.response.send_message("Bạn không thể tự chuyển token cho mình.", ephemeral=True); return
    if số_tiền <= 0: await interaction.response.send_message("Số tiền chuyển phải lớn hơn 0.", ephemeral=True); return
    sender_balance = get_balance(sender_id)
    if sender_balance is None: await interaction.response.send_message("Bạn chưa đăng ký! Dùng `/register`.", ephemeral=True); return
    if sender_balance < số_tiền: await interaction.response.send_message(f"Bạn không đủ token. Bạn chỉ có {sender_balance} token.", ephemeral=True); return
    if get_balance(receiver_id) is None: register_user(receiver_id, get_int_setting('starting_balance', 100))
    update_balance(sender_id, -số_tiền); update_balance(receiver_id, số_tiền)
    await interaction.response.send_message(f'✅ {interaction.user.mention} đã chuyển **{số_tiền} token** cho {người_nhận.mention}!')

@client.tree.command(name="leaderboard", description="Xem bảng xếp hạng 10 phú hộ token.")
async def leaderboard(interaction: discord.Interaction):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10"); results = cursor.fetchall(); conn.close()
    embed = discord.Embed(title="👑 Bảng Xếp Hạng Phú Hộ 👑", color=discord.Color.gold())
    if not results: embed.description = "Chưa có ai trong bảng xếp hạng."; await interaction.response.send_message(embed=embed); return
    leaderboard_text = ""; medals = ["🥇", "🥈", "🥉"]
    for i, (user_id, balance) in enumerate(results):
        try: user = await client.fetch_user(user_id); user_name = user.display_name
        except discord.NotFound: user_name = f"User (ID: {user_id})"
        rank_icon = medals[i] if i < 3 else f"**{i+1}.**"
        leaderboard_text += f"{rank_icon} {user_name}: **{balance}** token\n"
    embed.description = leaderboard_text
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="my_bets", description="Xem các kèo bạn đang cược (chưa chốt).")
async def my_bets(interaction: discord.Interaction):
    user_id = interaction.user.id
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    query = """
    SELECT m.match_id, m.team_a, m.team_b, b.team_bet_on, b.amount, m.status
    FROM bets b JOIN matches m ON b.match_id = m.match_id
    WHERE b.user_id = ? AND m.status IN ('open', 'locked') ORDER BY m.match_id
    """
    cursor.execute(query, (user_id,)); bets = cursor.fetchall(); conn.close()
    if not bets: await interaction.response.send_message("Bạn không có kèo nào đang chờ.", ephemeral=True); return
    embed = discord.Embed(title=f"Kèo đang cược của {interaction.user.display_name}", color=discord.Color.blue())
    for match_id, team_a, team_b, team_bet_on, amount, status in bets:
        status_text = "Đang mở cược" if status == 'open' else "Đã khóa cược"
        embed.add_field(name=f"`{match_id}`: {team_a} vs {team_b}", value=f"Bạn cược **{amount} token** cho **{team_bet_on.upper()}**\n*Trạng thái: {status_text}*", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="match_info", description="Xem tỷ lệ cược (tổng tiền) cho một trận đấu.")
@app_commands.describe(id="ID nội bộ của trận đấu")
async def match_info(interaction: discord.Interaction, id: str):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT team_a, team_b, status FROM matches WHERE match_id = ?", (id,)); match = cursor.fetchone()
    if match is None: await interaction.response.send_message(f'Lỗi: Trận đấu `{id}` không tồn tại.', ephemeral=True); conn.close(); return
    team_a, team_b, status = match
    cursor.execute("SELECT team_bet_on, SUM(amount), COUNT(user_id) FROM bets WHERE match_id = ? GROUP BY team_bet_on", (id,)); pools = cursor.fetchall(); conn.close()
    embed = discord.Embed(title=f"📊 Thông tin kèo `{id}`: {team_a} vs {team_b}", color=discord.Color.orange())
    embed.add_field(name="Trạng thái", value=status.capitalize(), inline=False)
    pool_data = {team_a.lower(): {'amount': 0, 'count': 0}, team_b.lower(): {'amount': 0, 'count': 0}, 'hòa': {'amount': 0, 'count': 0}}
    total_pot = 0
    for team_name, amount, count in pools:
        if team_name in pool_data: pool_data[team_name]['amount'] = amount; pool_data[team_name]['count'] = count; total_pot += amount
    embed.add_field(name=f"Tổng tiền cược (Tất cả phe)", value=f"**{total_pot} token**", inline=False)
    for team_name_lower, data in pool_data.items():
        team_display_name = team_name_lower.capitalize()
        if team_name_lower == team_a.lower(): team_display_name = team_a
        if team_name_lower == team_b.lower(): team_display_name = team_b
        embed.add_field(name=f"Phe {team_display_name}", value=f"**{data['amount']} token** ({data['count']} lượt cược)", inline=True)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="stats", description="Xem thống kê cá cược của bạn.")
async def stats(interaction: discord.Interaction):
    user_id = interaction.user.id
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT balance, wins, losses, profit_loss FROM users WHERE user_id = ?", (user_id,)); result = cursor.fetchone(); conn.close()
    if result is None: await interaction.response.send_message("Bạn chưa đăng ký! Dùng `/register`.", ephemeral=True); return
    balance, wins, losses, profit_loss = result
    total_bets = wins + losses; win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    embed = discord.Embed(title=f"📊 Thống kê của {interaction.user.display_name}", color=discord.Color.magenta())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.add_field(name="💰 Số dư Token", value=f"**{balance}**", inline=False)
    embed.add_field(name="📈 Tổng Lợi nhuận/Thua lỗ (P/L)", value=f"**{profit_loss:+}** token", inline=False)
    embed.add_field(name="🏆 Thắng", value=f"{wins}", inline=True)
    embed.add_field(name="📉 Thua", value=f"{losses}", inline=True)
    embed.add_field(name="🎯 Tỷ lệ thắng", value=f"{win_rate:.2f}%", inline=True)
    await interaction.response.send_message(embed=embed)

@client.tree.command(name="upcoming", description="Xem các kèo sắp diễn ra trong 3 ngày tới từ watchlist.")
async def upcoming(interaction: discord.Interaction):
    await interaction.response.defer()
    fixtures_data = get_upcoming_fixtures_from_watchlist(days_ahead=3)
    if isinstance(fixtures_data, str): await interaction.followup.send(fixtures_data, ephemeral=True); return
    if not fixtures_data: await interaction.followup.send("Không tìm thấy trận nào sắp diễn ra (3 ngày tới) trong watchlist."); return
    embed = discord.Embed(title="📅 Các kèo sắp diễn ra (3 ngày tới)", color=discord.Color.teal())
    leagues = {}
    for f in fixtures_data:
        league_name = f['league_name']
        if league_name not in leagues: leagues[league_name] = []
        leagues[league_name].append(f)
    for league_name, fixtures in leagues.items():
        field_value = ""
        for f in fixtures: team_a, team_b, timestamp = f['teams']['home']['name'], f['teams']['away']['name'], f['fixture']['timestamp']; field_value += f"- {team_a} vs {team_b} (<t:{timestamp}:R>)\n"
        embed.add_field(name=f"⚽ {league_name}", value=field_value, inline=False)
    await interaction.followup.send(embed=embed)

@client.tree.command(name="challenge", description="Thách đấu 1v1 với một người dùng khác.")
@app_commands.describe(user="Người bạn muốn thách đấu", match_id="ID nội bộ của trận đấu", cược_cho="Đội bạn cược (không thể cược HÒA)", số_tiền="Số token thách đấu")
async def challenge(interaction: discord.Interaction, user: discord.Member, match_id: str, cược_cho: str, số_tiền: int):
    challenger_id, opponent_id = interaction.user.id, user.id
    if challenger_id == opponent_id: await interaction.response.send_message("Bạn không thể tự thách đấu mình.", ephemeral=True); return
    if số_tiền <= 0: await interaction.response.send_message("Số tiền phải lớn hơn 0.", ephemeral=True); return
    if user.bot: await interaction.response.send_message("Bạn không thể thách đấu bot.", ephemeral=True); return
    challenger_balance = get_balance(challenger_id)
    if challenger_balance is None: await interaction.response.send_message("Bạn chưa đăng ký! Dùng `/register`.", ephemeral=True); return
    if challenger_balance < số_tiền: await interaction.response.send_message(f"Bạn không đủ {số_tiền} token.", ephemeral=True); return
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT team_a, team_b, status FROM matches WHERE match_id = ?", (match_id,)); match = cursor.fetchone()
    if match is None: await interaction.response.send_message(f'Trận đấu `{match_id}` không tồn tại.', ephemeral=True); conn.close(); return
    team_a, team_b, status = match
    if status != 'open': await interaction.response.send_message(f'Trận đấu `{match_id}` không còn mở cược.', ephemeral=True); conn.close(); return
    challenger_bet_on, opponent_bet_on = None, None
    if cược_cho.lower() == team_a.lower(): challenger_bet_on, opponent_bet_on = team_a.lower(), team_b.lower()
    elif cược_cho.lower() == team_b.lower(): challenger_bet_on, opponent_bet_on = team_b.lower(), team_a.lower()
    else: await interaction.response.send_message("Thách đấu 1v1 chỉ hỗ trợ cược cho Đội A hoặc Đội B.", ephemeral=True); conn.close(); return
    try:
        cursor.execute("INSERT INTO challenges (match_id, challenger_id, opponent_id, challenger_bet_on, opponent_bet_on, amount, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')", (match_id, challenger_id, opponent_id, challenger_bet_on, opponent_bet_on, số_tiền)); challenge_id = cursor.lastrowid
        conn.commit()
        embed = discord.Embed(title="⚔️ THÁCH ĐẤU 1V1 ⚔️", color=discord.Color.red()); embed.description = f"{interaction.user.mention} thách đấu {user.mention}!"
        embed.add_field(name="Trận đấu", value=f"`{match_id}` ({team_a} vs {team_b})"); embed.add_field(name="Tiền cược", value=f"**{số_tiền} token**")
        embed.add_field(name=f"{interaction.user.display_name} cược cho", value=f"**{cược_cho.upper()}**", inline=False)
        embed.add_field(name=f"{user.display_name} (nếu chấp nhận) sẽ cược cho", value=f"**{opponent_bet_on.upper()}**", inline=False)
        view = ChallengeView()
        await interaction.response.send_message(content=f"Này {user.mention}, bạn có một lời thách đấu!", embed=embed, view=view)
        message = await interaction.original_response()
        cursor.execute("UPDATE challenges SET message_id = ? WHERE challenge_id = ?", (message.id, challenge_id)); conn.commit()
    except Exception as e: await interaction.response.send_message(f"Lỗi khi tạo thách đấu: {e}", ephemeral=True)
    finally: conn.close()

# --- Nhóm Lệnh Admin ---
@client.tree.command(name="find_match", description="[ADMIN] Tự động tìm trận đấu để tạo kèo.")
@app_commands.describe(team_a_name="Tên đội A (ví dụ: Vietnam)", team_b_name="Tên đội B (ví dụ: Thailand)")
@app_commands.checks.has_permissions(administrator=True)
async def find_match(interaction: discord.Interaction, team_a_name: str, team_b_name: str):
    if not RAPIDAPI_KEY: await interaction.response.send_message("Lỗi: Admin chưa cấu hình `RAPIDAPI_KEY`!", ephemeral=True); return
    await interaction.response.defer(thinking=True, ephemeral=True)
    team_a_id = get_team_id(team_a_name); team_b_id = get_team_id(team_b_name)
    if team_a_id is None: await interaction.followup.send(f'Không tìm thấy đội "{team_a_name}".', ephemeral=True); return
    if team_b_id is None: await interaction.followup.send(f'Không tìm thấy đội "{team_b_name}".', ephemeral=True); return
    fixtures = find_future_fixtures(team_a_id, team_b_id)
    if not fixtures: await interaction.followup.send(f'Không tìm thấy trận đấu sắp diễn ra nào giữa 2 đội.', ephemeral=True); return
    matches_data_for_select = []
    for f in fixtures[:25]:
        api_id, team_a, team_b = f['fixture']['id'], f['teams']['home']['name'], f['teams']['away']['name']
        league, date_str = f['league']['name'], f['fixture']['date']
        friendly_date = datetime.fromisoformat(date_str).strftime('%d/%m/%Y %H:%M')
        matches_data_for_select.append({'label': f"{team_a} vs {team_b}", 'description': f"({league}) - {friendly_date}", 'value': str(api_id), 'api_id': api_id, 'team_a': team_a, 'team_b': team_b})
    view = MatchSelectView(matches_data=matches_data_for_select)
    await interaction.followup.send("Tìm thấy các trận sau. Vui lòng chọn:", view=view, ephemeral=True)

@client.tree.command(name="create_match_manual", description="[ADMIN] Tạo kèo thủ công (dùng khi /find_match lỗi).")
@app_commands.describe(id="ID nội bộ", team_a="Tên đội A", team_b="Tên đội B", api_id="ID trận đấu trên API")
@app_commands.checks.has_permissions(administrator=True)
async def create_match_manual(interaction: discord.Interaction, id: str, team_a: str, team_b: str, api_id: int):
    await interaction.response.defer(thinking=True, ephemeral=True)
    await internal_create_match(interaction, id, team_a, team_b, api_id)

@client.tree.command(name="resolve_match", description="[ADMIN] Chốt kết quả thủ công.")
@app_commands.describe(id="ID nội bộ của trận đấu", đội_thắng="Tên đội thắng (hoặc 'HÒA')")
@app_commands.checks.has_permissions(administrator=True)
async def resolve_match(interaction: discord.Interaction, id: str, đội_thắng: str):
    await interaction.response.defer()
    await internal_resolve_logic(interaction.followup.send, match_id=id, winner_team_name=đội_thắng)

@client.tree.command(name="auto_resolve", description="[ADMIN] Tự động lấy kết quả từ API và trả thưởng.")
@app_commands.describe(id="ID nội bộ của trận đấu")
@app_commands.checks.has_permissions(administrator=True)
async def auto_resolve(interaction: discord.Interaction, id: str):
    if not RAPIDAPI_KEY: await interaction.response.send_message("Lỗi: Admin chưa cấu hình `RAPIDAPI_KEY`!", ephemeral=True); return
    await interaction.response.defer()
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT api_match_id, status FROM matches WHERE match_id = ?", (id,)); match_info = cursor.fetchone(); conn.close()
    if match_info is None: await interaction.followup.send(f'Lỗi: Không tìm thấy trận đấu `{id}`.'); return
    api_match_id, status = match_info
    if status == 'closed' or status == 'cancelled': await interaction.followup.send(f'Trận đấu `{id}` đã được chốt hoặc đã bị hủy.'); return
    if api_match_id is None: await interaction.followup.send(f'Lỗi: Trận đấu `{id}` không có `api_id`.'); return
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"; querystring = {"id": str(api_match_id)}
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"}
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=10); response.raise_for_status(); data = response.json()
        if not data['response']: await interaction.followup.send(f'Lỗi: API không trả về dữ liệu cho `api_id: {api_match_id}`.'); return
        fixture_data = data['response'][0]; match_status = fixture_data['fixture']['status']['short']
        if match_status not in ['FT', 'AET', 'PEN']: await interaction.followup.send(f'Trận đấu `{id}` (API: {api_match_id}) chưa kết thúc! Trạng thái: {match_status}.'); return
        teams, winner_name = fixture_data['teams'], None
        is_draw = (fixture_data['teams']['home']['winner'] is False and fixture_data['teams']['away']['winner'] is False)
        if is_draw: winner_name = "HÒA"
        elif teams['home']['winner']: winner_name = teams['home']['name']
        elif teams['away']['winner']: winner_name = teams['away']['name']
        elif match_status == 'PST': await interaction.followup.send(f'Trận đấu `{id}` đã bị hoãn. Dùng `/cancel_match`.'); return
        else: await interaction.followup.send(f'Lỗi: Không thể xác định đội thắng. Trạng thái: {match_status}.'); return
        await internal_resolve_logic(interaction.followup.send, match_id=id, winner_team_name=winner_name)
    except Exception as e: await interaction.followup.send(f'Lỗi khi gọi hoặc phân tích API: {e}')

@client.tree.command(name="lock_bets", description="[ADMIN] Khóa cược (ngăn cược mới) cho một trận đấu.")
@app_commands.describe(id="ID nội bộ của trận đấu")
@app_commands.checks.has_permissions(administrator=True)
async def lock_bets(interaction: discord.Interaction, id: str):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT status FROM matches WHERE match_id = ?", (id,)); result = cursor.fetchone()
    if result is None: await interaction.response.send_message(f'Lỗi: Trận đấu `{id}` không tồn tại.', ephemeral=True); conn.close(); return
    if result[0] != 'open': await interaction.response.send_message(f'Trận đấu `{id}` không ở trạng thái "open".', ephemeral=True); conn.close(); return
    cursor.execute("UPDATE matches SET status = 'locked' WHERE match_id = ?", (id,)); conn.commit(); conn.close()
    await interaction.response.send_message(f'🔒 Kèo `{id}` đã được khóa! Không nhận cược mới.')

@client.tree.command(name="cancel_match", description="[ADMIN] Hủy một kèo và hoàn tiền cho tất cả người cược.")
@app_commands.describe(id="ID nội bộ của trận đấu")
@app_commands.checks.has_permissions(administrator=True)
async def cancel_match(interaction: discord.Interaction, id: str):
    await interaction.response.defer()
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT status FROM matches WHERE match_id = ?", (id,)); result = cursor.fetchone()
    if result is None: await interaction.followup.send(f'Lỗi: Trận đấu `{id}` không tồn tại.'); conn.close(); return
    if result[0] == 'closed' or result[0] == 'cancelled': await interaction.followup.send(f'Trận đấu `{id}` đã đóng/hủy.'); conn.close(); return
    cursor.execute("SELECT user_id, amount FROM bets WHERE match_id = ?", (id,)); bets = cursor.fetchall()
    refund_msg = f"🚫 Kèo `{id}` đã bị hủy! Hoàn tiền:\n"
    if not bets: refund_msg += "- Không có ai cược pool.\n"
    for user_id, amount in bets: update_balance(user_id, amount); user = await client.fetch_user(user_id); refund_msg += f"- Pool: {user.mention} nhận lại {amount} token.\n"
    cursor.execute("SELECT challenger_id, opponent_id, amount FROM challenges WHERE match_id = ? AND (status = 'accepted' OR status = 'pending')", (id,)); challenges = cursor.fetchall()
    if not challenges: refund_msg += "- Không có kèo 1v1 nào.\n"
    for p1_id, p2_id, amount in challenges:
        # Chỉ hoàn tiền cho người đã 'accepted', người 'pending' không bị trừ
        cursor.execute("SELECT status FROM challenges WHERE challenger_id = ? AND opponent_id = ? AND match_id = ?", (p1_id, p2_id, id))
        chal_status = cursor.fetchone()[0]
        if chal_status == 'accepted':
            update_balance(p1_id, amount); update_balance(p2_id, amount)
            p1, p2 = await client.fetch_user(p1_id), await client.fetch_user(p2_id)
            refund_msg += f"- 1v1 (Accepted): {p1.mention} và {p2.mention} mỗi người nhận lại {amount} token.\n"
        else: # Pending
             p1 = await client.fetch_user(p1_id); refund_msg += f"- 1v1 (Pending): Kèo của {p1.mention} đã bị hủy.\n"
    cursor.execute("UPDATE matches SET status = 'cancelled' WHERE match_id = ?", (id,))
    cursor.execute("UPDATE challenges SET status = 'cancelled' WHERE match_id = ? AND (status = 'accepted' OR status = 'pending')", (id,))
    conn.commit(); conn.close()
    await interaction.followup.send(refund_msg)

@client.tree.command(name="edit_match", description="[ADMIN] Sửa thông tin của một kèo (tên đội, api_id).")
@app_commands.describe(id="ID nội bộ", team_a="Tên MỚI cho đội A", team_b="Tên MỚI cho đội B", api_id="ID MỚI trên API")
@app_commands.checks.has_permissions(administrator=True)
async def edit_match(interaction: discord.Interaction, id: str, team_a: str = None, team_b: str = None, api_id: int = 0):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT team_a, team_b, api_match_id FROM matches WHERE match_id = ?", (id,)); result = cursor.fetchone()
    if result is None: await interaction.response.send_message(f'Lỗi: Trận đấu `{id}` không tồn tại.', ephemeral=True); conn.close(); return
    current_a, current_b, current_api_id = result
    new_a, new_b = (team_a if team_a is not None else current_a), (team_b if team_b is not None else current_b)
    new_api_id = api_id if api_id != 0 else current_api_id
    cursor.execute("UPDATE matches SET team_a = ?, team_b = ?, api_match_id = ? WHERE match_id = ?", (new_a, new_b, new_api_id, id)); conn.commit(); conn.close()
    await interaction.response.send_message(f'✅ Kèo `{id}` đã cập nhật.', ephemeral=True)

@client.tree.command(name="admin_adjust_tokens", description="[ADMIN] Cộng hoặc trừ token của một thành viên.")
@app_commands.describe(user="Người dùng cần điều chỉnh", amount="Số token (dùng số âm để trừ)", reason="Lý do điều chỉnh (không bắt buộc)")
@app_commands.checks.has_permissions(administrator=True)
async def admin_adjust_tokens(interaction: discord.Interaction, user: discord.Member, amount: int, reason: str = None):
    if user.bot: await interaction.response.send_message("Không thể điều chỉnh token của bot.", ephemeral=True); return
    if amount == 0: await interaction.response.send_message("Số lượng phải khác 0.", ephemeral=True); return
    user_balance = get_balance(user.id)
    if user_balance is None: register_user(user.id, get_int_setting('starting_balance', 100))
    update_balance(user.id, amount); new_balance = get_balance(user.id)
    action_str = "cộng" if amount > 0 else "trừ"; reason_str = f" với lý do: {reason}" if reason else ""
    await interaction.response.send_message(f"✅ Đã {action_str} **{abs(amount)} token** cho {user.mention}{reason_str}.\nSố dư mới: **{new_balance} token**.")

@client.tree.command(name="settings", description="[ADMIN] Mở bảng cài đặt chung cho bot.")
@app_commands.checks.has_permissions(administrator=True)
async def settings(interaction: discord.Interaction):
    await interaction.response.send_modal(SettingsModal())

# --- Nhóm Lệnh Admin Role Tier ---
role_tier_group = app_commands.Group(name="roles", description="Quản lý hệ thống Role tự động theo token", default_permissions=discord.Permissions(administrator=True))
@role_tier_group.command(name="set_tier", description="[ADMIN] Đặt một mốc role (ví dụ: Role 'Phú Hộ' cần 10000 token).")
@app_commands.describe(role="Role Discord", min_tokens="Số token tối thiểu để đạt được role này")
async def set_role_tier(interaction: discord.Interaction, role: discord.Role, min_tokens: int):
    if not interaction.guild: await interaction.response.send_message("Lệnh này chỉ dùng trong server.", ephemeral=True); return
    if role.is_default(): await interaction.response.send_message("Không thể dùng role @everyone.", ephemeral=True); return
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO role_tiers (role_id, min_tokens, guild_id) VALUES (?, ?, ?)", (role.id, min_tokens, interaction.guild.id)); conn.commit()
        await interaction.response.send_message(f"✅ Đã cài đặt: Role {role.mention} sẽ được gán cho ai có >= **{min_tokens} token**.", ephemeral=True)
    except sqlite3.IntegrityError: await interaction.response.send_message(f"Lỗi: Đã có một role khác được gán cho mốc {min_tokens} token.", ephemeral=True)
    finally: conn.close()
@role_tier_group.command(name="remove_tier", description="[ADMIN] Xóa một mốc role khỏi hệ thống.")
@app_commands.describe(role="Role Discord cần xóa")
async def remove_role_tier(interaction: discord.Interaction, role: discord.Role):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("DELETE FROM role_tiers WHERE role_id = ?", (role.id,)); changes = conn.total_changes
    conn.commit(); conn.close()
    if changes > 0: await interaction.response.send_message(f"✅ Đã xóa mốc role {role.mention} khỏi hệ thống.", ephemeral=True)
    else: await interaction.response.send_message("Không tìm thấy role đó trong hệ thống.", ephemeral=True)
@role_tier_group.command(name="list_tiers", description="[ADMIN] Xem tất cả các mốc role đã cài đặt.")
async def list_role_tiers(interaction: discord.Interaction):
    if not interaction.guild: await interaction.response.send_message("Lệnh này chỉ dùng trong server.", ephemeral=True); return
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT role_id, min_tokens FROM role_tiers WHERE guild_id = ? ORDER BY min_tokens DESC", (interaction.guild.id,)); tiers = cursor.fetchall(); conn.close()
    if not tiers: await interaction.response.send_message("Chưa có mốc role nào được cài đặt.", ephemeral=True); return
    embed = discord.Embed(title="👑 Các Mốc Role Token", color=discord.Color.gold())
    desc = ""
    for role_id, min_tokens in tiers:
        role = interaction.guild.get_role(role_id); desc += f"{role.mention if role else f'Role (ID: {role_id})'}: **{min_tokens} token**\n"
    embed.description = desc
    await interaction.response.send_message(embed=embed, ephemeral=True)
client.tree.add_command(role_tier_group)

# --- Nhóm Lệnh Watchlist ---
watchlist_group = app_commands.Group(name="watchlist", description="Quản lý danh sách giải đấu tự động theo dõi", default_permissions=discord.Permissions(administrator=True))
@watchlist_group.command(name="add", description="[ADMIN] Thêm giải đấu vào watchlist.")
@app_commands.describe(league_id="ID giải đấu (từ API-Football)", league_name="Tên giải (để dễ nhớ)")
async def watchlist_add(interaction: discord.Interaction, league_id: int, league_name: str):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try: cursor.execute("INSERT INTO watched_leagues (league_id, league_name) VALUES (?, ?)", (league_id, league_name)); conn.commit()
    except sqlite3.IntegrityError: await interaction.response.send_message(f'Lỗi: Giải {league_id} đã có trong watchlist.', ephemeral=True); conn.close(); return
    await interaction.response.send_message(f'✅ Đã thêm **{league_name}** (ID: {league_id}) vào watchlist.', ephemeral=True); conn.close()
@watchlist_group.command(name="remove", description="[ADMIN] Xóa giải đấu khỏi watchlist.")
@app_commands.describe(league_id="ID giải đấu cần xóa")
async def watchlist_remove(interaction: discord.Interaction, league_id: int):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("DELETE FROM watched_leagues WHERE league_id = ?", (league_id,)); changes = conn.total_changes; conn.commit(); conn.close()
    if changes > 0: await interaction.response.send_message(f'✅ Đã xóa giải (ID: {league_id}) khỏi watchlist.', ephemeral=True)
    else: await interaction.response.send_message(f'Không tìm thấy giải ID {league_id}.', ephemeral=True)
@watchlist_group.command(name="list", description="[ADMIN] Xem watchlist hiện tại.")
async def watchlist_list(interaction: discord.Interaction):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT league_id, league_name FROM watched_leagues"); leagues = cursor.fetchall(); conn.close()
    if not leagues: await interaction.response.send_message("Watchlist đang trống.", ephemeral=True); return
    embed = discord.Embed(title="📋 Danh sách Giải đấu đang theo dõi", color=discord.Color.blue())
    embed.description = "\n".join([f"- **{name}** (ID: `{id}`)" for id, name in leagues])
    await interaction.response.send_message(embed=embed, ephemeral=True)
client.tree.add_command(watchlist_group)

# --- Nhóm Lệnh Tác vụ Nền ---
autofind_group = app_commands.Group(name="autofind", description="Quản lý tác vụ tự động tìm kèo", default_permissions=discord.Permissions(administrator=True))
@autofind_group.command(name="start", description="[ADMIN] Bật tính năng tự động tìm kèo.")
@app_commands.describe(channel="Kênh chat để bot thông báo kèo mới.")
@app_commands.checks.has_permissions(administrator=True)
async def autofind_start(interaction: discord.Interaction, channel: discord.TextChannel):
    # --- ĐÂY LÀ HÀM ĐÃ SỬA LỖI TIMEOUT ---
    await interaction.response.defer(ephemeral=True) 
    set_setting('autofind_channel_id', channel.id)
    try:
        client.auto_find_task.restart() 
    except Exception as e:
        print(f"Lỗi khi restart autofind_task (có thể bỏ qua): {e}")
    freq = get_int_setting('autofind_frequency', 6)
    await interaction.followup.send(f'✅ Đã kích hoạt tính năng tự động tìm kèo!\n'
                                    f'Bot sẽ đăng kèo mới vào {channel.mention} (Tần suất: {freq} giờ/lần).')
@autofind_group.command(name="stop", description="[ADMIN] Tắt tính năng tự động tìm kèo.")
@app_commands.checks.has_permissions(administrator=True)
async def autofind_stop(interaction: discord.Interaction):
    set_setting('autofind_channel_id', None)
    await interaction.response.send_message(f'❌ Đã tắt tính năng tự động tìm kèo. Bot sẽ ngừng ở lần lặp tiếp theo.')
client.tree.add_command(autofind_group)

# --- 8. Xử lý Lỗi (BÊN NGOÀI CLASS) ---
@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("Bạn không có quyền dùng lệnh này!", ephemeral=True)
    elif isinstance(error, app_commands.errors.CommandInvokeError):
        print(f"Lỗi trong lệnh {interaction.command.name}: {error.original}")
        if interaction.response.is_done(): await interaction.followup.send(f"Đã xảy ra lỗi khi thực thi lệnh.", ephemeral=True)
        else: await interaction.response.send_message(f"Đã xảy ra lỗi khi thực thi lệnh.", ephemeral=True)
    else:
        print(f"Lỗi app command không xác định: {error}")
        if not interaction.response.is_done(): await interaction.response.send_message(f"Đã xảy ra lỗi: {error}", ephemeral=True)

# --- 9. CHẠY BOT (BÊN NGOÀI CLASS) ---
TOKEN = os.environ.get('DISCORD_TOKEN')
if TOKEN is None:
    print("LỖI: Không tìm thấy DISCORD_TOKEN. Hãy thiết lập nó trong Secrets.")
else:
    keep_alive() # Chạy web server
    client.run(TOKEN)
