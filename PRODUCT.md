# Reddit Copilot — Product Plan

**Status:** Final  
**Product:** Open-source, local-first Reddit engagement assistant  
**Later:** Optional hosted cloud service

---

## Vision

For indie founders, developer advocates, and small marketers who know Reddit is where their users hang out — but can’t spend hours browsing threads, and won’t run a spam bot that gets them banned.

**Job to be done:** Continuously find threads where people want (or need) what you offer → draft replies in your voice → you approve in minutes → post now or schedule safely.

**Why now:** GummySearch is gone (thread/intent discovery vacuum), Reddit’s API is tighter, LLMs are good enough that your job is judgment not typing — and local OSS with *your* Reddit OAuth tokens is one of the few lanes Reddit still leaves open.

---

## Positioning

**One-liner:** It finds threads and drafts replies while you sleep. You approve in 10 minutes. Nothing posts without you.

**Category:** Human-in-the-loop Reddit engagement assistant — with an autonomous discovery + draft pipeline (open source, local-first).

**Feels like:** A background agent (Polsia-style “it keeps working”).  
**Behaves like:** A copilot — human gate on every publish.

**Not this:**

- Not a karma bot
- Not a brand-alert / social-listening SaaS (Syften)
- Not fully autonomous “AI posts for you” with no approvals (Polsia / Growvia / Blitz)
- Not a multi-platform AI social team
- Not a generic content calendar (Postpone’s lane) — scheduling is for *already-approved* Reddit replies/posts

---

## Market scope

| Need | Decision | How it shows up |
|------|----------|-----------------|
| **1. Find threads where people want my product** | **Build** | Intent discovery, keyword/topic filters, question radar → triage into the queue |
| **2. AI drafts replies, human posts** | **Build (core)** | Auto-draft into queue → edit/approve → post; nothing ships without a human |
| **3. Keyword / brand alerts** | **Skip** | No always-on “ping me forever” monitoring inbox — leave that to Syften |
| **4. Schedule Reddit posts** | **Build** | Schedule **approved** comments (and later posts) — schedule delays an approved action, it does not replace approval |

**Autonomy we steal from Polsia (safe):**

- Always-on **discover**
- Always-on **draft** into the review queue
- **Weekly digest** of what was found / drafted / posted / how it performed

**Autonomy we refuse:**

- Auto-posting comments or posts without per-item human approval
- “Reply to everything” / engagement farming

---

## Personas

| Persona | Goal | Pain | Success |
|--------|------|------|---------|
| **Maya** — indie SaaS founder | 3–5 helpful comments/week in niche + founder subs | Opens Reddit “for 10 min,” loses an hour; can’t find buying-intent threads | Pipeline fills itself; 15-min weekly review → 5 posts she’s proud of; some become DMs/signups; approved replies scheduled for peak hours |
| **Dev** — developer advocate | Be the helpful expert without sounding corporate | Closed $49/mo tools store Reddit creds on someone else’s server | Runs locally, voice matches him, audit log for his manager |
| **Priya** — solo marketer (2 clients) | Find intent threads per client, reply from the right account, prove value | Account switching + no tracking + posting at bad times | Per-account queues, scheduled sends, monthly outcomes export |

---

## Core loop

```
Discover (auto) → Triage → Draft (auto) → Approve/Edit (human) → Post now | Schedule → Learn → Digest
```

Users live in the **review queue**, not on reddit.com.

1. **Discover (autonomous)** — continuously pull threads that match product/intent signals (subs, keywords, unanswered questions).
2. **Triage** — rank and hide noise.
3. **Draft (autonomous)** — keep the queue filled with replies in the user’s voice.
4. **Approve/Edit (human)** — the only hard gate before anything reaches Reddit.
5. **Post now or schedule** — only approved items; scheduler is a delay, not autopilot.
6. **Learn + digest** — outcomes improve discovery/drafts; weekly summary pulls the user back.

---

## Feature map

### P0 — Revival (OSS v1)

| Feature | Pillar | Why it matters |
|--------|--------|----------------|
| **Intent / keyword thread discovery** | 1 | Find threads where people ask for problems your product solves (GummySearch gap) |
| **Autonomous fetch + draft pipeline** | 1–2 | Background loop fills the queue — Polsia “it runs” feel without auto-post |
| **Relevance scoring & triage** | 1 | Rank by fit; hide noise so review is fast |
| **Voice / persona config** | 2 | “Describe your product + tone once” — generic LLM comments get downvoted |
| **One-keystroke review UI** | 2 | Approve / edit / reject / regenerate; review session *is* the product |
| **Safe posting guardrails** | 2 | Rate limits, cooldowns, no double-reply, allowlists |
| **Schedule approved comments** | 4 | Queue an *approved* reply for a future time |
| **Audit log** | 2 | Every draft, edit, post, schedule event in SQLite |
| **5-minute onboarding** | 2 | `rcopilot init` works cold on a fresh machine |

