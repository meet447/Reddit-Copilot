# Reddit Copilot — Design System

**Status:** Final  
**Language:** Meuxe, tuned for an engagement desk — not a chat toy, not an enterprise console.

Reddit Copilot should feel like a **personal desk companion** for Reddit work: quiet, keyboard-first, warm enough to trust with your voice — never like a growth hacker dashboard or a tech demo.

Visual system = **Linear/Raycast utility** (structured rail, dense review, quiet chrome) + **Notion-style warmth** from the mascot and pastel tints — never from warm greys.

---

## Principles

1. **Neutral, low contrast.** Surfaces are neutral white and grey; text is neutral near-black (`ink`). Colour appears only as pastel tints for highlights, status, and the mascot. No saturated fills. Never put white text on a pastel.
2. **Soft geometry.** Generous radii everywhere. Buttons and inputs are pillow-like. Prefer squircle-capable containers where supported.
3. **Flat, not floating.** Nothing casts a drop shadow. Elevation = surface-colour shift + 1px hairline ring. Never stack border + ring + shadow + backdrop-blur.
4. **Negative space divides.** Sidebar/rail and main content are separated by canvas background and padding, not by heavy rules.
5. **Restrained iconography.** One stroke weight (1.6), round caps. No emoji as UI icons.
6. **Mascot as anchor.** The blob appears in the mark, empty states, and loading/thinking moments — “friendly, collaborative, non-threatening,” not “AI overlord.”
7. **Craft-hacker texture.** Optional stippled ASCII accent for empty states and panel headers (`ink-4` only). Not part of onboarding.
8. **Copy is human.** Sentence case. No uppercase-tracked micro-labels except tiny status pills. Prefer “Nothing posts until you say so” over “HUMAN-IN-THE-LOOP GATE.”

---

## Product tone (Reddit Copilot)

| Do | Don’t |
|----|--------|
| Desk companion for finding threads and shipping replies | Karma farm / bot control panel |
| “Review queue,” “Draft ready,” “Scheduled for later” | “Campaigns,” “Blast,” “Autopilot engaged” |
| Calm confidence about guardrails | Fearmongering or growth-hack hype |
| Keyboard shortcuts as first-class | Mouse-only dense tables |

The **review session is the hero surface.** Discovery and scheduling serve that session.

---

## Tokens

Tokens live in `web/src/index.css` (`@theme`). Primitives live in `web/src/components/ui/`. **Use them** — do not hand-roll colours, radii, shadows, or icons in feature components.

### Palette

| Token | Value / range | Use |
|-------|----------------|-----|
| `surface-2` | `#ffffff` | Raised: inputs on focus, hover, draft cards |
| `surface` | `#fcfcfc` | Default panel / card |
| `canvas` | `#f4f4f5` | App background behind panels |
| `well` / `well-2` | `#f0f0f2` / `#e6e6e9` | Sunken insets, resting inputs, rail |
| `line` / `line-2` | `#ebebee` / `#dcdce0` | Hairlines (sparingly) |
| `ink` → `ink-4` | `#1b1b1e` → `#bbbbc2` | Text: primary → placeholder |
| `accent-*` | pastel amber (`300` ≈ `#f3cd78`) | Highlights, selection rings, links, mascot, selected thread tint |
| `peach-*` | pastel rose | Soft secondary highlights |
| `honey-*` | pastel lemon | In progress / needs attention (pending drafts, scheduled waiting) |
| `sage-*` | pastel mint | Ready / success (approved, posted) |
| `clay-*` | pastel coral | Destructive / errors (reject, failed post) |

**Primary actions** use `bg-ink text-white` — not pastel fills with white text.

Disable the default Tailwind palette (`--color-*: initial`). Before merge, grep for `slate|blue|indigo|violet|gray|emerald|red-` — those classes will silently render nothing.

### Radii

| Token | Size | Use |
|-------|------|-----|
| `rounded-control` / `rounded-field` | 12px | Buttons, inputs, pills |
| `rounded-card` | 16px | Draft cards, choice tiles |
| `rounded-panel` | 20px | Main stage, queue panel |
| `rounded-sheet` | 24px | Settings / modal sheets |
| `rounded-full` | pill | Composer-like filters, search field |

Add squircle / `corner-shape` on containers where supported.

### Elevation

