import discord
from discord.ext import tasks, commands
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
FMP_API_KEY = os.getenv('FMP_API_KEY')  # Ta clé FMP
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

    # Dates pour les 15 prochains jours (FMP accepte from/to au format YYYY-MM-DD)
    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=15)
    from_date = today.strftime('%Y-%m-%d')
    to_date = end_date.strftime('%Y-%m-%d')

    url = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={from_date}&to={to_date}&apikey={FMP_API_KEY}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        events = response.json()
    except Exception as e:
        print(f"Erreur lors de la requête API FMP : {e}")
        return

    if not events:
        print("Aucune donnée reçue de l'API.")
        return

    # Récupérer les événements existants
    try:
        existing_events = {event.name: event.scheduled_start_time for event in await guild.fetch_scheduled_events()}
    except Exception as e:
        print(f"Erreur récupération événements existants : {e}")
        return

    created_count = 0

    for event in events:
        # Filtre impact high/medium (FMP utilise 'impact': 'High', 'Medium', 'Low')
        if event.get('impact', '').lower() not in ['high', 'medium']:
            continue

        country = event.get('country', 'Unknown')
        event_name = event.get('event', 'Unknown Event')
        full_name = f"{country} - {event_name}"
        if len(full_name) > 100:
            full_name = full_name[:97] + "..."

        # Date/heure (format YYYY-MM-DD HH:MM:SS, déjà en UTC)
        try:
            event_time_str = f"{event['date']} {event.get('time', '00:00:00')}"
            event_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        # Vérifier doublon
        if full_name in existing_events and existing_events[full_name] == event_time:
            continue

        # Détails
        actual = event.get('actual', 'N/A')
        estimate = event.get('estimate', 'N/A')  # forecast
        previous = event.get('previous', 'N/A')

        impact_label = "Élevé" if event['impact'].lower() == 'high' else "Moyen"

        description = (
            f"Impact : {impact_label}\n"
            f"Prévision : {estimate}\n"
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
