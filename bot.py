import discord
from discord import app_commands
from discord.ext import commands
import os
import random
import string
import re
import datetime
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "1552734813209886750"))

TOUR_HOST_ROLE_IDS = [
    1547825149859078234,
    1554190894909882428
]

REGIONS = {
    "Europe": "EU",
    "North America": "US",
    "Central America": "CAM",
    "India West": "INW",
    "South America": "SA",
    "Asia": "ASIA"
}

ABILITIES = [
    "Punch", "Slap", "Slide", "Brief Case", "Invisibility", "Bumper Field",
    "Bounching Ball", "Hat Hop", "Shutdown", "Block Throw", "Block Wall",
    "Boost", "Chop", "Gust", "Hook Dash", "Rake", "Speed Gel", "Spin",
    "Sticky Bomb", "Switch", "Banana", "Bolt", "Hug", "Shield", "Snowball",
    "Spit", "Dice Roll", "Glider", "Power Jump", "Rewind", "Rock Slam"
]

tournaments = {}

def has_host_role(member):
    return any(r.id in TOUR_HOST_ROLE_IDS for r in member.roles)

def gen_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_tournament(host_id):
    return tournaments.get(host_id)

def parse_time_to_unix(time_str):
    try:
        m = re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip())
        if not m:
            return None
        hours, minutes = int(m.group(1)), int(m.group(2))
        now = datetime.datetime.now()
        target = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        target -= datetime.timedelta(hours=3)
        if target < now:
            target += datetime.timedelta(days=1)
        return int(target.timestamp())
    except Exception:
        return None

def format_time(time_str):
    ts = parse_time_to_unix(time_str)
    if ts:
        return f"<t:{ts}:R> (`{time_str}`)"
    return time_str

def create_bracket(t):
    max_p = t["max_players"]
    players = t["players"]
    slots = [None] * max_p
    for i, p in enumerate(players[:max_p]):
        slots[i] = p["user_id"]

    matches = []
    match_num = 1
    for i in range(0, max_p, 2):
        matches.append({"round": 1, "number": match_num,
                        "p1": slots[i], "p2": slots[i+1] if i+1 < max_p else None,
                        "winner": None, "room": None, "status": "pending"})
        match_num += 1
    for _ in range(4):
        matches.append({"round": 2, "number": match_num, "p1": None, "p2": None,
                        "winner": None, "room": None, "status": "pending"})
        match_num += 1
    for _ in range(2):
        matches.append({"round": 3, "number": match_num, "p1": None, "p2": None,
                        "winner": None, "room": None, "status": "pending"})
        match_num += 1
    matches.append({"round": 4, "number": match_num, "p1": None, "p2": None,
                    "winner": None, "room": None, "status": "pending"})
    t["matches"] = matches

