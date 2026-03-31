import logging
from pathlib import Path

import nextcord as discord
from nextcord.ext import commands

from config import DEBUG_GUILD_IDS, DEBUG_MODE, DISCORD_TOKEN, OWNER_IDS
from database import db

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(intents=intents, command_prefix="!", owner_ids=OWNER_IDS)

if DEBUG_MODE:
    logger.info(f"🐛 DEBUG MODE ENABLED - Commands will register instantly to guilds {DEBUG_GUILD_IDS}")
else:
    logger.info("🌍 Production mode - Commands will register globally")


@bot.event
async def on_ready():
    await db.connect()
    logger.info(f"✅ {bot.user} is ready!")
    logger.info(f"Logged in as {bot.user.name} ({bot.user.id})")


@bot.event 
async def on_interaction(interaction: discord.Interaction):
    try:
        await bot.process_application_commands(interaction)
    except Exception as e:
        logger.error(f"Error processing interaction: {e}")


@bot.event
async def on_disconnect():
    await db.close()


@bot.event
async def on_guild_join(guild: discord.Guild):
    logger.info(f"Joined new guild: {guild.name} ({guild.id})")

    embed = discord.Embed(
        title="✅ Welcome to the Accountability Tracker!",
        description=(
            "Thanks for adding me to your server! "
            "I send periodic check-ins to keep you on track with your Google Calendar."
        ),
        color=discord.Color.green(),
    )

    embed.add_field(
        name="🚀 Quick Setup",
        value=(
            "Run `/tracker setup` to configure the check-in channel, "
            "your Google Calendar ID, and more.\n\n"
            "**Required Permission:** Manage Channels"
        ),
        inline=False,
    )

    embed.add_field(
        name="📖 Google Calendar",
        value=(
            "You'll need a Google Service Account to pull calendar events. "
            "See the README for a step-by-step guide."
        ),
        inline=False,
    )

    embed.set_footer(text="Run /tracker setup to get started!")
    target_channel = guild.system_channel
    if not target_channel:
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                target_channel = channel
                break

    if target_channel:
        try:
            await target_channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot send welcome message to {guild.name} - no permissions")
    else:
        logger.warning(f"No suitable channel found in {guild.name} for welcome message")


def load_extensions():
    bot.load_extension('onami')
    cogs_dir = Path(__file__).parent / "cogs"
    for cog_file in cogs_dir.glob("*.py"):
        if cog_file.stem.startswith("_"):
            continue
        
        cog_name = f"cogs.{cog_file.stem}"
        try:
            bot.load_extension(cog_name)
            logger.info(f"Loaded extension: {cog_name}")
        except Exception as e:
            logger.error(f"Failed to load extension {cog_name}: {e}")
    for cog_dir in cogs_dir.iterdir():
        if cog_dir.is_dir() and not cog_dir.stem.startswith("_"):
            init_file = cog_dir / "__init__.py"
            if init_file.exists():
                cog_name = f"cogs.{cog_dir.stem}"
                try:
                    bot.load_extension(cog_name)
                    logger.info(f"Loaded extension: {cog_name}")
                except Exception as e:
                    logger.error(f"Failed to load extension {cog_name}: {e}")


if __name__ == "__main__":
    load_extensions()
    bot.run(DISCORD_TOKEN)
