import discord
from discord import app_commands, ui
from discord.ext import tasks # Import Tác vụ nền
import sqlite3
import os
import requests
import json
from datetime import datetime, timedelta, date

# --- 1. CÀI ĐẶT CƠ SỞ DỮ LIỆU (Phiên bản 6.0) ---

def init_db():
    """Khởi tạo cơ sở dữ liệu và thêm các bảng/cột mới nếu cần."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Bảng users: Thêm last_daily, wins, losses, profit_loss
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
    
    # Bảng matches (Thêm UNIQUE cho api_match_id)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        team_a TEXT NOT NULL,
        team_b TEXT NOT NULL,
        api_match_id INTEGER UNIQUE,
        status TEXT NOT NULL DEFAULT 'open' 
    )
    ''')
    
    # Bảng bets (Giữ nguyên)
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

    # Bảng Watchlist (Giữ nguyên)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS watched_leagues (
        league_id INTEGER PRIMARY KEY,
        league_name TEXT NOT NULL
    )
    ''')
    
    # Bảng Settings (Giữ nguyên)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    
    # Bảng MỚI: Role Tiers
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS role_tiers (
        role_id INTEGER PRIMARY KEY,
        min_tokens INTEGER NOT NULL UNIQUE,
        guild_id INTEGER NOT NULL
    )
    ''')
    
    # Bảng MỚI: Challenges
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS challenges (
        challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id TEXT NOT NULL,
        challenger_id INTEGER NOT NULL,
        opponent_id INTEGER NOT NULL,
        challenger_bet_on TEXT NOT NULL,
        opponent_bet_on TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- pending, accepted, declined, resolved, cancelled
        message_id INTEGER,
        FOREIGN KEY(match_id) REFERENCES matches(match_id)
    )
    ''')

    # --- Nâng cấp Bảng Cũ ---
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

# --- 2. CÁC HÀM TRỢ GIÚP (Hoàn chỉnh) ---
def get_balance(user_id):
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone(); conn.close()
    return result[0] if result else None

def update_balance(user_id, amount, is_relative=True):
    """Cập nhật số dư. nếu is_relative=True, amount là số cộng thêm (hoặc trừ)."""
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    if is_relative:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    else:
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
    conn.commit(); conn.close()

def register_user(user_id, starting_balance=100):
    """Đăng ký người dùng mới. Trả về True nếu mới, False nếu đã tồn tại."""
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (user_id, balance, last_daily) VALUES (?, ?, ?)", (user_id, starting_balance, "1970-01-01T00:00:00"))
        conn.commit(); conn.close(); return True
    except sqlite3.IntegrityError: # Người dùng đã tồn tại
        conn.close(); return False

def get_setting(key, default=None):
    """Lấy một cài đặt từ DB."""
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else default

def set_setting(key, value):
    """Lưu một cài đặt vào DB."""
    conn = sqlite3.connect('database.db'); cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit(); conn.close()

def get_int_setting(key, default):
    """Lấy một cài đặt số nguyên."""
    value = get_setting(key, default)
    try: return int(value)
    except (ValueError, TypeError): return default

# --- 3. CÀI ĐẶT BOT DISCORD (Phiên bản 6.0) ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True # Cần Intent MEMBERS để cập nhật roles

class BettingBot(discord.Client):
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

    # --- (ĐÃ DI CHUYỂN VÀO TRONG CLASS) VÒNG LẶP TỰ ĐỘNG TÌM KÈO ---
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
                    if cursor.fetchone() is not None: continue # Kèo đã tồn tại
                    
                    team_a, team_b = fixture['teams']['home']['name'], fixture['teams']['away']['name']
                    internal_id = f"auto_{api_id}"
                    
                    # Dùng hàm riêng để tránh lỗi interaction
                    await internal_create_match_for_autofind(channel, internal_id, team_a, team_b, api_id)
                    new_matches_found += 1
            except Exception as e: print(f"Tác vụ tự động: Lỗi khi lấy giải {league_id}: {e}")
        
        print(f"Tác vụ tự động: Đã hoàn thành. Thêm được {new_matches_found} kèo mới.")
        conn.close()

    @auto_find_task.before_loop
    async def before_auto_find_task(self):
        # Đổi tần suất chạy dựa trên cài đặt
        frequency_hours = get_int_setting('autofind_frequency', 6)
        if self.auto_find_task.hours != frequency_hours:
            self.auto_find_task.change_interval(hours=frequency_hours)
            print(f"Tần suất tự động tìm kèo được cập nhật là: {frequency_hours} giờ.")
        await self.wait_until_ready()

    # --- (ĐÃ DI CHUYỂN VÀO TRONG CLASS) VÒNG LẶP TỰ ĐỘNG CẬP NHẬT ROLE ---
    @tasks.loop(minutes=30) # Chạy 30 phút 1 lần
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

# --- KHỞI TẠO BOT (Nằm bên ngoài class) ---
client = BettingBot(intents=intents)
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY')
# Các hằng số này sẽ được đọc từ DB
# DAILY_AMOUNT = 10 
# STARTING_BALANCE = 100

# --- 4. HÀM LOGIC LÕI (Nằm bên ngoài class) ---

async def internal_create_match(interaction: discord.Interaction, internal_id: str, team_a: str, team_b: str, api_id: int):
    """Hàm lõi tạo kèo (dùng cho lệnh manual và /find_match)."""
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
    """Hàm lõi tạo kèo, dùng cho tác vụ tự động."""
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
    """Hàm lõi xử lý trả thưởng (Hỗ trợ /stats và /challenge)."""
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

# --- 5. CÁC LỚP UI (Nằm bên ngoài class) ---
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
        super().__init__(timeout=None) # View vĩnh viễn
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

# --- 6. HÀM API HELPER (Nằm bên ngoài class) ---
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

# --- 7. CÁC LỆNH (COMMANDS) (Nằm bên ngoài class) ---

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
    team_a,
