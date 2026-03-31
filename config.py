import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLOUDCONVERT_API_KEY = os.getenv("CLOUDCONVERT_API_KEY")

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEBUG_GUILD_IDS = [int(gid.strip()) for gid in os.getenv("DEBUG_GUILD_IDS", "").split(",") if gid.strip()] if DEBUG_MODE else []

TOOL_LOG_CHANNEL_ID = int(os.getenv("TOOL_LOG_CHANNEL_ID")) if os.getenv("TOOL_LOG_CHANNEL_ID") and os.getenv("TOOL_LOG_CHANNEL_ID").isdigit() else None
MAX_TOOL_CALLS = int(os.getenv("MAX_TOOL_CALLS", "15"))

OWNER_IDS = {
    1030575337869955102,
    1172856531667140669
}