def advance_winner(t, match_number, winner_id):
    match = next((m for m in t["matches"] if m["number"] == match_number), None)
    if not match:
        return
    match["winner"] = winner_id
    match["status"] = "finished"
    rnd = match["round"]
    if rnd >= 4:
        return
    if rnd == 1:
        next_num = 8 + ((match_number - 1) // 2) + 1
    elif rnd == 2:
        next_num = 12 + ((match_number - 9) // 2) + 1
    else:
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
    lines = ["**TOURNAMENT BRACKET**\n"]
    current_round = None
    round_names = {1: "Round 1", 2: "Quarterfinal", 3: "Semifinal", 4: "Final"}
    for m in t["matches"]:
        if m["round"] != current_round:
            current_round = m["round"]
            lines.append(f"\n**── {round_names.get(m['round'], f'Round {m['round']}')} ──**")
        p1 = get_player_name(t, m["p1"])
        p2 = get_player_name(t, m["p2"])
        icon = "[IN PROGRESS]" if m["status"] == "in_progress" else "[DONE]" if m["status"] == "finished" else "[WAIT]"
        winner_mark = " [WIN]" if m["winner"] else ""
        lines.append(f"`#{m['number']:02d}` {icon} **{p1}** vs **{p2}**{winner_mark}")

    if t.get("winner"):
        lines.append(f"\n**Tournament Winner: <@{t['winner']}>**")

    return "\n".join(lines)

def build_tournament_embed(t):
    region_code = t.get("region", "EU")
    region_display = next((f"{n} ({c})" for n, c in REGIONS.items() if c == region_code), region_code)

    description = "**CLASSIC**\n\n"
    description += f"**Start** - {t.get('time_display', '—')}\n"
    description += f"**Region** - `{region_display}`\n"
    description += "**Version** - \n"
    description += "―――――――――――――――――――――――――――――\n"
    description += "**Tournament Details**\n"
    description += "**Format** - `1v1`\n"
    description += f"**Map** - `{t.get('map') or '—'}`\n"
    description += f"**Ability** - `{t.get('ability') or '—'}`\n"
    description += "**Registrations open**\n"
    description += "―――――――――――――――――――――――――――――\n"

    if t.get("winner"):
        description += "―――――――――――――――――――――――――――――\n"
        description += f"**Winner: <@{t['winner']}>**\n"

    description += "―――――――――――――――――――――――――――――\n"
    description += "**Storm Arena** - Register using the buttons below!"

    embed = discord.Embed(
        title=f"{t['name']}",
        description=description,
        color=discord.Color.purple()
    )
    embed.set_image(url="https://i.imgur.com/MRSAURq.png")
    embed.set_thumbnail(url="https://cdn.discordapp.com/icons/1542852842337865728/38e15931c9e781b35321711ddab95f24.png")
    return embed

async def update_tournament_message(host_id):
    t = tournaments.get(host_id)
    if not t or not t.get("message_id"):
        return
    channel = bot.get_channel(t["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(t["message_id"])
    except Exception:
        return
    try:
        view = TournamentView(host_id) if t["status"] == "registration" else None
        await msg.edit(embed=build_tournament_embed(t), view=view)
    except Exception as e:
        print(f"update_tournament_message error: {e}")

async def update_bracket_message(host_id):
    t = tournaments.get(host_id)
    if not t or not t.get("bracket_message_id"):
        return
    channel = bot.get_channel(t["channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(t["bracket_message_id"])
    except Exception:
        return
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"{t['name']} — Bracket", description=text, color=discord.Color.purple())
    try:
        await msg.edit(embed=embed)
    except Exception:
        pass

class TournamentView(discord.ui.View):
    def __init__(self, host_id):
        super().__init__(timeout=None)
        self.host_id = host_id
        t = tournaments.get(host_id)
        count = len(t["players"]) if t else 0
        max_p = t["max_players"] if t else 16
        self.register_button.label = f"{count}/{max_p} register"

    def _find_tournament(self, interaction):
        for tid, tour in tournaments.items():
            if tour.get("message_id") == interaction.message.id:
                return tid, tour
        return None, None

    @discord.ui.button(label="0/16 register", style=discord.ButtonStyle.success, row=0)
    async def register_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, t = self._find_tournament(interaction)
        if not t or t["status"] != "registration":
            await interaction.response.send_message("Registration is closed.", ephemeral=True)
            return
        if len(t["players"]) >= t["max_players"]:
            await interaction.response.send_message("Tournament is full.", ephemeral=True)
            return
        if any(p["user_id"] == interaction.user.id for p in t["players"]):
            await interaction.response.send_message("You are already registered.", ephemeral=True)
            return
        t["players"].append({
            "user_id": interaction.user.id,
            "username": interaction.user.display_name,
            "seed": len(t["players"]) + 1
        })
        await update_tournament_message(self.host_id)
        await interaction.response.send_message(
            f"You are registered! ({len(t['players'])}/{t['max_players']})", ephemeral=True)

    @discord.ui.button(label="Unregister", style=discord.ButtonStyle.danger, row=0)
    async def unregister_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, t = self._find_tournament(interaction)
        if not t or t["status"] != "registration":
            await interaction.response.send_message("Registration is closed.", ephemeral=True)
            return
        t["players"] = [p for p in t["players"] if p["user_id"] != interaction.user.id]
        await update_tournament_message(self.host_id)
        await interaction.response.send_message("You have unregistered.", ephemeral=True)

    @discord.ui.button(label="Players", style=discord.ButtonStyle.secondary, row=1)
    async def players_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, t = self._find_tournament(interaction)
        if not t or not t["players"]:
            await interaction.response.send_message("Player list is empty.", ephemeral=True)
            return
        text = "\n".join([f"`{p['seed']:02d}` <@{p['user_id']}> — {p['username']}" for p in t["players"]])
        await interaction.response.send_message(f"**Players:**\n{text}", ephemeral=True)

    @discord.ui.button(label="Locker", style=discord.ButtonStyle.secondary, row=1)
    async def locker_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your locker is empty.", ephemeral=True)

    @discord.ui.button(label="Host", style=discord.ButtonStyle.secondary, row=1)
    async def host_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Host: STORM Arena", ephemeral=True)

class MatchView(discord.ui.View):
    def __init__(self, host_id, match_number):
        super().__init__(timeout=None)
        self.host_id = host_id
        self.match_number = match_number

    @discord.ui.button(label="Player 1 won", style=discord.ButtonStyle.success)
    async def win1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 1)

    @discord.ui.button(label="Player 2 won", style=discord.ButtonStyle.success)
    async def win2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_winner(interaction, 2)

    async def handle_winner(self, interaction, slot):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("Only the host can set the winner.", ephemeral=True)
            return
        t = tournaments.get(self.host_id)
        if not t:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        match = next((m for m in t["matches"] if m["number"] == self.match_number), None)
        if not match:
            await interaction.response.send_message("Match not found.", ephemeral=True)
            return
        if match["winner"]:
            await interaction.response.send_message("Winner already set.", ephemeral=True)
            return
        winner_id = match["p1"] if slot == 1 else match["p2"]
        if not winner_id:
            await interaction.response.send_message("Player not defined.", ephemeral=True)
            return
        advance_winner(t, self.match_number, winner_id)
        await update_bracket_message(self.host_id)
        await interaction.response.send_message(
            f"Winner of match #{self.match_number}: <@{winner_id}>", ephemeral=True)

class SetupModal(discord.ui.Modal, title="STORM Arena Tournament Setup"):
    t_name = discord.ui.TextInput(
        label="Tournament name",
        placeholder="e.g. VrynTour1v1",
        required=True,
        max_length=100
    )
    t_time = discord.ui.TextInput(
        label="Start time (HH:MM)",
        placeholder="e.g. 17:15",
        required=True,
        max_length=5
    )
    t_region = discord.ui.TextInput(
        label="Region (EU/US/CAM/INW/SA/ASIA)",
        placeholder="e.g. EU",
        required=True,
        max_length=10
    )
    t_map = discord.ui.TextInput(
        label="Map",
        placeholder="e.g. Jungle Roll",
        required=True,
        max_length=100
    )
    t_ability = discord.ui.TextInput(
        label="Ability",
        placeholder="e.g. Punch",
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        host_id = interaction.user.id

        region_input = self.t_region.value.strip().upper()
        region_code = region_input if region_input in REGIONS.values() else "EU"

        tournaments[host_id] = {
            "name": self.t_name.value,
            "time_display": format_time(self.t_time.value),
            "channel_id": interaction.channel_id,
            "message_id": None,
            "bracket_message_id": None,
            "max_players": 16,
            "status": "registration",
            "players": [],
            "matches": [],
            "map": self.t_map.value,
            "ability": self.t_ability.value,
            "region": region_code,
            "winner": None
        }
        embed = build_tournament_embed(tournaments[host_id])
        view = TournamentView(host_id)
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        tournaments[host_id]["message_id"] = msg.id

class StormBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        if GUILD_ID:
            self.tree.copy_global_to(guild=discord.Object(id=GUILD_ID))
            await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        else:
            await self.tree.sync()

bot = StormBot()

@bot.event
async def on_ready():
    print(f"Bot {bot.user} is ready!")

@bot.tree.command(name="create_tournament", description="Create a new tournament (host role required)")
async def create_tournament(interaction: discord.Interaction):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to create tournaments.", ephemeral=True)
        return
    await interaction.response.send_modal(SetupModal())

@bot.tree.command(name="qual", description="Add a player to the tournament (host only)")
@app_commands.describe(user="Player")
async def qual(interaction: discord.Interaction, user: discord.Member):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] != "registration":
        await interaction.response.send_message("Registration is closed.", ephemeral=True)
        return
    if len(t["players"]) >= t["max_players"]:
        await interaction.response.send_message("Tournament is full.", ephemeral=True)
        return
    if any(p["user_id"] == user.id for p in t["players"]):
        await interaction.response.send_message(f"{user.mention} is already in the tournament.", ephemeral=True)
        return
    t["players"].append({"user_id": user.id, "username": user.display_name, "seed": len(t["players"]) + 1})
    await update_tournament_message(interaction.user.id)
    await interaction.response.send_message(
        f"{user.mention} added ({len(t['players'])}/{t['max_players']}).")

@bot.tree.command(name="start_tournament", description="Start the tournament (host only)")
async def start_tournament(interaction: discord.Interaction):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] == "finished":
        await interaction.response.send_message("Tournament is already finished.", ephemeral=True)
        return
    if len(t["players"]) < 2:
        await interaction.response.send_message("Not enough players.", ephemeral=True)
        return
    create_bracket(t)
    t["status"] = "in_progress"
    await update_tournament_message(interaction.user.id)
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"{t['name']} — Bracket", description=text, color=discord.Color.purple())
    msg = await interaction.channel.send(embed=embed)
    t["bracket_message_id"] = msg.id
    await interaction.response.send_message("Tournament started!", ephemeral=True)

@bot.tree.command(name="end_tour", description="End the tournament (host only)")
async def end_tour(interaction: discord.Interaction):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] == "finished":
        await interaction.response.send_message("Tournament is already finished.", ephemeral=True)
        return
    t["status"] = "finished"
    await update_tournament_message(interaction.user.id)
    await update_bracket_message(interaction.user.id)

    winner_text = f"<@{t['winner']}>" if t.get("winner") else "—"

    embed = discord.Embed(
        title=f"{t['name']} — Tournament Finished",
        description=f"Winner: {winner_text}",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="winner", description="Set the tournament winner (host only)")
@app_commands.describe(user="Winner of the tournament")
async def winner(interaction: discord.Interaction, user: discord.Member):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] == "finished":
        await interaction.response.send_message("Tournament is already finished.", ephemeral=True)
        return
    t["winner"] = user.id
    await update_tournament_message(interaction.user.id)
    await update_bracket_message(interaction.user.id)
    await interaction.response.send_message(f"Winner set: {user.mention}")