### P1 — Differentiate (OSS v1.x)

| Feature | Pillar | Why |
|--------|--------|-----|
| **Question radar** | 1 | Unanswered questions = highest-value intent threads |
| **Buying-intent / problem labels** | 1 | Tag threads (question, complaint, looking-for-tool) for fast scan |
| **Outcome tracking** | 2 | Upvotes / replies / removals → “this worked” |
| **Draft variants** | 2 | 2–3 angles per thread; pick instead of rewrite |
| **Weekly digest** | 2 | Found / drafted / posted / outcomes (Slack/email webhook) — not brand alerts |
| **Schedule approved posts** | 4 | Same approve-then-schedule flow for original posts |
| **Best-time suggestions** | 4 | Simple local heuristics for sub activity windows |
| **Local LLM (Ollama)** | 2 | Private, free drafting |
| **Multi-account routing** | 2 | Per-account subs, voice, queues, schedules |

### P2 — Compound (OSS v2)

| Feature | Pillar | Why |
|--------|--------|-----|
| **Saved discovery searches** | 1 | Reusable “find threads like this” per product/client |
| **Reply follow-ups** | 2 | Draft follow-ups when someone replies to you (still human-approved) |
| **Draft memory** | 2 | Learn from edits/rejections over time |
| **Export & reporting** | 2 | Client / team reports |
| **Calendar view for schedule** | 4 | See what’s queued by day/account |
| **Plugin hooks** | 1–2 | Custom scorers / discovery in Python |

### P3 — Cloud (later)

| Feature | Why people pay |
|--------|----------------|
| Hosted always-on discover + draft + schedule runner | Laptop off; pipeline and schedules still run |
| Mobile-friendly approval | 10-minute review from phone |
| Team review / roles | Agencies & DevRel |
| Cross-account analytics | Aggregated insight |
| Managed LLM | No API key setup |
| Compliance / audit exports | Regulated teams |

Same loop. Human still approves every publish. Cloud hosts the worker, not the judgment.

---

## Explicit non-goals

- Never post, upvote, or DM without per-item human approval
- No vote manipulation, proxies, account rotation, fingerprint evasion
- No “reply to everything,” no karma targets
- No scraping outside the official API / no reselling user data
- **No keyword / brand-alert product** (Syften’s lane)
- No Twitter/LinkedIn/multi-network “AI social team” (Polsia’s lane)
- Scheduling is Reddit-first and engagement-first — not a multi-network content calendar

---

## Success metrics

### OSS

- ~500 stars by end of Phase 3
- Clone → first posted **or scheduled** comment ≥ 20%
- Weekly active users (opt-in): 100 by v1.x
- ≥ 3 approved drafts / active user / week
- Approval rate ≥ 40% (below that, discovery/drafting is broken)
- Rising share of posts from intent-matched threads
- Zero reported bans from guardrail-compliant use

### Cloud (later)

- Waitlist from OSS users
- Trial → paid ≥ 5%
- 90-day retention ≥ 60%

---

## Roadmap

| Phase | Weeks | Focus | Exit criteria |
|-------|-------|--------|----------------|
| **1 — Revival** | 1–4 | P0: auto discover + auto draft + HITL review + schedule approved comments + docs/demo | Cold quickstart works; 10 external users posted or scheduled via the tool; Show HN / r/SideProject |
| **2 — Differentiate** | 5–10 | Question radar, intent labels, outcomes, variants, digest, schedule posts, Ollama | ≥40% approval rate; 50 WAU; 3 “switched from X” notes |
| **3 — Compound** | 11–18 | Saved searches, follow-ups, memory, calendar, plugins, export | 100 WAU; community PRs; cloud waitlist ≥200 |
| **4 — Cloud alpha** | 19–28 | Hosted discover/draft/schedule runner + mobile approve; paid from day one | 20 paying users; no ToS incidents; decide continue vs OSS-only |

---

## Tech stack

**Principle:** Python owns Reddit, LLM, storage, and workers. **Next.js** owns the review UI (OSS and cloud). One frontend stack end-to-end — no Flask UI.

### Phase 1–2 (OSS — locked)

