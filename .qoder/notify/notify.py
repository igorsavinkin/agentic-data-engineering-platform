#!/usr/bin/env python3
"""Send a Telegram alert when a Qoder task blocks or reaches a milestone.

Stdlib only. Fire-and-forget by design: callers should log a non-zero exit but
must never treat a failed notification as a task failure.

    python notify.py --level blocked --subject "TASK-040" --detail "Review BLOCKED"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

TELEGRAM_API = "https://api.telegram.org"
MESSAGE_LIMIT = 4096

LEVELS = {
    "blocked": "[BLOCKED]",
    "failed": "[FAILED]",
    "info": "[INFO]",
    "success": "[DONE]",
}

CONFIG_PATH = Path(__file__).with_name("config.json")


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def load_config() -> tuple[str, str]:
    """Return (bot_token, chat_id); either may be empty if not yet configured."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"notify: cannot read {CONFIG_PATH.name}: {exc}", file=sys.stderr)
            raw = {}
        token = token or str(raw.get("bot_token", "")).strip()
        chat_id = chat_id or str(raw.get("chat_id", "")).strip()

    return token, chat_id


def render(args: argparse.Namespace) -> str:
    lines = [f"{LEVELS[args.level]} {args.subject}"]
    if args.detail:
        lines.append("")
        lines.append(args.detail)
    if args.ref:
        lines.append("")
        lines.append(f"Link: {args.ref}")
    lines.append("")
    lines.append(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"))
    body = "\n".join(lines)
    if len(body) > MESSAGE_LIMIT:
        body = body[: MESSAGE_LIMIT - 20] + "\n... (truncated)"
    return body


def post(url: str, payload: dict, timeout: float) -> tuple[bool, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except OSError:
            detail = ""
        return False, f"HTTP {exc.code}: {detail}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if body.get("ok"):
        return True, "sent"
    return False, body.get("description", "unknown Telegram error")


def get_json(url: str, timeout: float) -> tuple[bool, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - report, never crash a workflow
        return False, f"{type(exc).__name__}: {exc}"


def discover_chat_id(token: str, timeout: float) -> int:
    url = f"{TELEGRAM_API}/bot{token}/getUpdates"
    ok, result = get_json(url, timeout)
    if not ok:
        print(f"notify: getUpdates failed - {result}", file=sys.stderr)
        return 1

    chats: dict[str, str] = {}
    for update in result.get("result", []):
        for key in ("message", "edited_message", "channel_post"):
            chat = update.get(key, {}).get("chat")
            if chat:
                label = chat.get("title") or chat.get("first_name") or "?"
                chats[str(chat["id"])] = f"{label} ({chat.get('type')})"

    if not chats:
        print(
            "notify: no messages found. Open Telegram, send your bot a message "
            "first, then re-run --discover-chat-id.",
            file=sys.stderr,
        )
        return 1

    print("Chat IDs seen by this bot:")
    for chat_id, label in chats.items():
        print(f"  {chat_id}  {label}")
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--level", choices=sorted(LEVELS), default="info")
    parser.add_argument("--subject", help="One-line headline, e.g. 'TASK-040'")
    parser.add_argument("--detail", help="Why it stopped or what finished")
    parser.add_argument("--ref", help="PR or run URL")
    parser.add_argument(
        "--discover-chat-id",
        action="store_true",
        help="List chat IDs that have messaged this bot, then exit",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    token, chat_id = load_config()
    if not token:
        print(
            "notify: no bot token. Set TELEGRAM_BOT_TOKEN or put one in "
            f"{CONFIG_PATH} (copy config.example.json). "
            "Create a token via @BotFather: see README.md.",
            file=sys.stderr,
        )
        return 1

    if args.discover_chat_id:
        return discover_chat_id(token, args.timeout)

    if not chat_id:
        print(
            "notify: no chat_id. Set TELEGRAM_CHAT_ID or add it to "
            f"{CONFIG_PATH}. Run --discover-chat-id to find it.",
            file=sys.stderr,
        )
        return 1

    if not args.subject:
        parser.error("--subject is required unless --discover-chat-id is used")

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": render(args),
        "disable_web_page_preview": True,
    }

    error = ""
    for attempt in range(1, 3):
        ok, error = post(url, payload, args.timeout)
        if ok:
            print(f"notify: {args.level} alert sent to {chat_id}")
            return 0
        if attempt < 2:
            time.sleep(1.5)

    print(f"notify: send failed - {error}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
