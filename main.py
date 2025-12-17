import discord
from discord.ext import tasks, commands
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID'))  # ID du serveur Discord

intents = discord.Intents.default()
intents.guild_scheduled_events = True  # Nécessaire pour créer/lire les événements

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot connecté : {bot.user}')
    update_economic_events.start()  # Lance la mise à jour quotidienne

@tasks.loop(hours=24)
async def update_economic_events():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Guild non trouvé. Vérifie l'ID du serveur.")
        return

    print("Mise à jour du calendrier économique en cours...")

    # Headers pour éviter le blocage
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
    }
    url = "https://www.investing.com/economic-calendar/"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Erreur lors du fetch de Investing.com : {e}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    events_table = soup.find('table', id='economicCalendarTable')
    
    if not events_table:
        print("Tableau du calendrier non trouvé sur la page.")
        return

    rows = events_table.find('tbody').find_all('tr', class_='js-event-item')

    # Récupérer les événements existants pour éviter les doublons
    try:
        existing_events = {event.name: event.scheduled_start_time for event in await guild.fetch_scheduled_events()}
    except Exception as e:
        print(f"Erreur lors de la récupération des événements existants : {e}")
        return

    today = datetime.now(timezone.utc).date()
    limit_date = today + timedelta(days=15)

    created_count = 0

    for row in rows:
        # Filtre impact : 3 = high, 2 = medium
        impact = row.get('data-event-volatility', '')
        if impact not in ['3', '2']:
            continue

        # Date et heure (format caché dans data-event-datetime)
        date_str = row.get('data-event-datetime')
        if not date_str:
            continue

        try:
            event_time = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        # Filtre : seulement les 15 prochains jours
        if not (today <= event_time.date() <= limit_date):
            continue

        # Pays/devise
        flag_td = row.find('td', class_='flagCur')
        country = flag_td.text.strip() if flag_td else "Unknown"

        # Nom de l'événement
        event_td = row.find('td', class_='event')
        if not event_td:
            continue
        event_link = event_td.find('a')
        event_name = event_link.text.strip() if event_link else "Unknown Event"

        full_name = f"{country} - {event_name}"
        if len(full_name) > 100:  # Limite Discord
            full_name = full_name[:97] + "..."

        # Vérifier doublon
        if full_name in existing_events and existing_events[full_name] == event_time:
            continue

        # Détails : prévision, actuel, précédent
        forecast = row.find('td', class_='fore').text.strip() if row.find('td', class_='fore') else 'N/A'
        actual = row.find('td', class_='act').text.strip() if row.find('td', class_='act') else 'N/A'
        previous = row.find('td', class_='prev').text.strip() if row.find('td', class_='prev') else 'N/A'

        impact_label = "Élevé" if impact == '3' else "Moyen"

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
                description=description[:1000],  # Limite description
                privacy_level=discord.ScheduledEventPrivacyLevel.guild_only
            )
            print(f"Événement créé : {full_name} le {event_time}")
            created_count += 1
        except Exception as e:
            print(f"Erreur création événement {full_name} : {e}")

    print(f"Mise à jour terminée. {created_count} nouveaux événements ajoutés.")

# Optionnel : commande manuelle pour forcer la mise à jour
@bot.command(name='updatecal')
@commands.has_permissions(administrator=True)
async def manual_update(ctx):
    await ctx.send("Mise à jour du calendrier en cours...")
    await update_economic_events()
    await ctx.send("Mise à jour terminée !")

bot.run(DISCORD_TOKEN)
