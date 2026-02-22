# Guhan's RewardHub

A chore tracker and allowance management web app for kids. Track daily chores, earn streaks, and manage allowance with bonuses and penalties. Data syncs to the cloud for access across devices.

![Built with HTML, CSS, JavaScript, Supabase](https://img.shields.io/badge/Stack-HTML%20%7C%20CSS%20%7C%20JS%20%7C%20Supabase-0891b2)

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

### Child View

- **Today's Goals** — Chores scheduled for the current day with check-off
- **Allowance Pot** — Real-time balance with streak bonus display
- **Streak System** — Consecutive full completion days earn bonus (configurable)
- **Custom Chores** — Log extra chores (optional, no allowance impact)
- **Past Week** — View completion status for the last 7 days
- **Past Months** — See saved allowance from previous months
- **Reminder Notes** — Full-width open text area to write anything to remind yourself later (auto-saved, synced to cloud)
- **Rules** — Collapsible panel explaining how the system works

### Parent Mode (Password Protected)

- **Settings** — Configure starting allowance, streak days, bonus/penalty amounts
- **Add/Edit/Delete Chores** — Manage chore list with day-of-week schedules (M–S)
- **Activity Log** — View recent activity (completions, bonuses, penalties)
- **Waive Chores** — Excuse a chore without penalty when needed
- **Undo Completions** — Correct mistaken check-offs
- **Past Chores Editor** — Edit completion status for past days (recalculates allowance)
- **Manual Pot Adjustment** — Double-click pot value to adjust (parent mode only)
- **Change Password** — Update parent password
- **Reset All Data** — Clear chores, history, and reset pot (destructive)

---

## Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client (Browser)                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  index.html                                                  ││
│  │  • Single-file SPA (no build step)                           ││
│  │  • Vanilla JS + inline CSS                                   ││
│  │  • State held in memory (state object)                       ││
│  └─────────────────────────────────────────────────────────────┘│
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ HTTPS (Supabase JS Client)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Supabase (BaaS)                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Table: chore_app_state                                      ││
│  │  • app_name (PK): 'GuhanApp'                                 ││
│  │  • app_data (JSONB): full state snapshot                     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Design Decisions

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| **Framework** | None (vanilla JS) | Minimal deps, fast load, easy to host as static HTML |
| **State** | In-memory + cloud sync | Single source of truth in `state` object; persisted on changes |
| **Auth** | Client-side password | Parent mode protected by password (stored in app state) |
| **Styling** | Inline CSS + custom properties | Self-contained, no external stylesheet |
| **Fonts** | Google Fonts (DM Sans) | Clean, readable typography |

### Data Flow

1. **Load** — `loadCloudData()` fetches from Supabase → merges into `state` → `checkDailyLogic()` → `renderUI()`
2. **User Action** — Handler updates `state` → `saveAction()` → `renderUI()` + `syncToCloud()`
3. **Daily Logic** — On date change: persist yesterday's completions, apply bonus/penalty, reset `completedToday`/`waivedToday`
4. **Monthly Reset** — On month change: save current pot to `monthlyPots[lastMonth]`, reset pot to `startingAllowance`, clear streak

---

## Configuration

### Environment / Supabase

The app uses hardcoded Supabase credentials in `index.html`:

```javascript
const SUPABASE_URL = "https://urfpiauvuusibgzeyjjf.supabase.co";
const SUPABASE_KEY = "sb_publishable_pt2FCjNMufUil0txOXXSaw_KgY7kcyr";
```

> ⚠️ **Security note:** The publishable key is intended for client-side use. For production, consider Row Level Security (RLS) on the Supabase table to restrict access.

### Required Supabase Table

Create a table `chore_app_state`:

```sql
CREATE TABLE chore_app_state (
  app_name TEXT PRIMARY KEY,
  app_data JSONB DEFAULT '{}'
);

-- Insert initial row for GuhanApp
INSERT INTO chore_app_state (app_name, app_data)
VALUES ('GuhanApp', '{}');
```

### Default App Config (Parent Settings)

| Setting | Default | Description |
|---------|---------|-------------|
| `startingAllowance` | 150 | Allowance at start of each month ($) |
| `streakDaysForBonus` | 5 | Consecutive days required for bonus |
| `bonusAmount` | 5 | Bonus when streak reached ($) |
| `penaltyAmount` | 5 | Penalty when chores missed ($) |
| `parentPassword` | Admin123+ | Password for parent mode |

### CSS Variables (Theme)

```css
--primary: #0891b2;      /* Cyan/teal */
--primary-bright: #22d3ee;
--accent: #f59e0b;       /* Amber */
--accent-soft: #fef3c7;
--danger: #ef4444;
--success: #10b981;
--warning: #f59e0b;
--text: #0f172a;
--text-muted: #64748b;
```

### Timezone

Uses `America/New_York` for date/timestamp display. Change in `nowStr()` and `todayDate` if needed.

---

## Setup & Deployment

### Prerequisites

- A Supabase project
- Static file hosting (any) or local file server

### Local Development

1. Clone the repo:
   ```bash
   git clone <repo-url>
   cd gtaskmanager
   ```

2. Create the `chore_app_state` table in Supabase (see [Required Supabase Table](#required-supabase-table)).

3. Update `SUPABASE_URL` and `SUPABASE_KEY` in `index.html` if using your own project.

4. Serve `index.html`:
   ```bash
   # Python 3
   python3 -m http.server 8000

   # Node (npx)
   npx serve .

   # Open directly (CORS may block Supabase from file://)
   open index.html
   ```

5. Open `http://localhost:8000` (or your serve URL).

### Deployment

Deploy `index.html` and `guhan.png` to any static host:

- **Netlify** — Drag & drop or connect repo
- **Vercel** — `vercel` CLI or GitHub integration
- **GitHub Pages** — Push to `gh-pages` branch or use Actions
- **Supabase Storage** — Upload as static site (with redirect rules if SPA)

No build step required.

---

## Usage

### Child Flow

1. Open the app → see today's chores and allowance pot.
2. Complete a chore → click checkbox → optional comment → Confirm.
3. Waive a chore (if parent allows) → "Waive" button.
4. Log extra chore (optional) → type in "Log a chore I did..." → Log it.
5. Reminder Notes → write anything to remember later (auto-saved).

### Parent Flow

1. Click **Parent login** → enter password → unlock.
2. Adjust **Settings** (allowance, streak days, bonus, penalty) → Save.
3. Add chores under **Add Chore** (name + days M–S).
4. Edit/delete chores in **All Chores** table.
5. Use **Past chores** to fix historical completions (allowance recalculates).
6. Double-click **Allowance Pot** to manually adjust balance.

---

## Data Model

### State Object

```javascript
{
  pot: number,              // Current allowance balance
  streak: number,           // Consecutive full-completion days
  tasks: [                  // Chore definitions
    { id: number, name: string, days: number[] }  // days: 0=Sun..6=Sat
  ],
  history: [                // Activity log
    { date, timestamp, msg, amt, class }
  ],
  lastCheck: string,         // Last date processed (locale format)
  completedToday: number[], // Task IDs completed today
  waivedToday: number[],    // Task IDs waived today
  customChoresToday: string[],
  config: {
    startingAllowance, streakDaysForBonus, bonusAmount, penaltyAmount, parentPassword
  },
  dayCompletions: {         // Past dates: { completed: [], waived: [] }
    "M/D/YYYY": { completed: [taskId], waived: [taskId] }
  },
  lastMonthlyReset: string, // "YYYY-MM"
  monthlyPots: {            // Saved pot at month end
    "YYYY-MM": number
  },
  reminderNotes: string    // Kid's free-form reminder notes (auto-saved)
}
```

### Day Codes

- `0` = Sunday, `1` = Monday, … `6` = Saturday

---

## Project Structure

```
gtaskmanager/
├── index.html      # Single-file app (HTML + CSS + JS)
├── guhan.png       # Profile image for header
├── README.md       # This file
└── .git/           # Git repository
```

---

## License

Private/personal project. Use as desired.
