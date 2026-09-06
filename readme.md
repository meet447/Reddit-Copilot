<p align="center">
  <img src="assets/logo.svg" alt="Reddit Copilot" width="120" height="120" />
</p>

<h1 align="center">Reddit Copilot</h1>

<p align="center">
  <strong>Local-first Reddit engagement assistant</strong><br />
  Finds intent threads. Drafts replies in your voice. Nothing posts without you.
</p>

<p align="center">
  <a href="https://github.com/meet447/Reddit-Karma-Bot/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" /></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/ui-Next.js-black.svg" alt="Next.js" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/api-FastAPI-009688.svg" alt="FastAPI" /></a>
  <a href="https://github.com/meet447/Reddit-Karma-Bot/stargazers"><img src="https://img.shields.io/github/stars/meet447/Reddit-Karma-Bot?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/meet447/Reddit-Karma-Bot/issues"><img src="https://img.shields.io/github/issues/meet447/Reddit-Karma-Bot" alt="GitHub issues" /></a>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#configuration">Configuration</a> ·
  <a href="#cli">CLI</a> ·
  <a href="#contributing">Contributing</a> ·
  <a href="#license">License</a>
</p>

---

Formerly **Reddit-Karma-Bot** — rebuilt as a **human-in-the-loop** copilot, not a karma farmer.

Python owns Reddit, the LLM, SQLite, and the worker. Next.js owns the review desk. Your OAuth tokens stay on your machine.

## Features

- **Discover** — fetch and rank intent threads (questions, looking-for-tool, complaints, unanswered)
- **Review queue** — Add threads, stream a draft in your voice, edit, then **Post** or **Schedule**
- **Outcomes** — poll posted comments for score, replies, and removals
- **Local-first** — SQLite + `.env`; no cloud required
- **OpenAI-compatible LLMs** — OpenAI, Groq, OpenRouter, or Ollama

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
rcopilot post      # publish ready drafts
```

## How it works

```
Discover → Add / Skip → Draft / Edit → Post now | Schedule → Outcomes
```

```
config.yaml + .env
        │
        ▼
   rcopilot fetch / run ──► SQLite (posts, scores, drafts, jobs, audit)
        │
   rcopilot serve  ── JSON ──► Next.js review UI (web/)
        │
   you Post / Schedule  ──► Reddit comment (with outcome polling later)
```

Nothing reaches Reddit until you hit **Post** or **Schedule**. Scheduling only delays a reply you’ve already written.

## Configuration

### `config.yaml`

```yaml
subreddits:
  - python
  - learnpython
listing: new          # new | hot — new is better for unanswered questions
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
  # search_queries filled on fetch from the product blurb (LLM) or keywords

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

## Project layout

```
rcopilot/     # FastAPI, PRAW, LLM, SQLite, worker
web/          # Next.js review desk
tests/        # pytest
PRODUCT.md    # product plan / roadmap
DESIGN.md     # UI design system
```

## Responsible use

- Always review drafts before posting.
- Respect each subreddit’s rules and culture — don’t spam or hard-sell.
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

## Contributing

Issues and PRs are welcome. For larger changes, open an issue first so we can align on scope.

```bash
pip install -e ".[dev]"
pytest
cd web && npm install && npm run lint
```

## Roadmap

See [PRODUCT.md](PRODUCT.md). Current focus: intent discovery, review desk, outcomes, and safe scheduling.

## License

[MIT](LICENSE) © Meet Sonawane
