"""Google Calendar integration using a service account.

Setup guide
-----------
1. Go to https://console.cloud.google.com/ and create a new project.
2. Enable the "Google Calendar API" for your project.
3. Create a Service Account under "APIs & Services > Credentials".
4. Download the JSON key file for the service account.
5. Share each calendar you want to track with the service account e-mail address
   (the address ends with @<project>.iam.gserviceaccount.com).  Grant it at least
   "See all event details" (reader) access.
6. In your .env file set one of:
      GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
   OR
      GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
7. Configure the calendar ID for each server with /tracker setup.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_credentials():
    """Return Google service-account credentials, or None if not configured."""
    try:
        from google.oauth2 import service_account  # type: ignore
    except ImportError:
        logger.error(
            "google-auth is not installed. "
            "Run: pip install google-auth google-api-python-client"
        )
        return None

    creds_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if creds_file and os.path.exists(creds_file):
        return service_account.Credentials.from_service_account_file(
            creds_file, scopes=SCOPES
        )

    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        try:
            info = json.loads(creds_json)
            return service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
        except json.JSONDecodeError as exc:
            logger.error(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {exc}")

    return None


def get_calendar_service():
    """Build and return a Google Calendar API service, or None if credentials are missing."""
    credentials = _get_credentials()
    if not credentials:
        return None

    try:
        from googleapiclient.discovery import build  # type: ignore

        return build("calendar", "v3", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        logger.error(f"Failed to build Google Calendar service: {exc}")
        return None


def get_current_or_upcoming_event(
    service, calendar_id: str
) -> Optional[Dict[str, Any]]:
    """Return the event that is currently active or starting soonest within the next 2 hours.

    Returns None if there are no upcoming events or if the API call fails.
    """
    try:
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(hours=2)

        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=1,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = result.get("items", [])
        return events[0] if events else None
    except Exception as exc:
        logger.error(f"Error fetching Google Calendar events: {exc}")
        return None


def get_event_name(event: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract the human-readable summary from an event dict."""
    if event:
        return event.get("summary") or "Unnamed Event"
    return None


def is_configured() -> bool:
    """Return True if Google Calendar credentials are available."""
    return _get_credentials() is not None
