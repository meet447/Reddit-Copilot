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
  <a href="#quickstart-use-the-app">Quickstart</a> ·
  <a href="#quickstart-develop">Develop</a> ·
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

## Quickstart (use the app)

Needs **Python 3.10+** and **Node.js 20+**.

```bash
git clone https://github.com/meet447/Reddit-Karma-Bot.git
cd Reddit-Karma-Bot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

rcopilot init
rcopilot serve              # API :8000 + UI :3000 (runs npm install once if needed)
```

Open http://127.0.0.1:3000 and finish **onboarding** (Reddit web app, Connect Reddit, product voice, subreddits, LLM).

Create the Reddit app at https://www.reddit.com/prefs/apps with redirect URI:

`http://127.0.0.1:8000/api/oauth/callback`

Optional: `rcopilot serve --with-worker` to keep discovery/schedules running in the background.

## Quickstart (develop)

Run API and UI in separate terminals when you’re iterating on the frontend:

```bash
# Terminal 1 — API only
rcopilot serve --api-only
# rcopilot serve --api-only --with-worker

# Terminal 2 — Next.js
cd web && npm install && npm run dev
```

Or drive the pipeline from the CLI after setup:

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

You don’t need to edit config by hand for normal use. **Onboarding** (and later **Settings**) write:

- `config.yaml` — subreddits, voice, discovery, LLM model/base URL, rate limits
- `.env` — Reddit client id/secret, refresh token after Connect Reddit, LLM API key

Advanced defaults and a full example live in [`config.example.yaml`](config.example.yaml). Named accounts can use `REDDIT_<NAME>_CLIENT_ID` (and matching secret/refresh token). Password grant (`REDDIT_USERNAME` / `REDDIT_PASSWORD`) still works as a fallback for script apps.

### LLM providers

Pick any OpenAI-compatible endpoint in onboarding/Settings (`base_url` + model + API key):

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
rcopilot serve [--port 8000] [--ui-port 3000] [--api-only] [--with-worker]
rcopilot run                 # discover + draft + due schedules, looping
rcopilot approve --id N
rcopilot reject --id N
rcopilot post [--id N]
```

`rcopilot serve` starts the API and Next.js UI together. Use `--api-only` when developing the frontend separately.

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
