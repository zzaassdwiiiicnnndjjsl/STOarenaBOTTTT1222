import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import string
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("MTU1NDE1MTg5NzcyNjcxODA0Mg.GTK3dJ.zuqiGnBSSclI10IZwrBFQHf2ufX12FobuPhjRU")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# ==================== ХРАНИЛИЩЕ В ПАМЯТИ ====================

# tournaments[host_id] = {
#   "name": str, "channel_id": int, "message_id": int,
#   "max_players": int, "status": str,
#   "players": [ {"user_id": int, "username": str, "seed": int} ],
#   "matches": [ {"round": int, "number": int, "p1": int|None, "p2": int|None,
#                 "winner": int|None, "room": str|None, "status": str} ]
# }
tournaments = {}

def gen_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_tournament(host_id):
    return tournaments.get(host_id)

def create_bracket(t):
    """Создаёт сетку на 16 игроков."""
    max_p = t["max_players"]
    players = t["players"]
    slots = [None] * max_p
    for i, p in enumerate(players[:max_p]):
        slots[i] = p["user_id"]

    matches = []
    match_num = 1

    # Раунд 1: 8 матчей
    for i in range(0, max_p, 2):
        matches.append({
            "round": 1, "number": match_num,
            "p1": slots[i], "p2": slots[i+1] if i+1 < max_p else None,
            "winner": None, "room": None, "status": "pending"
        })
        match_num += 1

    # Раунд 2: 4 матча
    for _ in range(4):
        matches.append({"round": 2, "number": match_num, "p1": None, "p2": None,
                        "winner": None, "room": None, "status": "pending"})
        match_num += 1

    # Раунд 3: 2 матча (полуфинал)
    for _ in range(2):
        matches.append({"round": 3, "number": match_num, "p1": None, "p2": None,
                        "winner": None, "room": None, "status": "pending"})
        match_num += 1

    # Раунд 4: 1 матч (финал)
    matches.append({"round": 4, "number": match_num, "p1": None, "p2": None,
                    "winner": None, "room": None, "status": "pending"})

    t["matches"] = matches

