# Guhan's RewardHub

A chore tracker and allowance-style motivation web app for kids. Track daily goals (Mon–Fri), **Weekly Pot** and **Guhan's Bank**, optional **Daily Schedule** blocks, and sync data to the cloud (Supabase) for use across devices.

> **Main app** (`index.html`) — Bank + Weekly Pot: weekday success/miss rules, Friday settlement to savings, **Monthly Pot** summary, **three main tabs** (Status · Today's Goals · Daily Schedule), and a **daily reminders** popup after load. **Legacy v1** (`index-v1.html`) uses a different model and cloud row (`GuhanApp` vs main app — see `APP_NAME` in `index.html`).

![Built with HTML, CSS, JavaScript, Supabase](https://img.shields.io/badge/Stack-HTML%20%7C%20CSS%20%7C%20JS%20%7C%20Supabase-0d9488)

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Setup & Deployment](#setup--deployment)
- [Usage](#usage)
- [Data Model](#data-model)
- [Project Structure](#project-structure)

---

## Features

### Navigation (main app)

- **Three tabs** — **Status** (pots, weekday progress, Activity Log in parent mode), **Today's Goals** (settings, goals, extras, chore management in parent mode), **Daily Schedule** (default template + per-day calendar).
- **Tab memory** — Last tab is restored for the session (`sessionStorage`: `rh_app_main_tab`).
- **Today's reminders** — After data loads, a modal can list **pending goals for today** and **schedule blocks still ahead** (Eastern Time). Shown only when there is something pending; **dismiss is remembered once per calendar day (ET)** via `localStorage` key `rh_daily_reminders_dismissed`.

### Child view

- **Today's Goals** — Chores for the current day (Sun–Sat per task schedule); check off with optional comment; toasts and celebrations when all weekday chores are done.
- **Status** — Weekly Pot, Guhan's Bank, weekday strip + motivation copy; Activity Log (parent).
- **Daily Schedule** — Scroll days; **By time** (grid) or **Activities** (list) on narrow screens; tap slots to add/edit blocks.
- **Extras** — Log optional custom chores (does not change Weekly Pot rules).
- **Past week** — Toggle to see recent days.
- **Rules** — Collapsible rules list. **Parent login** lives in the Rules footer; **← v1 (classic)** appears only in **Parent mode** (legacy app link).

### Parent mode (password protected)

- **Settings** — Weekly pot start, success bonus, miss penalty; Supabase status + test; change password.
- **Add / All chores** — Manage tasks and weekdays; **Override Past chores** editor; waive / undo (where allowed).
- **Default schedule** — Template time blocks per weekday; merges with kid-specific **Daily Schedule** overrides.
- **Activity Log** — On **Status** tab (parent only).
- **Guhan's Bank** — **Add / deduct + reason** (or double-click) when unlocked; amount + required note are logged to Activity Log.
- **Caution** — Reset all data (destructive).

### Main app — Bank & Weekly Pot (summary)

| Feature | Description |
|--------|-------------|
| **Guhan's Bank** | Permanent savings. Never resets. |
| **Weekly Pot** | Resets each **Monday** to configured start (e.g. $25). |
| **Mon–Fri** | All chores done → **+success** amount. Any open chore → **−miss** amount (preview applies in UI until day rolls over). |
| **Weekends** | Task-free for pot rules; schedule blocks can still apply. |
| **Friday settlement** | Weekly Pot transfers into Guhan's Bank; negative pot reduces Bank. |
| **Monthly Pot** | Running total of Friday transfers in the **current calendar month** (ET). |
| **UI** | **Plus Jakarta Sans**, glass-style shell, pill tab bar, responsive schedule. |

---

## Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client (Browser)                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  index.html (main) · index-v1.html (legacy)                  ││
│  │  • Single-file SPA (no build step)                           ││
│  │  • Vanilla JS + inline CSS                                   ││
│  │  • State held in memory (`state` object)                     ││
│  └─────────────────────────────────────────────────────────────┘│
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ HTTPS (Supabase JS Client)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Supabase (BaaS)                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Table: `chore_app_state`                                    ││
│  │  • `app_name` (PK): must match `APP_NAME` in `index.html`    ││
│  │  • `app_data` (JSONB): full state snapshot                   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Design decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Framework** | None (vanilla JS) | Minimal deps, static hosting |
| **State** | In-memory + `localStorage` + cloud | Survives refresh offline; cloud when configured |
| **Auth** | Client-side parent password | Stored in app state / config |
| **Styling** | Inline CSS + CSS variables | Self-contained |
| **Fonts** | Google Fonts (**Plus Jakarta Sans**) | Modern, readable UI |
| **Timezone** | `America/New_York` | Dates, “today”, reminders, rollover |

### Data flow

1. **Load** — `loadCloudData()` tries Supabase; on failure or empty row, restores from **`localStorage`** (`GuhanRewardHub_<APP_NAME>_v2`). Then `checkDailyLogic()` → `saveAction()` → `renderUI()`.
2. **User action** — Update `state` → `saveAction()` → `renderUI()` + **`localStorage`** + `syncToCloud()` when Supabase works.
3. **Daily logic** — On EST date change: persist yesterday’s completions, apply weekday pot adjustments, reset `completedToday` / `waivedToday` / custom extras as needed.
4. **Weekly / Friday** — Monday reset and Friday-to-Bank settlement are handled inside the same daily pipeline (see code: `checkDailyLogic`).

**Note:** `localStorage` is per browser/device; use Supabase (same `app_name` row) to share across devices.

---

## Configuration

### Environment / Supabase

Credentials live in `index.html`:

```javascript
const SUPABASE_URL = "https://….supabase.co";
const SUPABASE_KEY = "…"; // anon public (legacy `eyJ…` JWT if publishable key fails)
const APP_NAME = 'GuhanApp'; // row key in chore_app_state — keep in sync with your table
```

> Use the **anon public** key (**Settings → API**). If the app’s **Test connection** fails, try the **legacy anon** JWT.

> **RLS:** If enabled with no policy, requests fail. Example for a trusted family app:

```sql
CREATE POLICY "chore_app_state_anon_rw"
ON chore_app_state FOR ALL
TO anon
USING (true)
WITH CHECK (true);
```

### Required Supabase table

```sql
CREATE TABLE chore_app_state (
  app_name TEXT PRIMARY KEY,
  app_data JSONB DEFAULT '{}'
);

INSERT INTO chore_app_state (app_name, app_data)
VALUES ('GuhanApp', '{}');
```

Use the same `app_name` as `APP_NAME` in `index.html`. The app uses **`.maybeSingle()`** on load so an empty table does not error.

### Default parent settings (main app)

| Setting | Default | Description |
|---------|---------|-------------|
| `weeklyPotStart` | 25 | Weekly Pot after each Monday reset ($) |
| `dailySuccessAmount` | 5 | Bonus when all weekday chores done ($) |
| `dailyFailureAmount` | 5 | Penalty when any weekday chore open ($) |
| `parentPassword` | (see `DEFAULT_PARENT_PASS` in app) | Parent unlock |

Optional **`config.defaultSlots`** — per weekday (0–6) arrays of `{ start, end, text, preset? }` for the default schedule template.

### CSS theme (approximate)

```css
--primary: #0d9488;
--primary-dark: #0f766e;
--accent: #f97316;
--danger: #ef4444;
--success: #059669;
--text: #0f172a;
--text-muted: #64748b;
```

---

## Setup & Deployment

### Prerequisites

- Supabase project (optional but recommended for sync)
- Static hosting or a local HTTP server

### Local development

1. `git clone <repo-url> && cd gtaskmanager`
2. Create `chore_app_state` and align `app_name` with `APP_NAME`.
3. Set `SUPABASE_URL` / `SUPABASE_KEY` in `index.html` if needed.
4. Serve over HTTP (avoid `file://` for Supabase):

   ```bash
   python3 -m http.server 8000
   # or
   npx serve .
   ```

### Deployment

Ship `index.html` (and `guhan.png` if used). No build step.

### PWA (install / offline shell)

The main app includes **`manifest.webmanifest`** and **`sw.js`**:

- **HTTPS required** (or `localhost`) for the service worker.
- **Install**: Chrome/Edge (Android/desktop) can offer “Install app”; iOS: **Share → Add to Home Screen** (uses `apple-mobile-web-app-*` meta tags).
- **Offline**: Same-origin pages open from cache if you’ve visited while online; Supabase/CDN still need network.
- After changing precached files, **bump** `CACHE_NAME` in `sw.js` so clients pick up a fresh cache.

---

## Usage

### Child flow

1. Open the app — optional **Today's reminders** if something is pending (dismiss for the rest of the day).
2. Use **Status** for pots and progress; **Today's Goals** for chores; **Daily Schedule** for the day plan.
3. Complete a chore — checkbox → optional comment → Confirm.
4. **Rules** — Read how the pots work; parents use **Parent login** here.

### Parent flow

1. Open **Rules** → **Parent login** → password → **Exit Parent Mode** when done.
2. **Today's Goals** tab → **Settings** (amounts, cloud test, password).
3. Manage chores, default schedule, past chores, Activity Log, and Caution as needed.
4. **← v1 (classic)** appears under Rules only while in parent mode.

---

## Data model

### `state` object (main app, illustrative)

```javascript
{
  guhansBank: number,
  weeklyPot: number,
  tasks: [{ id: number, name: string, days: number[] }],  // 0=Sun … 6=Sat
  history: [{ date, timestamp, msg, amt, class }],
  lastCheck: string,                    // Last processed calendar day (en-US, ET)
  completedToday: number[],
  waivedToday: number[],
  customChoresToday: string[],
  config: {
    weeklyPotStart, dailySuccessAmount, dailyFailureAmount, parentPassword,
    defaultSlots?: { [dayNum] : [{ start, end, text, preset? }] }
  },
  dayCompletions: { "M/D/YYYY": { completed: [], waived: [] } },
  lastWeeklyReset: string | null,
  lastWeekSettlement: string | null,
  weeklyDeposits: { [weekKey]: number },
  reminderNotes: string,
  calendarBlocks: { "M/D/YYYY": [{ id, start, end, text }] }
}
```

Persisted as JSON in Supabase `app_data` and in `localStorage` under `GuhanRewardHub_<APP_NAME>_v2`.

---

## Project structure

```
gtaskmanager/
├── index.html           # Main app (Bank & Weekly Pot + schedule)
├── manifest.webmanifest # PWA manifest (install, theme, icons)
├── sw.js                # Service worker (offline cache for same-origin)
├── index-v1.html        # Legacy streak / monthly model
├── guhan.png            # Header + PWA icons (optional)
├── README.md
└── .git/
```

---

## License

Private/personal project. Use as desired.
