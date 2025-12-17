import discord
from discord.ext import tasks, commands
import finnhub
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
GUILD_ID = int(os.getenv('GUILD_ID'))  # ID du serveur Discord cible

intents = discord.Intents.default()
intents.guild_scheduled_events = True  # Nécessaire pour les événements

bot = commands.Bot(command_prefix='!', intents=intents)
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

@bot.event
async def on_ready():
    print(f'Bot connecté : {bot.user}')
    update_economic_events.start()  # Lance la tâche auto

@tasks.loop(hours=24)
async def update_economic_events():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Guild non trouvé.")
        return

    # Dates : aujourd'hui à +15 jours
    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=15)
    calendar = finnhub_client.calendar_economic(str(today), str(end_date))

    existing_events = {e.name: e.scheduled_start_time for e in await guild.fetch_scheduled_events()}

    for event in calendar.get('economicCalendar', []):
        if event['impact'] not in ['high', 'medium']:  # Filtre par importance
            continue

        # Parse la date/heure (Finnhub : "YYYY-MM-DD HH:MM:SS")
        try:
            event_time = datetime.fromisoformat(event['time']).replace(tzinfo=timezone.utc)
        except ValueError:
            continue  # Skip si format invalide

        event_name = f"{event['country']} - {event['event']}"
        if event_name in existing_events and existing_events[event_name] == event_time:
            continue  # Événement existe déjà

        # Description avec détails
        description = (
            f"Devise : {event['unit']}\n"
            f"Impact : {event['impact']}\n"
            f"Estimation : {event.get('estimate', 'N/A')}\n"
            f"Actuel : {event.get('actual', 'N/A')}\n"
            f"Précédent : {event.get('prev', 'N/A')}"
        )

        # Créer l'événement (type EXTERNAL pour événements globaux)
        await guild.create_scheduled_event(
            name=event_name,
            start_time=event_time,
            entity_type=discord.ScheduledEventEntityType.external,
            metadata=discord.ScheduledEventMetadata(location='Global Market'),
            description=description,
            privacy_level=discord.ScheduledEventPrivacyLevel.guild_only
        )
        print(f"Événement créé : {event_name} à {event_time}")

bot.run(DISCORD_TOKEN)