def advance_winner(t, match_number, winner_id):
    """Продвигает победителя в следующий раунд."""
    match = next((m for m in t["matches"] if m["number"] == match_number), None)
    if not match:
        return
    match["winner"] = winner_id
    match["status"] = "finished"

    rnd = match["round"]
    if rnd >= 4:
        return  # финал — дальше некуда

    # Определяем следующий матч
    if rnd == 1:
        next_num = 8 + ((match_number - 1) // 2) + 1
    elif rnd == 2:
        next_num = 12 + ((match_number - 9) // 2) + 1
    else:  # rnd == 3
        next_num = 14 + ((match_number - 13) // 2) + 1

    next_match = next((m for m in t["matches"] if m["number"] == next_num), None)
    if not next_match:
        return

    if match_number % 2 == 1:
        next_match["p1"] = winner_id
    else:
        next_match["p2"] = winner_id

def get_player_name(t, user_id):
    if not user_id:
        return "—"
    for p in t["players"]:
        if p["user_id"] == user_id:
            return p["username"]
    return f"<@{user_id}>"

def build_bracket_text(t):
    lines = ["**🏆 ТУРНИРНАЯ СЕТКА**\n"]
    current_round = None
    round_names = {1: "Раунд 1", 2: "Четвертьфинал", 3: "Полуфинал", 4: "Финал"}

    for m in t["matches"]:
        if m["round"] != current_round:
            current_round = m["round"]
            lines.append(f"\n**── {round_names.get(m['round'], f'Раунд {m['round']}')} ──**")

        p1 = get_player_name(t, m["p1"])
        p2 = get_player_name(t, m["p2"])
        icon = "🟢" if m["status"] == "in_progress" else "✅" if m["status"] == "finished" else "⏳"
        winner_mark = " 🏆" if m["winner"] else ""
        lines.append(f"`#{m['number']:02d}` {icon} **{p1}** vs **{p2}**{winner_mark}")

    return "\n".join(lines)

# ==================== VIEW ====================

class TournamentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, custom_id="btn_register")
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Ищем турнир, где идёт регистрация (по последнему созданному)
        t = None
        for host_id, tour in tournaments.items():
            if tour["status"] == "registration" and tour["message_id"] == interaction.message.id:
                t = tour
                break
        if not t:
            await interaction.response.send_message("Регистрация закрыта.", ephemeral=True)
            return
        if len(t["players"]) >= t["max_players"]:
            await interaction.response.send_message("Турнир заполнен.", ephemeral=True)
            return
        if any(p["user_id"] == interaction.user.id for p in t["players"]):
            await interaction.response.send_message("Вы уже зарегистрированы.", ephemeral=True)
            return
        t["players"].append({
            "user_id": interaction.user.id,
            "username": interaction.user.display_name,
            "seed": len(t["players"]) + 1
        })
        await interaction.response.send_message(
            f"✅ Вы зарегистрированы! ({len(t['players'])}/{t['max_players']})", ephemeral=True)

    @discord.ui.button(label="Unregister", style=discord.ButtonStyle.danger, custom_id="btn_unregister")
    async def unregister_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = None
        for tour in tournaments.values():
            if tour["status"] == "registration" and tour["message_id"] == interaction.message.id:
                t = tour
                break
        if not t:
            await interaction.response.send_message("Регистрация закрыта.", ephemeral=True)
            return
        t["players"] = [p for p in t["players"] if p["user_id"] != interaction.user.id]
        await interaction.response.send_message("❌ Вы отменили регистрацию.", ephemeral=True)

    @discord.ui.button(label="Players", style=discord.ButtonStyle.secondary, custom_id="btn_players")
    async def players_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = None
        for tour in tournaments.values():
            if tour["message_id"] == interaction.message.id:
                t = tour
                break
        if not t or not t["players"]:
            await interaction.response.send_message("Список игроков пуст.", ephemeral=True)
            return
        text = "\n".join([f"`{p['seed']:02d}` <@{p['user_id']}> — {p['username']}" for p in t["players"]])
        await interaction.response.send_message(f"**Игроки:**\n{text}", ephemeral=True)

    @discord.ui.button(label="Locker", style=discord.ButtonStyle.secondary, custom_id="btn_locker")
    async def locker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Ваш локер пуст.", ephemeral=True)

    @discord.ui.button(label="Host", style=discord.ButtonStyle.secondary, custom_id="btn_host")
    async def host_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Хост: STORM Arena", ephemeral=True)


class MatchView(discord.ui.View):
    def __init__(self, host_id, match_number):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.match_number = match_number

    @discord.ui.button(label="Победил игрок 1", style=discord.ButtonStyle.success)
    async def win1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 1)

    @discord.ui.button(label="Победил игрок 2", style=discord.ButtonStyle.success)
    async def win2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 2)

    async def handle_winner(self, interaction, slot):
        t = tournaments.get(self.host_id)
        if not t:
            await interaction.response.send_message("Турнир не найден.", ephemeral=True)
            return
        match = next((m for m in t["matches"] if m["number"] == self.match_number), None)
        if not match:
            await interaction.response.send_message("Матч не найден.", ephemeral=True)
            return
        if match["winner"]:
            await interaction.response.send_message("Победитель уже отмечен.", ephemeral=True)
            return
        winner_id = match["p1"] if slot == 1 else match["p2"]
        if not winner_id:
            await interaction.response.send_message("Игрок не определён.", ephemeral=True)
            return
        advance_winner(t, self.match_number, winner_id)
        await update_bracket_message(self.host_id)
        await interaction.response.send_message(
            f"🏆 Победитель матча #{self.match_number}: <@{winner_id}>", ephemeral=True)

# ==================== ОБНОВЛЕНИЕ СЕТКИ ====================

async def update_bracket_message(host_id):
    t = tournaments.get(host_id)
    if not t or not t.get("bracket_message_id"):
        return
    channel = bot.get_channel(t["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(t["bracket_message_id"])
    except:
        return
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"🏆 {t['name']} — Сетка", description=text, color=discord.Color.purple())
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
        host_id = interaction.user.id

        tournaments[host_id] = {
            "name": self.t_name.value,
            "channel_id": interaction.channel_id,
            "message_id": None,
            "bracket_message_id": None,
            "max_players": 16,
            "status": "registration",
            "players": [],
            "matches": []
        }

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
                        "**NoobCorp** - Register using the buttons below!",
            color=discord.Color.purple()
        )
        embed.set_image(url="https://i.imgur.com/MRSAURq.png")
        embed.set_thumbnail(url="https://cdn.discordapp.com/icons/1542852842337865728/38e15931c9e781b35321711ddab95f24.png")

        view = TournamentView()
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        tournaments[host_id]["message_id"] = msg.id

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

