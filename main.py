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
intents.message_content = True  # Ajout explicite pour les commandes

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
        return

    print(f"Connexion réussie au serveur : {guild.name}")
    print("Mise à jour du calendrier économique en cours...")

    now = datetime.now(timezone.utc)

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        events = response.json()
    except Exception as e:
        print(f"Erreur fetch Forex Factory : {e}")
        return

    if not events:
        print("Aucune donnée reçue.")
        return

    end_date = now.date() + timedelta(days=15)

    try:
        existing_events = {event.name: event.start_time for event in await guild.fetch_scheduled_events()}
    except Exception as e:
        print(f"Erreur récupération événements : {type(e).__name__}: {e}")
        return

    created_count = 0
    skipped_past_count = 0

    for event in events:
        if event.get('impact') not in ['High', 'Medium']:
            continue

        country = event.get('country', 'Unknown')
        title = event.get('title', 'Unknown Event')
        full_name = f"{country} - {title}"
        if len(full_name) > 100:
            full_name = full_name[:97] + "..."

        try:
            event_time = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        except (ValueError, KeyError):
            continue

        if event_time <= now:
            skipped_past_count += 1
            continue

        if event_time.date() > end_date:
            continue

        end_time = event_time + timedelta(hours=1)

        if full_name in existing_events and existing_events[full_name] == event_time:
            continue

        actual = event.get('actual', 'N/A')
        forecast = event.get('forecast', 'N/A')
        previous = event.get('previous', 'N/A')

        impact_label = "Élevé" if event['impact'] == 'High' else "Moyen"

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
                end_time=end_time,
                entity_type=discord.EntityType.external,
                location='Marché Mondial',
                description=description[:1000],
                privacy_level=discord.PrivacyLevel.guild_only
            )
            print(f"Événement créé : {full_name} le {event_time}")
            created_count += 1
        except Exception as e:
            print(f"Erreur création {full_name} : {type(e).__name__}: {e}")

    print(f"Mise à jour terminée. {created_count} nouveaux événements créés, {skipped_past_count} passés ignorés.")

@bot.command(name='updatecal')
@commands.has_permissions(administrator=True)
async def manual_update(ctx):
    try:
        msg = await ctx.send("🔄 Mise à jour forcée du calendrier en cours...")
        await update_economic_events()
        await msg.edit(content="✅ Mise à jour terminée ! Vérifie l'onglet Événements.")
    except Exception as e:
        await ctx.send(f"Erreur lors de la mise à jour : {e}")

bot.run(DISCORD_TOKEN)
