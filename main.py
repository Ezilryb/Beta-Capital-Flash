import discord
from discord.ext import tasks, commands
import requests
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

    # Calcul des dates pour les 15 prochains jours
    today = datetime.now(timezone.utc).date()
    end_date = today + timedelta(days=15)
    date_from = today.strftime('%m/%d/%Y')
    date_to = end_date.strftime('%m/%d/%Y')

    url = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': 'https://www.investing.com/economic-calendar/',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'timeZone': '8',  # GMT/UTC
        'timeFilter': 'timeRemain',
        'currentTab': 'today',
        'limit_from': '0'
    }

    try:
        response = requests.post(url, headers=headers, data=data, timeout=15)
        response.raise_for_status()
        json_data = response.json()
    except Exception as e:
        print(f"Erreur lors de la requête API Investing.com : {e}")
        return

    if 'data' not in json_data:
        print("Aucune donnée reçue de l'API.")
        return

    html_content = json_data['data']  # Contient le HTML des lignes
    from bs4 import BeautifulSoup  # On garde BS4 juste pour parser ce petit HTML
    soup = BeautifulSoup(html_content, 'html.parser')
    rows = soup.find_all('tr', class_='js-event-item')

    existing_events = {event.name: event.scheduled_start_time for event in await guild.fetch_scheduled_events()}

    created_count = 0

    for row in rows:
        impact = row.get('data-event-volatility', '')
        if impact not in ['3', '2']:  # 3=high, 2=medium
            continue

        date_str = row.get('data-event-datetime')
        if not date_str:
            continue

        try:
            event_time = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if not (today <= event_time.date() <= end_date):
            continue

        country_td = row.find('td', class_='flagCur')
        country = country_td.text.strip() if country_td else "Unknown"

        event_td = row.find('td', class_='event')
        if not event_td:
            continue
        event_link = event_td.find('a')
        event_name = event_link.text.strip() if event_link else "Unknown Event"

        full_name = f"{country} - {event_name}"
        if len(full_name) > 100:
            full_name = full_name[:97] + "..."

        if full_name in existing_events and existing_events[full_name] == event_time:
            continue

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
