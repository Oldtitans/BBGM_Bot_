import discord
import os
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
import random
import sqlite3
from datetime import datetime, timedelta
from typing import List

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
AUTHORIZED_ROLE_ID = 904582538297761802  # Paste your Role ID here

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matches 
                 (match_id TEXT PRIMARY KEY, team_a TEXT, team_b TEXT, ups INTEGER, timestamp DATETIME, 
                  closing_at DATETIME, channel_id INTEGER, message_id INTEGER, guild_id INTEGER)''')
    
    # Migration: Add missing columns if they don't exist
    for col, type in [("closing_at", "DATETIME"), ("channel_id", "INTEGER"), ("message_id", "INTEGER"), ("guild_id", "INTEGER")]:
        try:
            c.execute(f"ALTER TABLE matches ADD COLUMN {col} {type}")
        except sqlite3.OperationalError:
            pass # Column already exists
        
    c.execute('''CREATE TABLE IF NOT EXISTS votes 
                 (match_id TEXT, user_id INTEGER, team_choice TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS results 
                 (match_id TEXT, winner_name TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- PERSISTENT VOTING VIEW ---
class PersistentMatchView(discord.ui.View):
    def __init__(self, match_id: str, team_a: str, team_b: str):
        super().__init__(timeout=None) # Important for persistence
        self.match_id = match_id
        self.team_a = team_a
        self.team_b = team_b

        # We set custom_ids so the bot recognizes these buttons after a restart
        self.add_item(discord.ui.Button(label=f"Vote {team_a}", style=discord.ButtonStyle.primary, custom_id=f"vote_a_{match_id}"))
        self.add_item(discord.ui.Button(label=f"Vote {team_b}", style=discord.ButtonStyle.danger, custom_id=f"vote_b_{match_id}"))
        self.add_item(discord.ui.Button(label="Show Votes", style=discord.ButtonStyle.secondary, custom_id=f"show_votes_{match_id}"))

class PredictionBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # This tells the bot to watch for button clicks even if the view wasn't just created
        # We fetch active matches from DB to re-register their views
        conn = sqlite3.connect('pro_bot.db')
        c = conn.cursor()
        c.execute("SELECT m.match_id, m.team_a, m.team_b FROM matches m LEFT JOIN results r ON m.match_id = r.match_id WHERE r.match_id IS NULL")
        active_matches = c.fetchall()
        conn.close()

        for m_id, t_a, t_b in active_matches:
            self.add_view(PersistentMatchView(m_id, t_a, t_b))
        
        await self.tree.sync()

bot = PredictionBot()

# --- INTERACTION HANDLING ---
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    if not any(x in custom_id for x in ["vote_a_", "vote_b_", "show_votes_"]):
        return

    # Extract info from custom_id
    parts = custom_id.split("_")
    action = "_".join(parts[:-1]) # vote_a, vote_b, or show_votes
    match_id = parts[-1]

    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT team_a, team_b, closing_at FROM matches WHERE match_id = ?", (match_id,))
    match_data = c.fetchone()

    if not match_data:
        conn.close()
        return await interaction.response.send_message("Match data not found in database.", ephemeral=True)

    team_a, team_b, closing_at_str = match_data

    # --- TIME CHECK FOR VOTING ---
    if action != "show_votes" and closing_at_str:
        closing_at = datetime.fromisoformat(closing_at_str)
        if datetime.now() > closing_at:
            conn.close()
            return await interaction.response.send_message("⌛ **Voting is closed for this match!** The game has already started.", ephemeral=True)

    if action == "show_votes":
        c.execute("SELECT user_id, team_choice FROM votes WHERE match_id = ?", (match_id,))
        rows = c.fetchall()
        conn.close()
        
        team_a_list = [f"<@{r[0]}>" for r in rows if r[1] == team_a]
        team_b_list = [f"<@{r[0]}>" for r in rows if r[1] == team_b]
        
        embed = discord.Embed(title=f"Votes - Match #{match_id}", color=discord.Color.blue())
        embed.add_field(name=f"🔵 {team_a}", value="\n".join(team_a_list) if team_a_list else "None", inline=True)
        embed.add_field(name=f"🔴 {team_b}", value="\n".join(team_b_list) if team_b_list else "None", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    else:
        # Determine which team was clicked based on the button ID
        new_choice = team_a if "vote_a" in action else team_b
        
        # Check if the user already has a vote for this specific match
        c.execute("SELECT team_choice FROM votes WHERE match_id = ? AND user_id = ?", (match_id, interaction.user.id))
        current_vote = c.fetchone()

        if current_vote:
            if current_vote[0] == new_choice:
                # User clicked the SAME team -> Remove the vote (Toggle OFF)
                c.execute("DELETE FROM votes WHERE match_id = ? AND user_id = ?", (match_id, interaction.user.id))
                conn.commit()
                conn.close()
                return await interaction.response.send_message(f"🗑️ Your vote for **{new_choice}** has been removed.", ephemeral=True)
            else:
                # User clicked the OTHER team -> Move the vote (Switching)
                c.execute("UPDATE votes SET team_choice = ? WHERE match_id = ? AND user_id = ?", (new_choice, match_id, interaction.user.id))
                conn.commit()
                conn.close()
                return await interaction.response.send_message(f"🔄 Your vote has been moved to **{new_choice}**!", ephemeral=True)
        else:
            # User has no vote yet -> Create new vote
            c.execute("INSERT INTO votes (match_id, user_id, team_choice) VALUES (?, ?, ?)", (match_id, interaction.user.id, new_choice))
            conn.commit()
            conn.close()
            await interaction.response.send_message(f"✅ Your vote for **{new_choice}** has been saved!", ephemeral=True)

# --- ROLE CHECK ---
def is_authorized_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        role = interaction.guild.get_role(AUTHORIZED_ROLE_ID)
        return role in interaction.user.roles
    return app_commands.check(predicate)

# --- AUTOCOMPLETE ---
async def match_id_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT m.match_id, m.team_a, m.team_b FROM matches m LEFT JOIN results r ON m.match_id = r.match_id WHERE r.match_id IS NULL AND m.match_id LIKE ?", (f"%{current}%",))
    rows = c.fetchall()
    conn.close()
    return [app_commands.Choice(name=f"ID: {r[0]} ({r[1]} vs {r[2]})", value=r[0]) for r in rows]

async def winner_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    match_id = interaction.namespace.match_id
    if not match_id: return []
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT team_a, team_b FROM matches WHERE match_id = ?", (match_id,))
    row = c.fetchone()
    conn.close()
    return [app_commands.Choice(name=t, value=t) for t in row if current.lower() in t.lower()] if row else []

# --- COMMANDS ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}. Persistence active.')

@bot.tree.command(name="match")
@is_authorized_role()
async def match(interaction: discord.Interaction, team_a: str, team_b: str, minutes: int, ups: int = 2):
    match_id = str(random.randint(100, 999))
    now = datetime.now()
    closing_at = now + timedelta(minutes=minutes)
    
    view = PersistentMatchView(match_id, team_a, team_b)
    embed = discord.Embed(title="🏆 UPCOMING MATCH", color=discord.Color.blue())
    embed.add_field(name="Teams", value=f"🔵 **{team_a}** vs 🔴 **{team_b}**", inline=False)
    embed.add_field(name="Reward", value=f"💰 **{ups} Ups**", inline=True)
    embed.set_footer(text=f"Match ID: {match_id} | Voting ends at {closing_at.strftime('%H:%M')}")
    
    await interaction.response.send_message(embed=embed, view=view)
    
    # Get the message object to store its ID
    msg = await interaction.original_response()
    
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (match_id, team_a, team_b, ups, now.isoformat(), closing_at.isoformat(), interaction.channel_id, msg.id, interaction.guild_id))
    conn.commit()
    conn.close()

@bot.tree.command(name="edit_match")
@app_commands.autocomplete(match_id=match_id_autocomplete)
@is_authorized_role()
async def edit_match(interaction: discord.Interaction, match_id: str, team_a: str = None, team_b: str = None, ups: int = None, minutes: int = None):
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT team_a, team_b, ups, timestamp, channel_id, message_id FROM matches WHERE match_id = ?", (match_id,))
    match_data = c.fetchone()
    
    if not match_data:
        conn.close()
        return await interaction.response.send_message("❌ Match not found!", ephemeral=True)
    
    curr_team_a, curr_team_b, curr_ups, curr_timestamp, channel_id, message_id = match_data
    
    # Update values if provided
    new_team_a = team_a or curr_team_a
    new_team_b = team_b or curr_team_b
    new_ups = ups if ups is not None else curr_ups
    
    # Calculate new closing_at if minutes or teams changed
    # If minutes is provided, it's relative to the ORIGINAL timestamp (or should it be relative to NOW? User usually means "extends from start")
    # Actually, if the user edits it, they probably want to set a NEW closing time relative to NOW if they are extending it, 
    # OR relative to the start if they just want to fix a mistake. 
    # Let's make it relative to the ORIGINAL timestamp for consistency with /match logic.
    
    # Wait, the user might want to extend it. Let's stick to original timestamp + minutes.
    # If minutes is not provided, we keep the old closing_at.
    
    if minutes is not None:
        start_time = datetime.fromisoformat(curr_timestamp)
        new_closing_at = start_time + timedelta(minutes=minutes)
        c.execute("UPDATE matches SET team_a = ?, team_b = ?, ups = ?, closing_at = ? WHERE match_id = ?", 
                  (new_team_a, new_team_b, new_ups, new_closing_at.isoformat(), match_id))
    else:
        c.execute("UPDATE matches SET team_a = ?, team_b = ?, ups = ? WHERE match_id = ?", 
                  (new_team_a, new_team_b, new_ups, match_id))
    
    conn.commit()
    
    # Fetch final closing_at for the embed
    c.execute("SELECT closing_at FROM matches WHERE match_id = ?", (match_id,))
    final_closing_at_str = c.fetchone()[0]
    final_closing_at = datetime.fromisoformat(final_closing_at_str)
    conn.close()
    
    # Try to edit the original message
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
        
        view = PersistentMatchView(match_id, new_team_a, new_team_b)
        embed = discord.Embed(title="🏆 UPCOMING MATCH (EDITED)", color=discord.Color.blue())
        embed.add_field(name="Teams", value=f"🔵 **{new_team_a}** vs 🔴 **{new_team_b}**", inline=False)
        embed.add_field(name="Reward", value=f"💰 **{new_ups} Ups**", inline=True)
        embed.set_footer(text=f"Match ID: {match_id} | Voting ends at {final_closing_at.strftime('%H:%M')}")
        
        await message.edit(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Match #{match_id} updated and original message edited!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"✅ Match #{match_id} updated in DB, but could not edit message: {e}", ephemeral=True)

@bot.tree.command(name="cancel_match")
@app_commands.autocomplete(match_id=match_id_autocomplete)
@is_authorized_role()
async def cancel_match(interaction: discord.Interaction, match_id: str):
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT team_a, team_b, channel_id, message_id FROM matches WHERE match_id = ?", (match_id,))
    match_data = c.fetchone()
    
    if not match_data:
        conn.close()
        return await interaction.response.send_message("❌ Match not found!", ephemeral=True)
    
    team_a, team_b, channel_id, message_id = match_data
    
    # Delete match and votes
    c.execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM votes WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM results WHERE match_id = ?", (match_id,))
    conn.commit()
    conn.close()
    
    # Try to edit the original message to show it's cancelled
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
        
        embed = discord.Embed(title="❌ MATCH CANCELLED", color=discord.Color.red())
        embed.description = f"The match between **{team_a}** and **{team_b}** has been cancelled."
        embed.set_footer(text=f"Match ID: {match_id}")
        
        await message.edit(embed=embed, view=None) # Remove buttons
        await interaction.response.send_message(f"✅ Match #{match_id} has been cancelled and original message updated.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"✅ Match #{match_id} deleted from database, but could not update message: {e}", ephemeral=True)

@bot.tree.command(name="result")
@app_commands.autocomplete(match_id=match_id_autocomplete, winner=winner_autocomplete)
@is_authorized_role()
async def result(interaction: discord.Interaction, match_id: str, winner: str):
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    c.execute("SELECT team_a, team_b, ups FROM matches WHERE match_id = ?", (match_id,))
    match_data = c.fetchone()
    
    if not match_data or winner not in [match_data[0], match_data[1]]:
        conn.close()
        return await interaction.response.send_message("❌ Selection error!", ephemeral=True)

    c.execute("INSERT OR REPLACE INTO results VALUES (?, ?, ?)", (match_id, winner, datetime.now().isoformat()))
    c.execute("SELECT user_id FROM votes WHERE match_id = ? AND team_choice = ?", (match_id, winner))
    winners = [f"<@{row[0]}>" for row in c.fetchall()]
    conn.commit()
    conn.close()

    embed = discord.Embed(title="🏁 MATCH RESULT", color=discord.Color.green())
    embed.description = f"Winner: **{winner}**\nPoints: **{match_data[2]} Ups**"
    if winners: embed.add_field(name="Predictors", value=", ".join(winners))
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="summary")
async def summary(interaction: discord.Interaction):
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    # Get season start for THIS guild
    season_key = f"season_start_{interaction.guild_id}"
    c.execute("SELECT value FROM config WHERE key = ?", (season_key,))
    start_date = c.fetchone()
    start_date = start_date[0] if start_date else "1970-01-01"
    
    # Sum only for THIS guild
    query = """
        SELECT v.user_id, SUM(m.ups) 
        FROM votes v 
        JOIN results r ON v.match_id = r.match_id AND v.team_choice = r.winner_name 
        JOIN matches m ON v.match_id = m.match_id 
        WHERE r.timestamp >= ? AND m.guild_id = ?
        GROUP BY v.user_id 
        ORDER BY SUM(m.ups) DESC
    """
    c.execute(query, (start_date, interaction.guild_id))
    rows = c.fetchall()
    conn.close()
    
    if not rows: return await interaction.response.send_message("No data yet for this server.")
    lb = "\n".join([f"**#{i+1}** <@{r[0]}> — `{r[1]} Ups`" for i, r in enumerate(rows)])
    await interaction.response.send_message(embed=discord.Embed(title=f"📊 {interaction.guild.name} LEADERBOARD", description=lb, color=0x9b59b6))

@bot.tree.command(name="next_season")
@is_authorized_role()
async def next_season(interaction: discord.Interaction, confirm: bool):
    if not confirm: return await interaction.response.send_message("Cancelled.", ephemeral=True)
    conn = sqlite3.connect('pro_bot.db')
    c = conn.cursor()
    season_key = f"season_start_{interaction.guild_id}"
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (season_key, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"🚀 New season started for **{interaction.guild.name}**!")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Authorized Role required.", ephemeral=True)

bot.run(TOKEN)