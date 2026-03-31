"""Accountability tracker cog.

Sends periodic prompts to a configured Discord channel asking users how well
they are following their Google Calendar.  Compiles all responses at the end
of the day into a summary report.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import nextcord as discord
import pytz
from nextcord import SlashOption
from nextcord.ext import commands, tasks

from database import db

logger = logging.getLogger(__name__)

VALID_INTERVALS = [5, 10, 15, 20, 30, 60]


def _admin_check():
    """Require the user to have Manage Channels (or server admin) permission."""

    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.manage_channels

    return commands.check(predicate)


def _resolve_tz(tz_name: str) -> Any:
    try:
        return pytz.timezone(tz_name)
    except pytz.UnknownTimeZoneError:
        return pytz.UTC


def _build_summary_embed(
    responses: List[Dict[str, Any]], date: str
) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 Daily Accountability Summary — {date}",
        color=discord.Color.gold(),
    )

    if not responses:
        embed.description = "No responses were recorded today."
        return embed

    on_track = sum(1 for r in responses if r["response_type"] == "on_track")
    slightly = sum(1 for r in responses if r["response_type"] == "slightly_distracted")
    off_track = sum(1 for r in responses if r["response_type"] == "off_track")
    total = len(responses)

    def pct(n: int) -> str:
        return f"{n * 100 // total}%" if total else "0%"

    embed.add_field(
        name="📈 Overall",
        value=(
            f"✅ On Track: **{on_track}** ({pct(on_track)})\n"
            f"🟡 Slightly Distracted: **{slightly}** ({pct(slightly)})\n"
            f"❌ Off Track: **{off_track}** ({pct(off_track)})\n"
            f"📝 Total Responses: **{total}**"
        ),
        inline=False,
    )

    # Per-user breakdown
    user_stats: Dict[int, Dict] = {}
    for r in responses:
        uid = r["user_id"]
        if uid not in user_stats:
            user_stats[uid] = {
                "username": r["username"],
                "on_track": 0,
                "slightly_distracted": 0,
                "off_track": 0,
            }
        user_stats[uid][r["response_type"]] += 1

    for stats in user_stats.values():
        user_total = (
            stats["on_track"] + stats["slightly_distracted"] + stats["off_track"]
        )
        embed.add_field(
            name=f"👤 {stats['username']}",
            value=(
                f"✅ {stats['on_track']} | "
                f"🟡 {stats['slightly_distracted']} | "
                f"❌ {stats['off_track']}\n"
                f"Responses: {user_total}"
            ),
            inline=True,
        )

    return embed


class TrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory tracking to avoid flooding (guild_id -> datetime)
        self._last_ping: Dict[int, datetime] = {}
        # guild_id -> date string of last sent summary
        self._last_summary: Dict[int, str] = {}
        self.tracker_loop.start()

    def cog_unload(self):
        self.tracker_loop.cancel()

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def tracker_loop(self):
        try:
            configs = await db.tracker.get_all_enabled()
        except Exception as exc:
            logger.error(f"Tracker loop: failed to fetch configs: {exc}")
            return

        now_utc = datetime.now(timezone.utc)

        for config in configs:
            guild_id = config["guild_id"]
            try:
                tz = _resolve_tz(config.get("timezone", "UTC"))
                now_local = now_utc.astimezone(tz)

                # --- Ping check ---
                interval = int(config.get("ping_interval_minutes", 15))
                last_ping = self._last_ping.get(guild_id)
                seconds_since = (
                    (now_utc - last_ping).total_seconds() if last_ping else float("inf")
                )
                if seconds_since >= interval * 60:
                    await self._send_ping(config)
                    self._last_ping[guild_id] = now_utc

                # --- Summary check ---
                summary_time = config.get("summary_time", "22:00")
                today = now_local.strftime("%Y-%m-%d")
                current_hm = now_local.strftime("%H:%M")
                if (
                    current_hm == summary_time
                    and self._last_summary.get(guild_id) != today
                ):
                    await self._send_summary(config, today)
                    self._last_summary[guild_id] = today

            except Exception as exc:
                logger.error(f"Tracker loop error for guild {guild_id}: {exc}")

    @tracker_loop.before_loop
    async def before_tracker_loop(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_ping(self, config: Dict[str, Any]):
        guild_id = config["guild_id"]
        channel = self.bot.get_channel(int(config["channel_id"]))
        if not channel:
            logger.warning(
                f"Tracker: channel {config['channel_id']} not found for guild {guild_id}"
            )
            return

        calendar_event: Optional[str] = None
        if config.get("calendar_id"):
            try:
                from utils.calendar_client import (
                    get_calendar_service,
                    get_current_or_upcoming_event,
                    get_event_name,
                )

                service = get_calendar_service()
                if service:
                    event = get_current_or_upcoming_event(service, config["calendar_id"])
                    calendar_event = get_event_name(event)
            except Exception as exc:
                logger.error(
                    f"Tracker: calendar fetch failed for guild {guild_id}: {exc}"
                )

        embed = discord.Embed(
            title="⏰ Accountability Check-In",
            color=discord.Color.blurple(),
        )
        if calendar_event:
            embed.description = (
                f"📅 Current activity: **{calendar_event}**\n\n"
                "How are you doing right now?"
            )
        else:
            embed.description = "How are you doing right now?"

        tz = _resolve_tz(config.get("timezone", "UTC"))
        local_time = datetime.now(timezone.utc).astimezone(tz)
        embed.set_footer(text=local_time.strftime("%-I:%M %p %Z"))

        from cogs.tracker_views import AccountabilityView

        prompt_id = uuid.uuid4().hex[:8]
        view = AccountabilityView(
            guild_id=guild_id,
            calendar_event=calendar_event,
            prompt_id=prompt_id,
        )

        try:
            await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            logger.warning(
                f"Tracker: no permission to send in channel {config['channel_id']} "
                f"for guild {guild_id}"
            )
        except Exception as exc:
            logger.error(f"Tracker: failed to send ping to guild {guild_id}: {exc}")

    async def _send_summary(self, config: Dict[str, Any], date: str):
        guild_id = config["guild_id"]
        channel_id = config.get("summary_channel_id") or config["channel_id"]
        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            logger.warning(
                f"Tracker: summary channel {channel_id} not found for guild {guild_id}"
            )
            return

        try:
            responses = await db.tracker.get_responses_for_date(guild_id, date)
            embed = _build_summary_embed(responses, date)
            await channel.send(embed=embed)
        except Exception as exc:
            logger.error(
                f"Tracker: failed to send summary to guild {guild_id}: {exc}"
            )

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    @discord.slash_command(
        name="tracker", description="Accountability tracker commands"
    )
    async def tracker(self, interaction: discord.Interaction):
        pass

    @tracker.subcommand(
        name="setup",
        description="Configure the accountability tracker for this server",
    )
    @_admin_check()
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = SlashOption(
            name="channel",
            description="Channel where 15-minute check-ins will be posted",
            required=True,
        ),
        calendar_id: Optional[str] = SlashOption(
            name="calendar_id",
            description="Google Calendar ID (e.g. user@gmail.com or the long hex ID)",
            required=False,
        ),
        summary_channel: Optional[discord.TextChannel] = SlashOption(
            name="summary_channel",
            description="Channel for daily summary (defaults to the main channel)",
            required=False,
        ),
        timezone: str = SlashOption(
            name="timezone",
            description="Your timezone, e.g. America/New_York (default: UTC)",
            required=False,
            default="UTC",
        ),
        interval: int = SlashOption(
            name="interval",
            description="How often to ping in minutes (default: 15)",
            required=False,
            default=15,
            choices={str(v): v for v in VALID_INTERVALS},
        ),
        summary_time: str = SlashOption(
            name="summary_time",
            description="Time to send daily summary, 24-h HH:MM in your timezone (default: 22:00)",
            required=False,
            default="22:00",
        ),
    ):
        """Set up or update the accountability tracker for this server."""
        # Validate timezone
        try:
            pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            await interaction.response.send_message(
                f"❌ Unknown timezone: `{timezone}`. "
                "Use a valid tz name like `America/New_York` or `Europe/London`.",
                ephemeral=True,
            )
            return

        # Validate summary_time format
        try:
            datetime.strptime(summary_time, "%H:%M")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid summary time. Use 24-hour format, e.g. `22:00`.",
                ephemeral=True,
            )
            return

        kwargs: Dict[str, Any] = {
            "channel_id": channel.id,
            "timezone": timezone,
            "ping_interval_minutes": interval,
            "summary_time": summary_time,
            "enabled": 1,
        }
        if calendar_id is not None:
            kwargs["calendar_id"] = calendar_id
        if summary_channel is not None:
            kwargs["summary_channel_id"] = summary_channel.id

        await db.tracker.create_or_update_config(interaction.guild_id, **kwargs)

        embed = discord.Embed(
            title="✅ Tracker Configured",
            color=discord.Color.green(),
        )
        embed.add_field(name="Check-In Channel", value=channel.mention, inline=True)
        embed.add_field(
            name="Summary Channel",
            value=summary_channel.mention if summary_channel else channel.mention,
            inline=True,
        )
        embed.add_field(
            name="Calendar ID",
            value=f"`{calendar_id}`" if calendar_id else "*(not set)*",
            inline=False,
        )
        embed.add_field(name="Timezone", value=timezone, inline=True)
        embed.add_field(name="Ping Interval", value=f"{interval} min", inline=True)
        embed.add_field(name="Summary Time", value=summary_time, inline=True)
        embed.set_footer(
            text="Use /tracker disable to pause tracking, /tracker enable to resume."
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tracker.subcommand(name="status", description="Show the current tracker configuration")
    async def status(self, interaction: discord.Interaction):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ The tracker is not configured for this server. "
                "Use `/tracker setup` to get started.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔍 Tracker Status",
            color=discord.Color.blue() if config["enabled"] else discord.Color.greyple(),
        )
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if config["enabled"] else "🔴 Disabled",
            inline=True,
        )
        embed.add_field(
            name="Check-In Channel",
            value=f"<#{config['channel_id']}>",
            inline=True,
        )
        summary_ch = config.get("summary_channel_id")
        embed.add_field(
            name="Summary Channel",
            value=f"<#{summary_ch}>" if summary_ch else f"<#{config['channel_id']}> *(same)*",
            inline=True,
        )
        embed.add_field(
            name="Calendar ID",
            value=f"`{config['calendar_id']}`" if config.get("calendar_id") else "*(not set)*",
            inline=False,
        )
        embed.add_field(name="Timezone", value=config.get("timezone", "UTC"), inline=True)
        embed.add_field(
            name="Ping Interval",
            value=f"{config.get('ping_interval_minutes', 15)} min",
            inline=True,
        )
        embed.add_field(
            name="Summary Time",
            value=config.get("summary_time", "22:00"),
            inline=True,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tracker.subcommand(name="enable", description="Enable accountability pings")
    @_admin_check()
    async def enable(self, interaction: discord.Interaction):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ No tracker configured yet. Use `/tracker setup` first.",
                ephemeral=True,
            )
            return
        await db.tracker.create_or_update_config(interaction.guild_id, enabled=1)
        await interaction.response.send_message(
            "✅ Accountability tracker **enabled**.", ephemeral=True
        )

    @tracker.subcommand(name="disable", description="Pause accountability pings")
    @_admin_check()
    async def disable(self, interaction: discord.Interaction):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ No tracker configured yet. Use `/tracker setup` first.",
                ephemeral=True,
            )
            return
        await db.tracker.create_or_update_config(interaction.guild_id, enabled=0)
        await interaction.response.send_message(
            "🔴 Accountability tracker **disabled**.", ephemeral=True
        )

    @tracker.subcommand(
        name="ping_now",
        description="Manually send an accountability check-in right now (admin)",
    )
    @_admin_check()
    async def ping_now(self, interaction: discord.Interaction):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ No tracker configured. Use `/tracker setup` first.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            "⏰ Sending accountability check-in…", ephemeral=True
        )
        await self._send_ping(config)

    @tracker.subcommand(
        name="summary",
        description="Generate the accountability summary for today (or a specific date)",
    )
    @_admin_check()
    async def summary(
        self,
        interaction: discord.Interaction,
        date: Optional[str] = SlashOption(
            name="date",
            description="Date to summarise, YYYY-MM-DD (defaults to today)",
            required=False,
        ),
    ):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ No tracker configured. Use `/tracker setup` first.",
                ephemeral=True,
            )
            return

        if date:
            try:
                datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid date format. Use `YYYY-MM-DD`.",
                    ephemeral=True,
                )
                return
        else:
            tz = _resolve_tz(config.get("timezone", "UTC"))
            date = datetime.now(timezone.utc).astimezone(tz).strftime("%Y-%m-%d")

        await interaction.response.defer(ephemeral=False)
        responses = await db.tracker.get_responses_for_date(interaction.guild_id, date)
        embed = _build_summary_embed(responses, date)
        await interaction.followup.send(embed=embed)

    @tracker.subcommand(
        name="remove",
        description="Remove the tracker configuration for this server (admin)",
    )
    @_admin_check()
    async def remove(self, interaction: discord.Interaction):
        config = await db.tracker.get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message(
                "❌ No tracker configured for this server.",
                ephemeral=True,
            )
            return

        view = discord.ui.View(timeout=60)

        async def confirm_callback(confirm_interaction: discord.Interaction):
            await db.tracker.delete_config(interaction.guild_id)
            self._last_ping.pop(interaction.guild_id, None)
            self._last_summary.pop(interaction.guild_id, None)
            await confirm_interaction.response.edit_message(
                content="🗑️ Tracker configuration removed.", view=None
            )

        async def cancel_callback(cancel_interaction: discord.Interaction):
            await cancel_interaction.response.edit_message(
                content="Cancelled.", view=None
            )

        confirm_btn = discord.ui.Button(
            label="Confirm Remove", style=discord.ButtonStyle.danger
        )
        confirm_btn.callback = confirm_callback
        cancel_btn = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.secondary
        )
        cancel_btn.callback = cancel_callback
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)

        await interaction.response.send_message(
            "⚠️ Are you sure you want to remove the tracker configuration? "
            "All stored response data for this server will also be deleted.",
            view=view,
            ephemeral=True,
        )


def setup(bot: commands.Bot):
    bot.add_cog(TrackerCog(bot))
