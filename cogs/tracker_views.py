"""Discord UI views for the accountability tracker."""

import logging
from datetime import datetime, timezone
from typing import Optional

import nextcord as discord

logger = logging.getLogger(__name__)

# Mapping of internal response_type keys to human-readable labels
RESPONSE_LABELS = {
    "on_track": "✅ On Track",
    "slightly_distracted": "🟡 Slightly Distracted",
    "off_track": "❌ Off Track",
}


class AccountabilityView(discord.ui.View):
    """A View that presents three accountability-check buttons.

    Each button records the clicking user's response in the database.
    Multiple users in the same channel can each click a button independently.
    """

    def __init__(
        self,
        guild_id: int,
        calendar_event: Optional[str] = None,
        prompt_id: str = "0",
    ):
        # Timeout of 840 seconds (14 min) keeps the view alive until the next ping.
        super().__init__(timeout=840)
        self.guild_id = guild_id
        self.calendar_event = calendar_event

        button_defs = [
            ("on_track", "✅ On Track", discord.ButtonStyle.success),
            ("slightly_distracted", "🟡 Slightly Distracted", discord.ButtonStyle.secondary),
            ("off_track", "❌ Off Track", discord.ButtonStyle.danger),
        ]

        for response_type, label, style in button_defs:
            btn = discord.ui.Button(
                label=label,
                style=style,
                custom_id=f"tracker_{response_type}_{prompt_id}",
            )
            btn.callback = self._make_callback(response_type, label)
            self.add_item(btn)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_callback(self, response_type: str, label: str):
        """Return an async callback that records *response_type* for the clicking user."""

        async def callback(interaction: discord.Interaction):
            await self._record_response(interaction, response_type, label)

        return callback

    async def _record_response(
        self,
        interaction: discord.Interaction,
        response_type: str,
        label: str,
    ):
        from database import db

        now = datetime.now(timezone.utc)
        prompt_msg_id = interaction.message.id if interaction.message else None

        try:
            await db.tracker.record_response(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                username=str(interaction.user),
                response_type=response_type,
                calendar_event=self.calendar_event,
                prompt_message_id=prompt_msg_id,
                response_date=now.strftime("%Y-%m-%d"),
            )
            await interaction.response.send_message(
                f"Recorded: **{label}**",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error(f"Error recording tracker response: {exc}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Failed to record your response. Please try again.",
                    ephemeral=True,
                )
