# Reddit Copilot

Formerly **Reddit-Karma-Bot** — now a **human-in-the-loop** Reddit engagement assistant.

It finds threads and drafts replies in your voice. You approve in a few minutes. Nothing posts without you.

Local-first, open source. Python owns Reddit, the LLM, SQLite, and the worker. Next.js owns the review desk.

## Quickstart

```bash
# Python 3.10+
git clone https://github.com/meet447/Reddit-Karma-Bot.git
cd Reddit-Karma-Bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

rcopilot init
```

1. Copy `.env.example` → `.env` and fill in Reddit client id/secret + LLM key.
2. Edit `config.yaml` (subreddits, keywords, voice, model) — or finish onboarding in the UI.
3. Create a Reddit **web** app at https://www.reddit.com/prefs/apps. Redirect URI must be exactly:
   `http://127.0.0.1:8000/api/oauth/callback`
4. Open http://localhost:3000 and click **Connect Reddit**. Copilot stores a refresh token in `.env` — not your password.

```bash
# Terminal 1 — API (and optionally the discover/draft worker)
rcopilot serve            # http://127.0.0.1:8000
# rcopilot serve --with-worker

# Terminal 2 — review UI
cd web && npm install && npm run dev   # http://localhost:3000
```

Or drive the pipeline from the CLI:

```bash
rcopilot fetch     # pull posts
rcopilot draft     # generate replies
rcopilot post      # publish approved drafts
```

## How it works

```
Discover (auto) → Triage → Draft (auto) → Approve/Edit (you) → Post now | Schedule
```

```
config.yaml + .env
        │
        ▼
   rcopilot fetch / run ──► SQLite (posts, scores, drafts, jobs, audit)
        │
   rcopilot serve  ── JSON ──► Next.js review UI (web/)
        │
   you approve  ──► post now, or schedule for later
```

Nothing reaches Reddit until you approve it. Scheduling only delays an approved reply.

## Configuration

### `config.yaml`

```yaml
subreddits:
  - python
  - learnpython
listing: hot          # hot | new
fetch_limit: 25
db_path: rcopilot.db

accounts:
  - name: default
    user_agent: "reddit-copilot/1.0 by u/YOUR_USERNAME"

llm:
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini

rate_limits:
  min_interval_seconds: 120
  daily_cap: 10

voice:
  product: ""
  tone: ""
  persona: ""
  avoid: ""

discovery:
  keywords: []
  min_score: 0.25

worker:
  interval_seconds: 300

oauth_redirect_uri: http://127.0.0.1:8000/api/oauth/callback
frontend_url: http://localhost:3000
```

### `.env`

```bash
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_REFRESH_TOKEN=
LLM_API_KEY=
```

`REDDIT_REFRESH_TOKEN` is written automatically after **Connect Reddit**. Named accounts can use `REDDIT_<NAME>_CLIENT_ID` (and matching secret/refresh token).

Password grant (`REDDIT_USERNAME` / `REDDIT_PASSWORD`) still works as a fallback if you already have a script app.

### LLM providers

Set `llm.base_url` + `llm.model` + `LLM_API_KEY`:

| Provider   | `base_url` example              | Notes                |
|------------|----------------------------------|----------------------|
| OpenAI     | `https://api.openai.com/v1`      | default              |
| Groq       | `https://api.groq.com/openai/v1` | fast / cheap         |
| OpenRouter | `https://openrouter.ai/api/v1`   | many models          |
| Ollama     | `http://localhost:11434/v1`      | local; key can be any|

## CLI

```bash
rcopilot init
rcopilot fetch
rcopilot draft [--account NAME]
rcopilot serve [--port 8000] [--with-worker]
rcopilot run                 # discover + draft + due schedules, looping
rcopilot approve --id N
rcopilot reject --id N
rcopilot post [--id N]
```

`rcopilot review` is deprecated — use `serve` plus the Next.js app.

## Responsible use

- Always review drafts before posting.
- Respect each subreddit's rules and culture — don't spam or hard-sell.
- Keep rate limits conservative; Reddit may still rate-limit or restrict script apps.
- This tool does **not** use proxies, vote manipulation, or unattended auto-commenting.

## Migrating from Reddit-Karma-Bot (v0)

Removed on purpose:

- Auto-comment loops / karma farming
- Proxies and random user-agents
- Ad / spam posting modes
- `g4f` free-provider scraping
- Flask start/stop bot controls

The last pre-pivot code is tagged `v0-legacy` (once published). Prefer this `1.x` flow.

## Roadmap

See [PRODUCT.md](PRODUCT.md). Phase 1 is the review queue: intent discovery, auto-draft, human approve, schedule approved comments.

## License

MIT
