"""
User-facing tools for the AI cog.
"""
import logging
from datetime import datetime, timezone

from database import db

logger = logging.getLogger(__name__)


async def get_my_tracker_stats(**kwargs):
    """
    Get the calling user's accountability tracker stats for today.
    Returns a summary of their on-track / distracted / off-track responses.
    """
    message = kwargs.get('message')
    user_id = message.author.id if message else kwargs.get('user_id')
    guild_id = kwargs.get('guild_id')

    if not user_id or not guild_id:
        return "Error: User context missing."

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    responses = await db.tracker.get_responses_for_date(guild_id, today)
    user_responses = [r for r in responses if r['user_id'] == user_id]

    if not user_responses:
        return f"No tracker responses recorded for you today ({today})."

    on_track = sum(1 for r in user_responses if r['response_type'] == 'on_track')
    slightly = sum(1 for r in user_responses if r['response_type'] == 'slightly_distracted')
    off_track = sum(1 for r in user_responses if r['response_type'] == 'off_track')
    total = len(user_responses)

    return (
        f"**Your Accountability Stats for {today}:**\n"
        f"- ✅ On Track: {on_track}\n"
        f"- 🟡 Slightly Distracted: {slightly}\n"
        f"- ❌ Off Track: {off_track}\n"
        f"- 📝 Total Responses: {total}"
    )


USER_TOOLS = [
    get_my_tracker_stats,
]
