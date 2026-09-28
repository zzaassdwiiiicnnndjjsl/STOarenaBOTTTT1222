import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import os
import random
import string
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# ==================== БАЗА ДАННЫХ ====================

DB_PATH = "tournaments.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            host_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            max_players INTEGER DEFAULT 16,
            status TEXT DEFAULT 'registration',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            user_id INTEGER,
            username TEXT,
            seed INTEGER,
            eliminated INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            round INTEGER,
            match_number INTEGER,
            player1_id INTEGER,
            player2_id INTEGER,
            winner_id INTEGER,
            room_code TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db():
    return sqlite3.connect(DB_PATH)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def gen_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_tournament_by_host(host_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, name, channel_id, message_id, max_players, status FROM tournaments WHERE host_id = ? AND status != 'finished' ORDER BY id DESC LIMIT 1", (host_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_tournament_by_id(tid):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, name, host_id, channel_id, message_id, max_players, status FROM tournaments WHERE id = ?", (tid,))
    row = c.fetchone()
    conn.close()
    return row

def get_players(tid):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, seed, eliminated FROM players WHERE tournament_id = ? ORDER BY seed", (tid,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_match(tid, match_number):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, round, match_number, player1_id, player2_id, winner_id, room_code, status FROM matches WHERE tournament_id = ? AND match_number = ?", (tid, match_number))
    row = c.fetchone()
    conn.close()
    return row

def create_bracket(tid, max_players):
    """Создаёт сетку на max_players (16)."""
    conn = db()
    c = conn.cursor()
    # Очистим старые матчи
    c.execute("DELETE FROM matches WHERE tournament_id = ?", (tid,))
    players = get_players(tid)
    # Заполняем пустыми слотами
    slots = [None] * max_players
    for i, p in enumerate(players[:max_players]):
        slots[i] = p[1]  # user_id

    # Раунд 1: 8 матчей для 16 игроков
    match_num = 1
    for i in range(0, max_players, 2):
        p1 = slots[i]
        p2 = slots[i+1] if i+1 < len(slots) else None
        c.execute("INSERT INTO matches (tournament_id, round, match_number, player1_id, player2_id) VALUES (?, 1, ?, ?, ?)",
                  (tid, match_num, p1, p2))
        match_num += 1
    # Раунд 2: 4 матча (победители раунда 1)
    for i in range(4):
        c.execute("INSERT INTO matches (tournament_id, round, match_number, player1_id, player2_id) VALUES (?, 2, ?, NULL, NULL)",
                  (tid, match_num))
        match_num += 1
    # Раунд 3: 2 матча (полуфинал)
    for i in range(2):
        c.execute("INSERT INTO matches (tournament_id, round, match_number, player1_id, player2_id) VALUES (?, 3, ?, NULL, NULL)",
                  (tid, match_num))
        match_num += 1
    # Раунд 4: 1 матч (финал)
    c.execute("INSERT INTO matches (tournament_id, round, match_number, player1_id, player2_id) VALUES (?, 4, ?, NULL, NULL)",
              (tid, match_num))
    conn.commit()
    conn.close()

