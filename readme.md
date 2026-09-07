<p align="center">
  <img src="assets/logo.svg" alt="Reddit Copilot" width="120" height="120" />
</p>

<h1 align="center">Reddit Copilot</h1>

<p align="center">
  <strong>Local-first Reddit engagement assistant</strong><br />
  Finds intent threads for a workspace you brief once. Drafts in that voice. Nothing posts without you.
</p>

<p align="center">
  <a href="https://github.com/meet447/Reddit-Copilot/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" /></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/ui-Next.js-black.svg" alt="Next.js" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/api-FastAPI-009688.svg" alt="FastAPI" /></a>
  <img src="https://img.shields.io/badge/status-early%20development-orange.svg" alt="Status: early development" />
  <a href="https://github.com/meet447/Reddit-Copilot/stargazers"><img src="https://img.shields.io/github/stars/meet447/Reddit-Copilot?style=social" alt="GitHub stars" /></a>
  <a href="https://github.com/meet447/Reddit-Copilot/issues"><img src="https://img.shields.io/github/issues/meet447/Reddit-Copilot" alt="GitHub issues" /></a>
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

> [!WARNING]
> **Early development.** Reddit Copilot is actively changing. Expect rough edges, breaking config/API changes, and incomplete features. Feedback and issues are welcome — production use is at your own risk.

Formerly **Reddit-Karma-Bot** — rebuilt as a **human-in-the-loop** copilot, not a karma farmer.

Python owns Reddit, the LLM, SQLite, and the worker. Next.js owns the review desk. Your OAuth tokens stay on your machine. Reddit sign-in and the LLM key are **account-level**; each **workspace** (product, personal, or custom) has its own briefing, communities, drafts, and queue.

## Features

- **Workspaces** — brief a product, yourself, or a custom aim; switch without mixing queues
- **Discover** — fetch and rank intent threads (questions, looking-for-tool, complaints, unanswered)
- **Review queue** — Add threads, stream a draft, edit, then **Post** or **Schedule**
- **Original posts** — write or generate a self-post, then post now or schedule
- **Outcomes** — poll posted comments for score, replies, and removals
- **Local-first** — SQLite + `.env`; no cloud required
- **OpenAI-compatible LLMs** — OpenAI, Groq, OpenRouter, or Ollama

## Quickstart (use the app)

Needs **Python 3.10+** and **Node.js 20+**.

```bash
git clone https://github.com/meet447/Reddit-Copilot.git
cd Reddit-Copilot
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

rcopilot init
rcopilot serve              # API :8000 + UI :3000 (runs npm install once if needed)
```

Open **http://localhost:3000** (not `127.0.0.1` — the Next.js app blocks that origin).

1. Create a Reddit **web** app at https://www.reddit.com/prefs/apps  
   Redirect URI must match exactly: `http://127.0.0.1:8000/api/oauth/callback`
2. Connect Reddit and an OpenAI-compatible LLM key
3. Pick a purpose (product / personal / custom), talk to the briefing agent, review communities
4. Fetch threads, add a few to the queue, draft, then **Post** or **Schedule**

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
Workspace briefing → Discover → Add / Skip → Draft / Edit → Post now | Schedule | Original post → Outcomes
```

```
config.yaml + .env
        │
        ▼
   rcopilot fetch / run ──► SQLite (workspaces, posts, scores, drafts, jobs, audit)
        │
   rcopilot serve  ── JSON ──► Next.js review UI (web/)
        │
   you Post / Schedule  ──► Reddit comment or self-post
```

Nothing reaches Reddit until you hit **Post** or **Schedule**. Scheduling only delays something you’ve already written.

## Configuration

You don’t need to edit config by hand for normal use. **Onboarding** (and later **Settings**) write:

- `config.yaml` — active workspace, subreddits, voice/briefing, discovery, LLM model/base URL, rate limits
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

See [PRODUCT.md](PRODUCT.md). Phase 1 is done. Next: draft variants and a weekly digest.

## License

[MIT](LICENSE) © Meet Sonawane
