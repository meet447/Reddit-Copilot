# Reddit Karma Farmer — Chrome Extension

Autonomous Chrome extension that builds Reddit karma by finding threads, drafting AI comments, and posting with human-like typing — all from your real browser session.

## Why a Chrome extension?

Compared to the old Python API bot, this approach:

- Uses your **real browser session** (residential IP + real cookies)
- Posts through Reddit's normal UI (harder to fingerprint as a datacenter bot)
- Supports **human-like typing** with randomized delays
- Enforces **safety limits** (daily caps, cooldowns, circuit breaker)
- Runs **autonomously** once enabled — no manual copy-paste

## Install (developer / unpacked)

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `extension/` folder from this repo
5. Pin the extension to your toolbar

## Setup

1. **Log into Reddit** in Chrome (reddit.com or old.reddit.com)
2. Click the extension icon → **Settings**
3. Add your **AI API key** (Groq recommended — free tier available at https://console.groq.com)
4. Configure target subreddits (defaults are low-risk discussion subs)
5. Click **Save settings**
6. Click **Enable** in the popup

The bot will then autonomously:

1. Pick a random allowed subreddit
2. Open `old.reddit.com/r/{sub}/new/` in a background tab
3. Select a random unvisited thread
4. Generate a context-aware AI comment
5. Type it character-by-character
6. Submit and schedule the next action with a random delay

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Max comments/day | 8 | Hard daily cap |
| Max per sub/day | 2 | Avoid spamming one community |
| Min/max delay | 8–22 min | Random pause between comments |
| Active hours | 8am–11pm | Only runs during your waking hours |
| Warmup mode | On | Friendly, non-promotional comments |
| Use old Reddit | On | More reliable DOM for posting |

## AI providers

| Provider | Default model | Get a key |
|----------|---------------|-----------|
| Groq | `llama-3.3-70b-versatile` | https://console.groq.com |
| OpenAI | `gpt-4o-mini` | https://platform.openai.com |
| OpenRouter | `google/gemini-2.0-flash-001` | https://openrouter.ai |

## Safety features

- Subreddit allow-list only (no `r/all`)
- Skips NSFW, locked, and stickied posts
- Comment gate detection (won't post if textarea is missing)
- Post-submit visibility check
- Circuit breaker after 3 consecutive critical failures
- Never comments on the same post twice
- Gaussian typing delays

## Tips for best karma results

1. Use an account **30+ days old** with **verified email**
2. Start with **warmup mode** for the first 1–2 weeks
3. Keep limits at **8 comments/day or fewer**
4. Target discussion subs: `CasualConversation`, `NoStupidQuestions`, `todayilearned`
5. Stay logged into Reddit while the extension runs
6. Don't run 24/7 — the active hours setting mimics human schedules

## Project structure

```
extension/
├── manifest.json
├── icons/
└── src/
    ├── background/service-worker.js   # Scheduler & orchestration
    ├── content/reddit.js              # DOM scanning & posting
    ├── popup/                         # Enable/disable UI
    ├── options/                       # Settings page
    └── shared/                        # AI, safety, storage
```

## Disclaimer

For educational purposes. Automated engagement may violate Reddit's Terms of Service. Use responsibly, respect subreddit rules, and never use this for spam or vote manipulation. Account suspension is always possible.