@bot.tree.command(name="match", description="Show match info (host only)")
@app_commands.describe(number="Match number")
async def match(interaction: discord.Interaction, number: int):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] == "finished":
        await interaction.response.send_message("Tournament is already finished.", ephemeral=True)
        return
    m = next((x for x in t["matches"] if x["number"] == number), None)
    if not m:
        await interaction.response.send_message(f"Match #{number} not found.", ephemeral=True)
        return
    p1 = get_player_name(t, m["p1"])
    p2 = get_player_name(t, m["p2"])
    embed = discord.Embed(
        title=f"Match #{m['number']} (Round {m['round']})",
        description=f"**{p1}** vs **{p2}**\n\n"
                    f"Status: `{m['status']}`\n"
                    f"Room code: `{m['room'] or 'not set'}`",
        color=discord.Color.orange()
    )
    view = MatchView(interaction.user.id, number)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="room", description="Send or set a room code for a match (host only)")
@app_commands.describe(number="Match number", code="Room code (letters and digits). Leave empty for auto-generation.")
async def room(interaction: discord.Interaction, number: int, code: str = None):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if t["status"] == "finished":
        await interaction.response.send_message("Tournament is already finished.", ephemeral=True)
        return
    if t["status"] != "in_progress":
        await interaction.response.send_message("Tournament has not started yet.", ephemeral=True)
        return
    m = next((x for x in t["matches"] if x["number"] == number), None)
    if not m:
        await interaction.response.send_message(f"Match #{number} not found.", ephemeral=True)
        return

    if code:
        code = re.sub(r"[^A-Za-z0-9]", "", code)
        if not code:
            await interaction.response.send_message("Room code must contain letters or digits.", ephemeral=True)
            return
    else:
        code = gen_room_code()

    m["room"] = code
    m["status"] = "in_progress"

    sent = []
    for uid in [m["p1"], m["p2"]]:
        if uid:
            try:
                user = await bot.fetch_user(uid)
                await user.send(f"Match #{m['number']}\nRoom code: `{code}`\nGood luck!")
                sent.append(f"<@{uid}>")
            except Exception:
                pass
    await update_bracket_message(interaction.user.id)
    await interaction.response.send_message(
        f"Room code `{code}` sent to: {', '.join(sent) if sent else 'nobody'}", ephemeral=True)

@bot.tree.command(name="bracket", description="Show current bracket (host only)")
async def bracket(interaction: discord.Interaction):
    if not has_host_role(interaction.user):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    t = get_tournament(interaction.user.id)
    if not t:
        await interaction.response.send_message("You have no active tournament.", ephemeral=True)
        return
    if not t["matches"]:
        await interaction.response.send_message("Bracket not created yet. Run `/start_tournament`.", ephemeral=True)
        return
    text = build_bracket_text(t)
    embed = discord.Embed(title=f"{t['name']} — Bracket", description=text, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