| Token | Meaning |
|-------|---------|
| `shadow-soft` | Neutral ring ~0.07 alpha — white card on white |
| `shadow-float` | Neutral ring ~0.09 alpha — resting raised controls |
| `shadow-pop` | One very faint blur — overlays only (modals/popovers on scrim) |

No drop shadows on cards, sidebar, or queue rows.

### Type

| Role | Spec |
|------|------|
| UI font | **Figtree** — headings 600–700, tracking-tight, line-height 1.2; body 400–500, 14–15px, relaxed |
| Mono | **JetBrains Mono** — paths, post IDs, API/tool args, ASCII accent |
| Page title | 22–26px |
| Section | 15–16px semibold |
| Body | 14–15px |
| Meta | 12–13px `ink-3` |
| Pills | 11px |

---

## Layout

### App shell

- **Canvas** background with **12px** padding.
- **64px icon rail** on the left:
  - Top: MeuxeMark / Copilot mark, then workspace switcher
  - Middle: Queue, Discover, Posts, Schedule, Activity
  - Bottom: Settings
- **Main stage:** `rounded-panel` `surface` card filling the rest — this is the active workspace (queue, draft detail, calendar).
- **Context dock (optional):** on draft detail, a second panel to the right for thread context (post body + top comments) — a docked panel, **not** an overlay.
- Rail and stage separated by canvas + padding, not a vertical rule.

### Review queue (primary screen)

- Filter chips (Pending / Approved / Scheduled / Posted / Error) as soft pills — sentence case.
- List of draft cards: subreddit meta, title, truncated draft, status pill, relative time.
- Dense but breathable; keyboard focus ring uses soft `accent` — never a harsh blue.
- Empty state: mascot + AsciiAccent + one human line (“Nothing to review yet. Add threads from Discover.”).

### Draft detail

- Left/main: editable draft textarea (well → surface-2 on focus, soft accent ring).
- Actions: **Approve** (ink primary), **Reject** (danger-soft), **pick an angle** (not regenerate-roulette), **Post now** / **Schedule** (secondary or primary when approved).
- Right dock: thread title (link), selftext, top comments in a well.
- Keybindings visible as `<Kbd>` / `<KeyCombo>` (e.g. `A` approve, `R` reject, `E` focus editor, `S` schedule).

### Discover

- Intent filters (All / Question / Looking for tool / Unanswered / Complaint) as soft chips.
- Fetch threads is a header action. Keep the list while it runs. Show **skeleton cards** that drop away as real threads land; compact fetching notice. Never swap to empty-state copy mid-fetch.
- Results: Add / Skip — same card language as the queue.
- No alert-inbox aesthetics (we are not Syften).

### Posts

- Generate ideas is a header action. Same stream pattern as Discover: skeleton cards fill in as each self-post draft finishes. Existing drafts stay visible.

### Schedule

- Calendar or day list inside the stage panel.
- Scheduled items show honey pill (“Scheduled”) until posted (sage) or failed (clay).
- Editing time uses the same Field primitives.

### Settings sheet

- Centred **sheet** (`rounded-sheet`, `shadow-pop` on scrim).
- Own left nav: Accounts, Voice, Subreddits & discovery, Rate limits, LLM, About.
- Voice / discovery copy is **purpose-aware** for the active workspace (product vs personal vs custom).
- Forms use Field / Label / Input / Hint / FieldError — inputs rest in well, lift on focus.
- Links: redo briefing (`/onboarding?briefing=1`), new workspace (`/onboarding?new=1`).

### Onboarding

- Centred single-column on `bg-surface`.
- Thin top bar: mark + progress dots (account steps skip when Reddit + LLM are already connected).
- Mascot, meta, heading, subtitle centred; content max **560px**. Interview chat max **640px**, stretches to fill.
- Footer: ghost **Back** / **Cancel** left, ink **Continue** / **Finish** right. **No primary button on the interview step** — the agent advances when it has enough context.
- Steps: Reddit app → Connect Reddit → LLM → purpose (product / personal / custom) → briefing chat → review workspace → first fetch.
- Loading: `PageStatus` with searching mascot + matching copy. Refresh restores interview or review from `setup_step`.

---

## Status mapping (Reddit Copilot)