def advance_winner(tid, match_id, winner_id):
    """Продвигает победителя в следующий раунд."""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT round, match_number FROM matches WHERE id = ?", (match_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    round_num, match_num = row
    c.execute("UPDATE matches SET winner_id = ?, status = 'finished' WHERE id = ?", (winner_id, match_id))
    # Определяем следующий матч
    if round_num < 4:
        # Индекс матча в следующем раунде
        next_match_num = 8 + (match_num - 1) // 2 + 1 if round_num == 1 else (4 + (match_num - 9) // 2 + 1 if round_num == 2 else 6 + (match_num - 5) // 2 + 1)
        # Упрощённый расчёт: для 16 игроков
        if round_num == 1:
            next_match = 8 + ((match_num - 1) // 2) + 1
        elif round_num == 2:
            next_match = 12 + ((match_num - 9) // 2) + 1
        elif round_num == 3:
            next_match = 14 + ((match_num - 13) // 2) + 1
        else:
            conn.close()
            return
        c.execute("SELECT id, player1_id, player2_id FROM matches WHERE tournament_id = ? AND match_number = ?", (tid, next_match))
        next_row = c.fetchone()
        if next_row:
            next_id, p1, p2 = next_row
            # Чётный матч — в слот player1, нечётный — в player2
            if match_num % 2 == 1:
                c.execute("UPDATE matches SET player1_id = ? WHERE id = ?", (winner_id, next_id))
            else:
                c.execute("UPDATE matches SET player2_id = ? WHERE id = ?", (winner_id, next_id))
    conn.commit()
    conn.close()

def build_bracket_text(tid):
    """Строит текстовое представление сетки."""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT match_number, round, player1_id, player2_id, winner_id, status FROM matches WHERE tournament_id = ? ORDER BY match_number", (tid,))
    matches = c.fetchall()
    conn.close()

    lines = ["**🏆 ТУРНИРНАЯ СЕТКА**\n"]
    current_round = None
    round_names = {1: "Раунд 1", 2: "Четвертьфинал", 3: "Полуфинал", 4: "Финал"}

    for m in matches:
        m_num, rnd, p1, p2, winner, status = m
        if rnd != current_round:
            current_round = rnd
            lines.append(f"\n**── {round_names.get(rnd, f'Раунд {rnd}')} ──**")

        p1_name = "—"
        p2_name = "—"
        if p1:
            conn = db()
            c = conn.cursor()
            c.execute("SELECT username FROM players WHERE user_id = ? AND tournament_id = ?", (p1, tid))
            r = c.fetchone()
            p1_name = r[0] if r else f"<@{p1}>"
            conn.close()
        if p2:
            conn = db()
            c = conn.cursor()
            c.execute("SELECT username FROM players WHERE user_id = ? AND tournament_id = ?", (p2, tid))
            r = c.fetchone()
            p2_name = r[0] if r else f"<@{p2}>"
            conn.close()

        status_icon = "🟢" if status == "in_progress" else "✅" if status == "finished" else "⏳"
        winner_mark = " 🏆" if winner else ""
        lines.append(f"`#{m_num:02d}` {status_icon} **{p1_name}** vs **{p2_name}**{winner_mark}")

    return "\n".join(lines)

# ==================== EMBED И VIEW ====================

class TournamentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, custom_id="btn_register")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = db()
        c = conn.cursor()
        c.execute("SELECT id, max_players FROM tournaments WHERE status = 'registration' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message("Регистрация закрыта.", ephemeral=True)
            return
        tid, max_p = row
        c.execute("SELECT COUNT(*) FROM players WHERE tournament_id = ?", (tid,))
        count = c.fetchone()[0]
        if count >= max_p:
            conn.close()
            await interaction.response.send_message("Турнир заполнен.", ephemeral=True)
            return
        c.execute("SELECT id FROM players WHERE tournament_id = ? AND user_id = ?", (tid, interaction.user.id))
        if c.fetchone():
            conn.close()
            await interaction.response.send_message("Вы уже зарегистрированы.", ephemeral=True)
            return
        c.execute("INSERT INTO players (tournament_id, user_id, username, seed) VALUES (?, ?, ?, ?)",
                  (tid, interaction.user.id, interaction.user.display_name, count + 1))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ Вы зарегистрированы! ({count + 1}/{max_p})", ephemeral=True)

    @discord.ui.button(label="Unregister", style=discord.ButtonStyle.danger, custom_id="btn_unregister")
    async def unregister_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = db()
        c = conn.cursor()
        c.execute("SELECT id FROM tournaments WHERE status = 'registration' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message("Регистрация закрыта.", ephemeral=True)
            return
        tid = row[0]
        c.execute("DELETE FROM players WHERE tournament_id = ? AND user_id = ?", (tid, interaction.user.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message("❌ Вы отменили регистрацию.", ephemeral=True)

    @discord.ui.button(label="Players", style=discord.ButtonStyle.secondary, custom_id="btn_players")
    async def players_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = db()
        c = conn.cursor()
        c.execute("SELECT id FROM tournaments WHERE status = 'registration' ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if not row:
            conn.close()
            await interaction.response.send_message("Нет активного турнира.", ephemeral=True)
            return
        tid = row[0]
        players = get_players(tid)
        conn.close()
        if not players:
            await interaction.response.send_message("Список игроков пуст.", ephemeral=True)
            return
        text = "\n".join([f"`{p[3]:02d}` <@{p[1]}> — {p[2]}" for p in players])
        await interaction.response.send_message(f"**Игроки:**\n{text}", ephemeral=True)

    @discord.ui.button(label="Locker", style=discord.ButtonStyle.secondary, custom_id="btn_locker")
    async def locker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ваш локер пуст.", ephemeral=True)

    @discord.ui.button(label="Host", style=discord.ButtonStyle.secondary, custom_id="btn_host")
    async def host_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Хост: STORM Arena", ephemeral=True)


class MatchView(discord.ui.View):
    def __init__(self, tid, match_number):
        super().__init__(timeout=None)
        self.tid = tid
        self.match_number = match_number

    @discord.ui.button(label="Победил игрок 1", style=discord.ButtonStyle.success)
    async def win1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 1)

    @discord.ui.button(label="Победил игрок 2", style=discord.ButtonStyle.success)
    async def win2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 2)

    async def handle_winner(self, interaction, slot):
        m = get_match(self.tid, self.match_number)
        if not m:
            await interaction.response.send_message("Матч не найден.", ephemeral=True)
            return
        mid, rnd, mnum, p1, p2, winner, room, status = m
        if winner:
            await interaction.response.send_message("Победитель уже отмечен.", ephemeral=True)
            return
        winner_id = p1 if slot == 1 else p2
        if not winner_id:
            await interaction.response.send_message("Игрок не определён.", ephemeral=True)
            return
        advance_winner(self.tid, mid, winner_id)
        # Обновляем сетку
        await update_bracket_message(self.tid)
        await interaction.response.send_message(f"🏆 Победитель матча #{mnum}: <@{winner_id}>", ephemeral=True)

# ==================== ОБНОВЛЕНИЕ СООБЩЕНИЙ ====================

async def update_bracket_message(tid):
    t = get_tournament_by_id(tid)
    if not t:
        return
    _, name, host_id, channel_id, message_id, max_p, status = t
    if not channel_id or not message_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    try:
        msg = await channel.fetch_message(message_id)
    except:
        return
    text = build_bracket_text(tid)
    embed = discord.Embed(title=f"🏆 {name} — Сетка", description=text, color=discord.Color.purple())
    try:
        await msg.edit(embed=embed)
    except:
        pass

# ==================== МОДАЛЬНОЕ ОКНО ====================

class SetupModal(discord.ui.Modal, title="Настройка турнира STORM Arena"):
    t_name = discord.ui.TextInput(label="Название турнира", placeholder="Например: VrynTour1v1", required=True)
    t_time = discord.ui.TextInput(label="Время начала", placeholder="Например: 17:15", required=True)
    t_prize = discord.ui.TextInput(label="Общий призовой фонд", placeholder="Например: 20,240 Emerald", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO tournaments (name, host_id, channel_id, max_players, status) VALUES (?, ?, ?, 16, 'registration')",
                  (self.t_name.value, interaction.user.id, interaction.channel_id))
        tid = c.lastrowid
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title=f"🏆 {self.t_name.value}",
            description="🏆 **CLASSIC**\n\n"
                        f"🕒 **Start** - {self.t_time.value}\n"
                        f"🌍 **Region** - EU\n"
                        f"⚙️ **Version** - \n"
                        "―――――――――――――――――――――――――――――\n"
                        "📜 **Tournament Details**\n"
                        "**Format** - `1v1`\n"
                        "**Map** - `Выберите карту ниже`\n"
                        "**Ability** - `Выберите способность ниже`\n"
                        "🔒 **Registrations open**\n"
                        "🏅 **Top 4 also wins** `4K` - `[W] Classic J!`\n"
                        "―――――――――――――――――――――――――――――\n"
                        f"🎁 **Prize Total - 💎 {self.t_prize.value}**\n"
                        "🥇 **1st** - 6,000 Emeralds\n"
                        "🥈 **2nd** - 3,600 Emeralds\n"
                        "🥉 **Top 4** - 1,800 Emeralds\n"
                        "🏅 **Top 8** - 960 Emeralds\n"
                        "🎖️ **Top 16** - 400 Emeralds\n"
                        "―――――――――――――――――――――――――――――\n"
                        "**Storm Arena** - Register using the buttons below!",
            color=discord.Color.purple()
        )
        embed.set_image(url="https://i.imgur.com/MRSAURq.png")
        embed.set_thumbnail(url="https://cdn.discordapp.com/icons/1542852842337865728/38e15931c9e781b35321711ddab95f24.png")

        view = TournamentView()
        msg = await interaction.response.send_message(embed=embed, view=view)
        # Сохраняем message_id
        conn = db()
        c = conn.cursor()
        c.execute("UPDATE tournaments SET message_id = ? WHERE id = ?", (msg.message_id, tid))
        conn.commit()
        conn.close()

# ==================== БОТ ====================

class StormBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        self.add_view(TournamentView())
        if GUILD_ID:
            self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await self.tree.sync()

bot = StormBot()

@bot.event
async def on_ready():
    print(f"Бот {bot.user} готов к работе!")

# ==================== КОМАНДЫ ====================

@bot.tree.command(name="create_tournament", description="Создать новый турнир")
async def create_tournament(interaction: discord.Interaction):
    await interaction.response.send_modal(SetupModal())

@bot.tree.command(name="qual", description="Добавить игрока в турнир (квалификация)")
@app_commands.describe(user="Игрок, которого нужно добавить")
async def qual(interaction: discord.Interaction, user: discord.Member):
    t = get_tournament_by_host(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира. Создайте его через `/create_tournament`.", ephemeral=True)
        return
    tid, name, channel_id, message_id, max_p, status = t
    if status != 'registration':
        await interaction.response.send_message("Регистрация уже закрыта.", ephemeral=True)
        return
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM players WHERE tournament_id = ?", (tid,))
    count = c.fetchone()[0]
    if count >= max_p:
        conn.close()
        await interaction.response.send_message("Турнир заполнен.", ephemeral=True)
        return
    c.execute("SELECT id FROM players WHERE tournament_id = ? AND user_id = ?", (tid, user.id))
    if c.fetchone():
        conn.close()
        await interaction.response.send_message(f"{user.mention} уже в турнире.", ephemeral=True)
        return
    c.execute("INSERT INTO players (tournament_id, user_id, username, seed) VALUES (?, ?, ?, ?)",
              (tid, user.id, user.display_name, count + 1))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ {user.mention} добавлен в турнир ({count + 1}/{max_p}).")

@bot.tree.command(name="start_tournament", description="Запустить турнир и создать сетку")
async def start_tournament(interaction: discord.Interaction):
    t = get_tournament_by_host(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    tid, name, channel_id, message_id, max_p, status = t
    players = get_players(tid)
    if len(players) < 2:
        await interaction.response.send_message("Недостаточно игроков (минимум 2).", ephemeral=True)
        return
    create_bracket(tid, max_p)
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE tournaments SET status = 'in_progress' WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    # Отправляем сетку в канал
    text = build_bracket_text(tid)
    embed = discord.Embed(title=f"🏆 {name} — Сетка", description=text, color=discord.Color.purple())
    msg = await interaction.channel.send(embed=embed)
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE tournaments SET message_id = ? WHERE id = ?", (msg.id, tid))
    conn.commit()
    conn.close()
    await interaction.response.send_message("✅ Турнир запущен!", ephemeral=True)

@bot.tree.command(name="match", description="Показать информацию о матче")
@app_commands.describe(number="Номер матча")
async def match(interaction: discord.Interaction, number: int):
    t = get_tournament_by_host(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    tid = t[0]
    m = get_match(tid, number)
    if not m:
        await interaction.response.send_message(f"Матч #{number} не найден.", ephemeral=True)
        return
    mid, rnd, mnum, p1, p2, winner, room, status = m
    p1_name = f"<@{p1}>" if p1 else "—"
    p2_name = f"<@{p2}>" if p2 else "—"
    embed = discord.Embed(
        title=f"⚔️ Матч #{mnum} (Раунд {rnd})",
        description=f"**{p1_name}** vs **{p2_name}**\n\n"
                    f"Статус: `{status}`\n"
                    f"Код комнаты: `{room or 'не задан'}`",
        color=discord.Color.orange()
    )
    view = MatchView(tid, number)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="room", description="Отправить игрокам код комнаты в DM")
@app_commands.describe(number="Номер матча", code="Код комнаты (оставьте пустым для автогенерации)")
async def room(interaction: discord.Interaction, number: int, code: str = None):
    t = get_tournament_by_host(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    tid = t[0]
    m = get_match(tid, number)
    if not m:
        await interaction.response.send_message(f"Матч #{number} не найден.", ephemeral=True)
        return
    mid, rnd, mnum, p1, p2, winner, old_room, status = m
    if not code:
        code = gen_room_code()
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE matches SET room_code = ?, status = 'in_progress' WHERE id = ?", (code, mid))
    conn.commit()
    conn.close()

    sent = []
    for uid in [p1, p2]:
        if uid:
            try:
                user = await bot.fetch_user(uid)
                await user.send(f"🎮 **Матч #{mnum}**\nКод комнаты: `{code}`\nУдачи!")
                sent.append(f"<@{uid}>")
            except:
                pass
    await update_bracket_message(tid)
    await interaction.response.send_message(f"✅ Код `{code}` отправлен: {', '.join(sent) if sent else 'никому (не удалось)'}")

@bot.tree.command(name="bracket", description="Показать текущую турнирную сетку")
async def bracket(interaction: discord.Interaction):
    t = get_tournament_by_host(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    tid, name = t[0], t[1]
    text = build_bracket_text(tid)
    embed = discord.Embed(title=f"🏆 {name} — Сетка", description=text, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

# ==================== ЗАПУСК ====================

bot.run(MTU1NDE1MTg5NzcyNjcxODA0Mg.GTK3dJ.zuqiGnBSSclI10IZwrBFQHf2ufX12FobuPhjRU)
