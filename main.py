import discord
from discord.ext import tasks, commands
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID'))

intents = discord.Intents.default()
intents.guild_scheduled_events = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot connecté : {bot.user}')
    update_economic_events.start()

@tasks.loop(hours=24)
async def update_economic_events():
    await bot.wait_until_ready()

    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"ERREUR : Guild non trouvé avec l'ID {GUILD_ID}")
        print("Serveurs disponibles :")
        for g in bot.guilds:
            print(f" - {g.name} (ID: {g.id})")
        return

    print(f"Connexion réussie au serveur : {guild.name}")
    print("Mise à jour du calendrier économique en cours...")

    # RSS Forex Factory (high + medium impact, global, mis à jour en temps réel)
    rss_url = "https://www.forexfactory.com/ff_calendar_thisweek.xml"

    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:
        print(f"Erreur parsing RSS Forex Factory : {e}")
        return

    if not feed.entries:
        print("Aucune donnée dans le RSS.")
        return

    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=15)

    existing_events = {event.name: event.scheduled_start_time for event in await guild.fetch_scheduled_events()}

    created_count = 0

    for entry in feed.entries:
        # Impact (high = red, medium = orange, low = yellow, holiday = gray)
        impact = entry.get('impact', '').lower()
        if impact not in ['high', 'medium', 'orange', 'red']:
            continue

        # Date/heure (dans <time> tag, format YYYY-MM-DDTHH:MM:SS+00:00)
        event_time_str = entry.get('time')
        if not event_time_str:
            continue

        try:
            # Forex Factory utilise souvent date + time séparés, mais RSS combine
            event_time = datetime.strptime(event_time_str, '%Y-%m-%dT%H:%M:%S%z')
            event_time = event_time.astimezone(timezone.utc)  # Normalise UTC
        except ValueError:
            continue

        if not (today <= event_time.date() <= end_date):
            continue

        country = entry.get('country', 'Unknown')
        title = entry.get('title', 'Unknown Event')
        full_name = f"{country} - {title}"
        if len(full_name) > 100:
            full_name = full_name[:97] + "..."

        if full_name in existing_events and existing_events[full_name] == event_time:
            continue

        # Détails
        actual = entry.get('actual', 'N/A')
        forecast = entry.get('forecast', 'N/A')
        previous = entry.get('previous', 'N/A')

        impact_label = "Élevé" if impact in ['high', 'red'] else "Moyen"

        description = (
            f"Impact : {impact_label}\n"
            f"Prévision : {forecast}\n"
            f"Actuel : {actual}\n"
            f"Précédent : {previous}"
        )

        try:
            await guild.create_scheduled_event(
                name=full_name,
                start_time=event_time,
                entity_type=discord.ScheduledEventEntityType.external,
                metadata=discord.ScheduledEventMetadata(location='Marché Mondial'),
                description=description[:1000],
                privacy_level=discord.ScheduledEventPrivacyLevel.guild_only
            )
            print(f"Événement créé : {full_name} le {event_time}")
            created_count += 1
        except Exception as e:
            print(f"Erreur création : {e}")

    print(f"Mise à jour terminée. {created_count} nouveaux événements ajoutés.")

@bot.command(name='updatecal')
@commands.has_permissions(administrator=True)
async def manual_update(ctx):
    await ctx.send("Mise à jour forcée en cours...")
    await update_economic_events()
    await ctx.send("Mise à jour terminée !")

bot.run(DISCORD_TOKEN)