| State | Pill tone | Notes |
|-------|-----------|--------|
| Pending | `honey` | Needs review |
| Approved | `sage` | Ready to post or schedule |
| Scheduled | `honey` or soft `accent` | Waiting for `run_at` |
| Posted | `sage` | Done; link to permalink |
| Rejected | `ink-3` / muted | Quiet dismissal |
| Error | `clay` | Failed draft or failed post |

Pills: 11px, optional dot/pulse for in-progress worker (“Discovering…”, “Drafting…”).

---

## Primitives (`web/src/components/ui`)

| Component | Notes |
|-----------|--------|
| `Button` | primary ink, secondary raised, soft tinted, ghost, danger, danger-soft; sm/md/lg; leading/trailing/loading |
| `IconButton` | square; accessible label required; active state |
| `Surface` | tones surface/raised/well/canvas; radius control→sheet; elevation none/soft/float/pop; interactive |
| `Field`, `Label`, `Input`, `Textarea`, `Select`, `Hint`, `FieldError` | well rest → surface-2 focus + soft accent ring |
| `ChoiceCard` | selectable tile; selected check `bg-ink` |
| `Pill` | status chips; tones map to palette |
| `Notice` | soft callout, no border (e.g. rate-limit tip) |
| `Mascot`, `MeuxeMark` | moods: neutral/happy/thinking/sleepy/surprised; `talking` / `searching`; mark = pale amber (`accent-100`) squircle + warm mascot |
| `PageStatus` | loading vs empty; mascot + human line + dots while fetching |
| `AsciiAccent` | stippled strip; empty states / panel headers only |
| `Dots` | thinking indicator while drafting or page loading |
| `StreamCardSkeleton` | Discover / Posts card placeholders while SSE fills the list |
| `Kbd`, `KeyCombo` | keycaps for review shortcuts |
| `icons.tsx` | sole icon set |

Feature screens compose these only — no one-off colours or radii.

---

## Motion

Short and soft (≤350ms, `--ease-soft`):

- `animate-fade-in`, `animate-rise-in`, `animate-pop-in` for panels and cards
- Ambient: `animate-breathe`, `animate-blink` on mascot; `animate-dot` while drafting; `animate-bone` on stream skeletons
- Respect `motion-safe:` / reduced motion

No bounce-heavy “AI magic” animations on post success — a soft rise-in + sage pill is enough.

---

## Iconography & mark

- Stroke icons only from `ui/icons.tsx` (1.6 weight, round caps).
- App mark: Meuxe-style amber tile + cream mascot blob, tuned as **Reddit Copilot** (same geometry; product name in wordmark beside mark in marketing/README only — in-app rail uses mark alone).
- If shipping desktop later: master SVG full-bleed, no baked corner radius/margin/shadow; regenerate platform icons via script — never hand-edit PNGs.

---

## Copy snippets (canonical)

| Place | Copy |
|-------|------|
| Empty queue | “Nothing to review yet. Add threads from Discover.” |
| Discover loading | “Fetching threads from your communities…” / “Found N so far…” |
| Posts generating | “Drafting posts for your communities…” / “Drafted N so far…” |
| Guardrail notice | “Nothing posts until you approve it.” |
| After approve | “Ready when you are — post now or schedule.” |
| Worker drafting | “Drafting in your voice…” |
| Post success | “Posted. Nice work.” |
| Schedule set | “Queued for later. You can still edit or cancel.” |
| Error | “That didn’t go through. Check the note and try again.” |

---

## Anti-patterns

- Purple/indigo AI gradients, glow, glassmorphism stacks
- White text on pastel buttons
- Dense enterprise tables with uppercase column headers
- Emoji status icons
- “Autopilot,” “blast,” “farm,” “dominate Reddit”
- Drop shadows on every card
- Default Tailwind `slate` / `blue` / `gray` classes

---

## Implementation checklist

- [x] `web/src/index.css` — `@theme` tokens (palette, radii, shadows, fonts, motion)
- [x] `web/src/components/ui/` — primitives listed above
- [x] App shell: canvas + 64px rail + rounded-panel stage
- [x] Queue + draft detail + keyboard shortcuts
- [x] Mascot empty/loading states
- [ ] Grep gate: no `slate|blue|indigo|violet|gray|emerald|red-` in `web/`

**Stack fit:** Next.js App Router in `web/` consumes the FastAPI JSON API; all visual rules in this file apply to that app only — CLI remains unstyled text.
