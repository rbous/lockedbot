"""
add_announce_emoji.py
=====================
1. Uploads Announce.gif / Announce-check.png / Announce-failed.png to Discord.
2. Saves the resulting IDs into scripts/emoji_ids.json.
3. Patches the campaign tool entries in cogs/ai/chat_handler.py.

Usage:
    python scripts/add_announce_emoji.py
"""

import base64
import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

REPO_ROOT    = Path(__file__).parent.parent
ASSETS_DIR   = REPO_ROOT / "assets"
JSON_PATH    = Path(__file__).parent / "emoji_ids.json"
HANDLER_PATH = REPO_ROOT / "cogs" / "ai" / "chat_handler.py"

load_dotenv(dotenv_path=REPO_ROOT / ".env")
BOT_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID  = "1462925923547484314"
HEADERS   = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
PREFIX    = "wird"


def file_to_data_uri(path: Path) -> str:
    raw  = path.read_bytes()
    mime = "image/gif" if path.suffix.lower() == ".gif" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def list_existing() -> dict:
    r = requests.get(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/emojis",
        headers=HEADERS, timeout=15,
    )
    r.raise_for_status()
    return {e["name"]: e for e in r.json()}


def upload(name: str, path: Path, existing: dict) -> dict:
    if name in existing:
        print(f"  [skip]     {name}  (already exists, id={existing[name]['id']})")
        return existing[name]
    r = requests.post(
        f"https://discord.com/api/v10/guilds/{GUILD_ID}/emojis",
        headers=HEADERS,
        json={"name": name, "image": file_to_data_uri(path)},
        timeout=20,
    )
    if r.status_code == 429:
        wait = r.json().get("retry_after", 5)
        print(f"  [rate-limit] sleeping {wait}s …")
        time.sleep(wait + 0.5)
        return upload(name, path, existing)
    if not r.ok:
        sys.exit(f"  [ERROR] {name}: {r.status_code} {r.text}")
    emoji = r.json()
    print(f"  [uploaded] {name}  id={emoji['id']}")
    time.sleep(1)
    return emoji


def emoji_str(e: dict) -> str:
    prefix = "a" if e.get("animated") else ""
    return f"<{prefix}:{e['name']}:{e['id']}>"


def patch_chat_handler(anim: str, ok: str, err: str) -> None:
    """Replace every campaign tool entry's emoji triple with Announce ones."""
    src = HANDLER_PATH.read_text(encoding="utf-8")

    # Campaign tools that should use Announce
    campaign_tools = [
        "create_campaign_tool",
        "send_campaign",
        "list_campaigns",
        "get_campaign_responses",
        "add_campaign_button",
    ]

    changed = 0
    for tool in campaign_tools:
        # Match the full tuple line for this tool and replace the 3 emoji fields
        # Pattern: '<tool_name>': ('<any_anim>', '...', '...', '<any_ok>', '<any_err>'),
        pattern = re.compile(
            r"('" + re.escape(tool) + r"'\s*:\s*\()'[^']*'(\s*,\s*'[^']*'\s*,\s*'[^']*'\s*,\s*)'[^']*'(\s*,\s*)'[^']*'",
        )
        replacement = rf"\g<1>'{anim}'\2'{ok}'\3'{err}'"
        new_src, n = re.subn(pattern, replacement, src)
        if n:
            src = new_src
            changed += n
            print(f"  patched  '{tool}'")
        else:
            print(f"  [warn]   '{tool}' not found in handler, skipping")

    HANDLER_PATH.write_text(src, encoding="utf-8")
    print(f"\nPatched {changed} tool entries in {HANDLER_PATH.name}")


def main():
    if not BOT_TOKEN:
        sys.exit("ERROR: DISCORD_TOKEN not found in .env")

    print("Fetching existing guild emojis …")
    existing = list_existing()

    print("\n── Announce ──")
    anim_obj = upload(f"{PREFIX}Announce",      ASSETS_DIR / "Announce.gif",        existing)
    ok_obj   = upload(f"{PREFIX}Announce_ok",   ASSETS_DIR / "Announce-check.png",  existing)
    err_obj  = upload(f"{PREFIX}Announce_err",  ASSETS_DIR / "Announce-failed.png", existing)

    anim_s = emoji_str(anim_obj)
    ok_s   = emoji_str(ok_obj)
    err_s  = emoji_str(err_obj)

    print(f"\n  anim : {anim_s}")
    print(f"  ok   : {ok_s}")
    print(f"  err  : {err_s}")

    # Update JSON
    data = json.loads(JSON_PATH.read_text()) if JSON_PATH.exists() else {}
    data["Announce"] = {
        "anim_id":  anim_obj["id"],
        "ok_id":    ok_obj["id"],
        "err_id":   err_obj["id"],
        "anim_str": anim_s,
        "ok_str":   ok_s,
        "err_str":  err_s,
    }
    JSON_PATH.write_text(json.dumps(data, indent=2))
    print(f"\nUpdated {JSON_PATH}")

    # Patch chat_handler.py
    print("\nPatching chat_handler.py …")
    patch_chat_handler(anim_s, ok_s, err_s)

    print("\nDone! Restart the bot to pick up the new emojis.")


if __name__ == "__main__":
    main()
