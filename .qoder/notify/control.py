#!/usr/bin/env python3
"""
Telegram bot control daemon - receive commands via Telegram, execute locally.

Polls Telegram's getUpdates API for incoming messages, parses commands,
and sends responses back. Reuses the same config.json as notify.py.

Usage:
    python .qoder/notify/control.py          # run in foreground
    python .qoder/notify/control.py &        # run in background

Commands:
    /status   - Show running tasks, last merge, queue status
    /list     - List available task specs in ai/tasks/
    /help     - Show this help message

Security:
    Only accepts commands from the chat_id configured in config.json.
    All other messages are ignored.

Stop:
    Ctrl+C (foreground) or kill the PID (background)
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# UTF-8 for Windows terminals
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, AttributeError):
                pass

TELEGRAM_API = "https://api.telegram.org"
CONFIG_PATH = Path(__file__).parent / "config.json"
POLL_INTERVAL = 3  # seconds
OFFSET_FILE = Path(__file__).parent / ".control_offset"


def load_config() -> tuple[str, str]:
    """Return (bot_token, chat_id) from config.json or environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"control: cannot read {CONFIG_PATH.name}: {exc}", file=sys.stderr)
            raw = {}
        token = token or str(raw.get("bot_token", "")).strip()
        chat_id = chat_id or str(raw.get("chat_id", "")).strip()
    return token, chat_id


def load_offset() -> int:
    """Load last processed update ID to avoid reprocessing."""
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass
    return 0


def save_offset(offset: int) -> None:
    """Save last processed update ID."""
    try:
        OFFSET_FILE.write_text(str(offset), encoding="utf-8")
    except OSError as exc:
        print(f"control: cannot save offset: {exc}", file=sys.stderr)


def api_get(url: str, timeout: float = 10.0) -> tuple[bool, dict | str]:
    """GET request to Telegram API. Return (ok, result_or_error)."""
    req = urllib.request.Request(url, method="GET")
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
        return True, body.get("result", [])
    return False, body.get("description", "unknown Telegram error")


def api_post(url: str, payload: dict, timeout: float = 10.0) -> tuple[bool, str]:
    """POST request to Telegram API. Return (ok, error_message)."""
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


def send_message(token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API."""
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    ok, result = api_post(url, payload)
    if not ok:
        print(f"control: sendMessage failed: {result}", file=sys.stderr)
    return ok


def handle_status() -> str:
    """Handle /status command - show running tasks, last merge, queue."""
    import subprocess

    lines = ["*Status*", ""]

    # Last merge from git log
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        commits = result.stdout.strip().split("\n")
        last_merge = None
        for commit in commits:
            if "feat(TASK-" in commit or "fix(TASK-" in commit:
                last_merge = commit
                break
        if last_merge:
            lines.append(f"Last merge: {last_merge}")
        else:
            lines.append("Last merge: (none found in last 10 commits)")
    except (subprocess.SubprocessError, FileNotFoundError):
        lines.append("Last merge: (git unavailable)")

    # Running orchestrator processes (crude check)
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Count python processes (very rough)
            count = len([line for line in result.stdout.split("\n") if "python" in line.lower()])
        else:
            result = subprocess.run(
                ["pgrep", "-f", "qoder-task-orchestrator"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            count = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0

        if count > 0:
            lines.append(f"Running: {count} python process(es)")
        else:
            lines.append("Running: none")
    except (subprocess.SubprocessError, FileNotFoundError):
        lines.append("Running: (check unavailable)")

    # Queue status (MVP: always empty)
    lines.append("Queue: empty")
    lines.append("")
    lines.append(f"_{datetime.now().astimezone().strftime('%H:%M %Z')}_")

    return "\n".join(lines)


def handle_list() -> str:
    """Handle /list command - show available task specs."""
    from glob import glob

    task_dir = Path("ai/tasks")
    if not task_dir.exists():
        return "No ai/tasks/ directory found."

    task_files = sorted(glob(str(task_dir / "TASK-*.md")))
    if not task_files:
        return "No task specs found in ai/tasks/."

    lines = [f"*Available Tasks* ({len(task_files)} total)", ""]

    for task_file in task_files[:20]:  # limit to 20 to avoid message overflow
        task_id = Path(task_file).stem
        # Read first line as title
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                # Skip markdown headers
                if first_line.startswith("#"):
                    first_line = first_line.lstrip("#").strip()
                if len(first_line) > 60:
                    first_line = first_line[:57] + "..."
            lines.append(f"• {task_id}: {first_line}")
        except (OSError, UnicodeDecodeError):
            lines.append(f"• {task_id}: (unreadable)")

    if len(task_files) > 20:
        lines.append(f"... and {len(task_files) - 20} more")

    return "\n".join(lines)


def handle_help() -> str:
    """Handle /help command - show available commands."""
    return """*Available Commands*

/status - Show running tasks, last merge, queue
/list - List available task specs
/help - Show this help message

*Coming soon:*
/run TASK-XXX - Start orchestrator for task
/batch TASK-001,TASK-002 - Run multiple tasks
/cancel - Stop current run"""


def process_command(token: str, chat_id: str, text: str) -> None:
    """Parse and execute a command, send response."""
    text = text.strip()
    if not text.startswith("/"):
        return

    # Parse command (ignore arguments for now)
    command = text.split()[0].lower().split("@")[0]  # handle /cmd@botname

    if command == "/status":
        response = handle_status()
    elif command == "/list":
        response = handle_list()
    elif command == "/help" or command == "/start":
        response = handle_help()
    else:
        response = f"Unknown command: {command}\n\n{handle_help()}"

    send_message(token, chat_id, response)


def main() -> int:
    token, allowed_chat_id = load_config()
    if not token:
        print(
            "control: bot_token not found. Create config.json or set TELEGRAM_BOT_TOKEN.",
            file=sys.stderr,
        )
        return 1
    if not allowed_chat_id:
        print(
            "control: chat_id not found. Create config.json or set TELEGRAM_CHAT_ID.",
            file=sys.stderr,
        )
        return 1

    print(f"control: polling for commands (chat_id={allowed_chat_id})...")
    print("control: send /help to see available commands")

    offset = load_offset()

    while True:
        try:
            url = f"{TELEGRAM_API}/bot{token}/getUpdates?offset={offset}&timeout=30"
            ok, result = api_get(url, timeout=35)

            if not ok:
                print(f"control: getUpdates failed: {result}", file=sys.stderr)
                time.sleep(POLL_INTERVAL)
                continue

            updates = result if isinstance(result, list) else []

            for update in updates:
                update_id = update.get("update_id", 0)
                message = update.get("message", {})
                chat = message.get("chat", {})
                chat_id = str(chat.get("id", ""))
                text = message.get("text", "")

                # Security: only accept from configured chat_id
                if chat_id != allowed_chat_id:
                    print(f"control: ignored message from {chat_id} (not authorized)")
                    offset = update_id + 1
                    continue

                if text:
                    print(f"control: received command: {text}")
                    try:
                        process_command(token, chat_id, text)
                    except Exception as exc:
                        print(f"control: command failed: {exc}", file=sys.stderr)
                        send_message(token, chat_id, f"Error: {exc}")

                offset = update_id + 1

            if updates:
                save_offset(offset)

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            print("\ncontrol: stopped")
            return 0
        except Exception as exc:
            print(f"control: unexpected error: {exc}", file=sys.stderr)
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