| Layer | Choice | Why |
|-------|--------|-----|
| Backend language | **Python 3.10+** | PRAW ecosystem; pipeline + worker stay here |
| Package / CLI | **`rcopilot`** via `pyproject.toml` | `fetch` / `draft` / `run` / `post` / `serve` |
| HTTP API | **FastAPI** | JSON API for the Next app; replaces Flask UI routes |
| Reddit API | **PRAW** + web-app OAuth (refresh token) | Browser Connect Reddit; no password; local `.env` |
| LLM | **OpenAI-compatible HTTP** (`openai` SDK) | OpenAI / Groq / OpenRouter / **Ollama** via `base_url` |
| Storage | **SQLite** | Zero ops; posts, drafts, audit, schedule queue |
| Config | **`config.yaml` + `.env`** | Non-secrets vs secrets; gitignore-safe |
| Frontend | **Next.js (App Router) + TypeScript** | Review queue, keyboard shortcuts, schedule calendar — same UI path as cloud |
| Autonomy worker | **CLI daemon** (`rcopilot run`) or cron | Discover + draft loop; can share process with API |
| Scheduler | **SQLite due jobs + worker tick** | Approved items with `run_at`; no Celery yet |
| Local DX | `rcopilot serve` starts API; `npm run dev` in `web/` for UI (or a small compose script) | Two processes is fine for OSS |

**Repo layout (target):**

```
rcopilot/          # Python: pipeline, store, PRAW, LLM, FastAPI
web/               # Next.js review app
```

**Explicitly not for Phase 1:** Flask templates, Postgres, Redis/Celery, multi-platform OAuth, Electron, rewriting Reddit/LLM logic in Node.

### Phase 3 (OSS compound)

| Add | When |
|-----|------|
| Optional **Postgres** | Only if SQLite becomes a real limit for power users |
| **Plugin hooks** (Python entry points) | Custom scorers / discovery |
| Webhook digest | Slack/Discord from the Python worker |
| Next.js polish | Calendar view, denser keyboard review, mobile layout |

### Phase 4 (Cloud)

| Layer | Choice | Why |
|-------|--------|-----|
| API | Same **FastAPI** core | Don’t fork business logic |
| DB | **Postgres** | Multi-tenant |
| Jobs | **Redis + worker** (RQ/Arq/Celery) or managed queue | Always-on discover/draft/schedule |
| Auth | User accounts + **BYO Reddit credentials** first | Survive without commercial Reddit API |
| Frontend | Same **Next.js** app, hosted | Mobile-friendly approve; team features |
| LLM | BYO key + optional managed key | Onboarding for non-devs |

### Architecture sketch

```
┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│ CLI / worker │────▶│  pipeline    │────▶│  SQLite     │
│ rcopilot run │     │  discover    │     │  posts      │
└──────────────┘     │  draft       │     │  drafts     │
                     │  post/sched  │     │  jobs/audit │
┌──────────────┐     └──────┬───────┘     └──────▲──────┘
│ Next.js web/ │            │                    │
│ review UI    │──── JSON ──┤                    │
└──────────────┘            │                    │
                     ┌──────▼───────┐     ┌──────┴──────┐
                     │  FastAPI     │     │  PRAW + LLM │
                     │  /api/*      │     └─────────────┘
                     └──────────────┘
```

**Cloud later:** same API + Next app; swap SQLite→Postgres and local worker→hosted worker.

### Stack decision (locked)

- **Backend:** Python + FastAPI + PRAW + SQLite + OpenAI-compatible LLM + background worker  
- **Frontend:** **Next.js + TypeScript** (OSS review UI from day one)  
- **Not:** Flask UI; not a Node rewrite of Reddit/LLM core

---

## Open decisions (non-blocking for Phase 1)

1. **Name** — keep *Reddit Copilot*, or rename before launch?
2. **License** — MIT (max adoption) vs AGPL (harder for someone else to host a clone)?
3. **Telemetry** — opt-in anonymous usage in OSS, or fly blind on stars/issues?
4. **Cloud API** — at Phase 4, apply for commercial Reddit API, or stay BYO-credentials forever?
5. **Dogfood** — use it on a real account and publish outcomes as launch proof?

---

## Final recommendation (locked)

Ship **Phase 1 around Maya**:

1. **Autonomous discover** of intent threads  
2. **Autonomous draft** into a review queue  
3. **Human approve** → **post now or schedule**  

Skip brand alerts. Skip full autonomous posting.

**Product in one sentence:** An autonomous Reddit engagement pipeline with a human publish gate.
