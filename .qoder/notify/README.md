# Telegram alerts for Qoder tasks

Get pinged on your phone when a task workflow blocks and needs you, or when it
finishes. One Python file, stdlib only, no packages to install.

This folder is git-ignored (see `.gitignore`) because `config.json` holds a bot
token.

## Setup (about 5 minutes)

**1. Create the bot.** Message [@BotFather](https://t.me/BotFather) in Telegram:

```
/newbot
```

Follow the prompts. BotFather replies with a token like
`8123456789:AAF4Q....` — keep it private, anyone holding it can message your bot's
chats.

**2. Start the chat.** Press START on your new bot, then send it any message
(e.g. `hi`). Telegram only lets a bot message chats that have spoken to it first.
Skip this step and `sendMessage` fails silently with `403 Forbidden`.

**3. Save the credentials.**

```bash
cp .qoder/notify/config.example.json .qoder/notify/config.json
```

Then edit `config.json` and paste the token.

**4. Find your chat ID.**

```bash
python .qoder/notify/notify.py --discover-chat-id
```

Prints every chat that has messaged the bot. Put the numeric ID into
`config.json` as `chat_id`. Negative IDs are groups and channels; a positive one
is your personal chat.

Alternatively skip the file and export env vars, which take priority:

```bash
export TELEGRAM_BOT_TOKEN="8123456789:AAF4Q..."
export TELEGRAM_CHAT_ID="555121234"
```

**5. Prove it works.**

```bash
python .qoder/notify/notify.py --level success --subject "notify smoke test" --detail "wired up correctly"
```

## Usage

```bash
python .qoder/notify/notify.py \
  --level blocked \
  --subject "TASK-040 review BLOCKED" \
  --detail "Qwen verdict BLOCKED on round 3; owner decision needed" \
  --ref "https://github.com/<owner>/<repo>/pull/53"
```

| Flag | Meaning |
|---|---|
| `--level` | `blocked`, `failed`, `info`, `success` — sets the `[TAG]` prefix |
| `--subject` | One-line headline, shown first |
| `--detail` | Why it stopped, or what finished |
| `--ref` | Optional PR or run URL |

Bodies over 4096 characters are truncated, so an oversized log excerpt can never
cause Telegram to reject the alert.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Delivered |
| 1 | Not configured, or bad arguments |
| 2 | Telegram rejected the request after one retry |

**A non-zero exit is never a task failure.** Alerting is best-effort — a network
blip must not abort a healthy run. Log the exit code and keep going.

## Why Telegram and not WhatsApp

Every WhatsApp alerting path is a commercial product. Meta's Cloud API needs a
Business account plus message templates pre-approved by Meta, which does not suit
free-form text like "TASK-040 blocked at round 3". Twilio's WhatsApp sandbox is
easier but paid and limited to numbers you manually opt in. Telegram is one
HTTPS POST and free.

## Troubleshooting

- **`HTTP 401`** — token wrong or revoked. Regenerate via BotFather `/revoke`.
- **`HTTP 403`** — you never messaged the bot (step 2), or you blocked it.
- **`HTTP 400` with a chat_id** — ID typo, or it is a group you have since left.
- **`--discover-chat-id` prints nothing** — no message has been sent to the bot
  yet, or the update is older than Telegram's 24h window. Message it again.

## Control daemon (bidirectional commands)

Send commands to the bot from your phone, get responses back. Uses the same
`config.json` as `notify.py`.

**Run it:**

```bash
python .qoder/notify/control.py          # foreground, Ctrl+C to stop
python .qoder/notify/control.py &        # background
```

**Available commands:**

| Command | Response |
|---|---|
| `/status` | Last merge, running processes, queue status |
| `/list` | Available task specs in `ai/tasks/` |
| `/help` | Show available commands |

**Security:** only the `chat_id` in `config.json` can send commands. All other
messages are ignored with a log line.

**Example session:**

```
You: /status
Bot: Status

     Last merge: c8bff33 fix(TASK-040): Add mypy type annotations
     Running: none
     Queue: empty

     14:23 UTC

You: /list
Bot: Available Tasks (45 total)

     • TASK-001: Initial project structure
     • TASK-002: Core data models
     ...
```

**Coming soon:** `/run TASK-XXX`, `/batch`, `/cancel` for triggering orchestrator
runs remotely.