@bot.tree.command(name="qual", description="Добавить игрока в турнир")
@app_commands.describe(user="Игрок")
async def qual(interaction: discord.Interaction, user: discord.Member):
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    if t["status"] != "registration":
        await interaction.response.send_message("Регистрация закрыта.", ephemeral=True)
        return
    if len(t["players"]) >= t["max_players"]:
        await interaction.response.send_message("Турнир заполнен.", ephemeral=True)
        return
    if any(p["user_id"] == user.id for p in t["players"]):
        await interaction.response.send_message(f"{user.mention} уже в турнире.", ephemeral=True)
        return
    t["players"].append({"user_id": user.id, "username": user.display_name, "seed": len(t["players"]) + 1})
    await interaction.response.send_message(
        f"✅ {user.mention} добавлен ({len(t['players'])}/{t['max_players']}).")

@bot.tree.command(name="start_tournament", description="Запустить турнир и создать сетку")
async def start_tournament(interaction: discord.Interaction):
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    if len(t["players"]) < 2:
        await interaction.response.send_message("Недостаточно игроков.", ephemeral=True)
        return
    create_bracket(t)
    t["status"] = "in_progress"
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"🏆 {t['name']} — Сетка", description=text, color=discord.Color.purple())
    msg = await interaction.channel.send(embed=embed)
    t["bracket_message_id"] = msg.id
    await interaction.response.send_message("✅ Турнир запущен!", ephemeral=True)

@bot.tree.command(name="match", description="Показать матч")
@app_commands.describe(number="Номер матча")
async def match(interaction: discord.Interaction, number: int):
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    m = next((x for x in t["matches"] if x["number"] == number), None)
    if not m:
        await interaction.response.send_message(f"Матч #{number} не найден.", ephemeral=True)
        return
    p1 = get_player_name(t, m["p1"])
    p2 = get_player_name(t, m["p2"])
    embed = discord.Embed(
        title=f"⚔️ Матч #{m['number']} (Раунд {m['round']})",
        description=f"**{p1}** vs **{p2}**\n\n"
                    f"Статус: `{m['status']}`\n"
                    f"Код комнаты: `{m['room'] or 'не задан'}`",
        color=discord.Color.orange()
    )
    view = MatchView(interaction.user.id, number)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="room", description="Отправить игрокам код комнаты в DM")
@app_commands.describe(number="Номер матча", code="Код (оставьте пустым для автогенерации)")
async def room(interaction: discord.Interaction, number: int, code: str = None):
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    m = next((x for x in t["matches"] if x["number"] == number), None)
    if not m:
        await interaction.response.send_message(f"Матч #{number} не найден.", ephemeral=True)
        return
    if not code:
        code = gen_room_code()
    m["room"] = code
    m["status"] = "in_progress"

    sent = []
    for uid in [m["p1"], m["p2"]]:
        if uid:
            try:
                user = await bot.fetch_user(uid)
                await user.send(f"🎮 **Матч #{m['number']}**\nКод комнаты: `{code}`\nУдачи!")
                sent.append(f"<@{uid}>")
            except:
                pass
    await update_bracket_message(interaction.user.id)
    await interaction.response.send_message(
        f"✅ Код `{code}` отправлен: {', '.join(sent) if sent else 'никому'}")

@bot.tree.command(name="bracket", description="Показать текущую сетку")
async def bracket(interaction: discord.Interaction):
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("У вас нет активного турнира.", ephemeral=True)
        return
    if not t["matches"]:
        await interaction.response.send_message("Сетка ещё не создана. Запустите `/start_tournament`.", ephemeral=True)
        return
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"🏆 {t['name']} — Сетка", description=text, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

# ==================== ЗАПУСК ====================

bot.run(TOKEN)
