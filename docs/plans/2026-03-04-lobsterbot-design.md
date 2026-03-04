# Plan: Claude Code Telegram Personal Assistant

## Context

Build an open-source repo that people fork to get a 24/7 personal AI assistant on Telegram. Claude Code runs on a VPS, pointed at a project directory that IS the assistant's brain. A thin Python layer bridges Telegram to `claude -p` subprocess calls. Users authenticate with their Max subscription via `setup-token` — no API key needed.

Working title: **lobsterbot** (TBD)

## Repository Structure

```
lobsterbot/
├── core/                           # Framework code (never touch in forks)
│   ├── __init__.py
│   ├── bot.py                      # Telegram listener + command handlers
│   ├── bridge.py                   # Claude Code subprocess wrapper
│   ├── session.py                  # SQLite session manager
│   ├── queue.py                    # Per-chat async message queue
│   ├── media.py                    # Voice/photo/doc handling
│   ├── scheduler.py                # Proactive cron-based messaging
│   ├── config.py                   # YAML config loader
│   └── formatter.py                # Markdown → Telegram formatting
│
├── .claude/
│   ├── settings.json               # Pre-configured permissions (security boundary)
│   └── agents/
│       ├── researcher.md           # Web research agent
│       ├── scheduler.md            # Reminders/planning agent
│       └── writer.md               # Drafting/composition agent
│
├── .mcp.json                       # Playwright MCP (headless)
├── CLAUDE.md                       # The brain — personality + instructions
│
├── memory/                         # Gitignored — never leaves machine
│   ├── daily/                      # Auto-created YYYY-MM-DD.md per day
│   ├── chats/                      # Per-conversation summaries
│   └── facts.md                    # Persistent user facts
│
├── user.example/                   # Template people copy from
│   ├── config.yaml                 # Telegram token, user IDs, scheduler
│   └── personality.md              # Extra personality instructions
│
├── user/                           # Gitignored — fork-specific config
│
├── deploy/
│   ├── install.sh                  # One-command Ubuntu VPS setup
│   ├── update.sh                   # Pull upstream + restart services
│   └── systemd/
│       ├── claude-bot.service
│       └── claude-scheduler.service
│
├── scripts/
│   └── setup_wizard.py             # Interactive config wizard
│
├── requirements.txt
├── .gitignore
└── README.md
```

## Key Architecture Decisions

### Subprocess Bridge (`core/bridge.py`)
- Uses `claude -p "msg" --output-format json --resume SESSION_ID`
- Returns `ClaudeResponse(text, session_id, cost_usd, usage)`
- Uses `--permission-mode bypassPermissions` (safe because `.claude/settings.json` deny list is still enforced — this just skips interactive prompts since there's no human)
- Strips `CLAUDECODE` env var to allow nested subprocess invocation

### Session Management (`core/session.py`)
- SQLite maps `telegram_chat_id → claude_session_id`
- First message: no `--resume`, response returns `session_id`, store it
- Subsequent messages: `--resume SESSION_ID` continues conversation
- Auto-archive after 24h inactivity; `/new` command starts fresh
- Session history table for old conversations

### Message Queue (`core/queue.py`)
- asyncio queue per chat_id — messages process sequentially
- If multiple messages arrive while Claude is thinking, concatenate them into one prompt
- File-based lock (`fcntl.flock`) coordinates bot + scheduler processes (both call Claude Code against same project dir)

### Permissions (`.claude/settings.json`)
- **Allow**: `Read`, `WebSearch`, `WebFetch(*)`, `Write(./memory/**)`, `Edit(./memory/**)`, safe bash commands (`date`, `python3`, `curl -s`, `ls`, etc.)
- **Deny**: `Write(./core/**)`, `Edit(./.claude/**)`, `Bash(sudo *)`, `Bash(rm -rf *)`, `Bash(systemctl *)`, `Read(./.env)`, all destructive/system-modifying commands

### Pre-built Agents (`.claude/agents/`)
1. **researcher.md** — Web search, synthesis, source citation (model: sonnet, maxTurns: 15)
2. **scheduler.md** — Daily logs, task tracking, reminders (model: sonnet, maxTurns: 10)
3. **writer.md** — Emails, docs, social media, tone matching (model: inherit, maxTurns: 10)

### Memory System
- `memory/daily/YYYY-MM-DD.md` — Auto-created per day, Claude appends notable events
- `memory/chats/` — Per-conversation summaries
- `memory/facts.md` — User fills in about themselves (name, location, preferences, work)
- CLAUDE.md instructs: read facts.md + today's daily + yesterday's daily at start of every session

### MCP (`.mcp.json`)
- Playwright with `--headless` flag (no display on VPS)
- Ships only Playwright by default — users add more MCP servers to their config

### Scheduler (`core/scheduler.py`)
- Separate systemd service, runs independently from bot
- Tasks defined in `user/config.yaml` with cron expressions + prompts
- Can message user proactively (morning briefs, evening summaries, weekly reviews)
- File lock prevents concurrent Claude Code invocations

### Telegram Commands
- `/new` — Start new conversation
- `/status` — Session info, uptime
- `/facts` — Show/edit persistent facts
- `/today` — Show today's daily log
- `/search` — Search memory
- `/help` — Available commands

### Media Handling
- **Voice**: Download OGG → ffmpeg to WAV → faster-whisper transcription → prepend to prompt
- **Photos**: Download to temp dir → tell Claude the path → Claude reads via multimodal Read tool
- **Documents**: Same as photos (PDFs, text files, etc.)
- Cleanup after processing or 1h TTL

### Upstream/Fork Split
- `user/` and `memory/` gitignored — never pushed upstream
- `user.example/` is the template — `install.sh` copies it to `user/`
- Framework changes in `core/`, `.claude/`, `deploy/` flow upstream cleanly
- `deploy/update.sh` pulls upstream, restarts services, never touches user config

## Implementation Phases

### Phase 1: Walking Skeleton (ship first)
1. `core/bridge.py` — subprocess wrapper, json mode only
2. `core/session.py` — SQLite session manager
3. `core/config.py` — YAML config loader
4. `core/bot.py` — Telegram listener, text messages only
5. `CLAUDE.md` — Basic assistant template
6. `.claude/settings.json` — Permissions
7. `user.example/config.yaml` — Config template
8. `requirements.txt` — python-telegram-bot, pyyaml
9. `.gitignore`

**Goal**: Working text-based assistant in ~500 lines of Python.

### Phase 2: Memory + Agents
1. Memory system (daily log creation, facts.md reading)
2. Three agents (researcher, scheduler, writer)
3. `.mcp.json` with Playwright
4. `core/queue.py` for concurrent message handling

### Phase 3: Media + Polish
1. `core/media.py` — voice, photo, document handling
2. `core/formatter.py` — Markdown → Telegram formatting
3. Streaming responses for long tasks (stream-json mode)

### Phase 4: Scheduler + Deploy
1. `core/scheduler.py` — cron-based proactive messaging
2. `deploy/install.sh` — one-command VPS setup
3. `deploy/systemd/` — service files
4. `deploy/update.sh`
5. `scripts/setup_wizard.py`

## Verification
- Phase 1: Run bot locally, send text message on Telegram, get response back
- Phase 2: Verify memory files created, agent delegation works
- Phase 3: Send voice/photo, verify transcription/reading works
- Phase 4: Deploy to VPS, verify systemd services run, scheduler sends proactive messages

## Dependencies
```
python-telegram-bot>=21.0
pyyaml>=6.0
croniter>=1.3
faster-whisper>=0.10.0  # Phase 3
```
