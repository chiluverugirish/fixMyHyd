
Real-world problem: 

Residents of large metropolitan areas like Hyderabad face daily civic issues – illegal garbage dumps, broken streetlights, potholes, and water logging. Reporting these issues to the Greater Hyderabad Municipal Corporation (GHMC) is a fragmented and frustrating process. Existing apps are often clunky, require precise categorization and location details that citizens don't have, and offer little to no feedback, leaving people feeling unheard.

Who is affected and why it matters: This affects every resident, impacting public health, safety, and quality of life. The lack of an efficient feedback loop leads to citizen apathy and the persistence of easily solvable problems, eroding trust in local governance.

Your Solution

Idea: "FixMyHyd," an AI-powered, communication-first platform that makes reporting a civic issue as easy as sending a message to a friend.

How it solves the problem: A citizen can simply send a photo or a voice note in Telugu, Hyderabadi Hindi, or English via a WhatsApp chatbot. The AI backend will automatically:

Extract the GPS location from the photo's metadata.

Analyze the image and transcribe the voice note to understand the context (e.g., "This is a broken manhole cover on Road No. 12, Banjara Hills").

Automatically categorize the issue (e.g., 'Sanitation', 'Roads', 'Electrical').

Draft and submit a formal complaint to the official GHMC portal on the user's behalf.

Uniqueness: It removes all friction from the reporting process ("zero-effort reporting") and, crucially, closes the feedback loop by acting as an autonomous follow-up agent for the citizen.



# FixMyHyd — Merged Project

A civic issue reporting platform for Hyderabad combining a **Telegram bot** for convenient on-the-go reporting with a **web portal** for status tracking and municipal management.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Citizens                          │
│                                                     │
│   📱 Telegram Bot          🌐 Web Portal           │
│   (quick reporting)        (full dashboard)         │
└──────────┬──────────────────────┬───────────────────┘
           │ HTTP POST            │ HTTP
           ▼                      ▼
┌──────────────────────────────────────────────────────┐
│              Flask Backend (app.py)                  │
│                                                      │
│  /api/bot/*   ←── Bot endpoints                      │
│  /api/report-issue ←── Portal endpoint               │
│                                                      │
│  _process_complaint_submission() ←── shared pipeline │
│                                                      │
│  ┌─────────────────────────────────────────────┐     │
│  │           Gemini AI Pipeline                │     │
│  │  1. analyze_image_with_gemini()             │     │
│  │  2. transcribe_audio_with_gemini()          │     │
│  │  3. analyze_text_with_gemini()              │     │
│  │  4. generate_formal_report_with_gemini()    │     │
│  └─────────────────────────────────────────────┘     │
│                                                      │
│  SQLite (dev) / PostgreSQL (prod)                    │
└──────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│              Municipal Dashboard                     │
│  Filters: Status | Category | Priority | Zone |Source│
│  Actions: View details | Update status | Export CSV  │
└──────────────────────────────────────────────────────┘
```

## User Account Linking

Telegram users get a portal account **automatically** on first bot interaction (`/start`). Their `telegram_id` is stored in the `users` table. All complaints submitted via the bot are visible in the portal under the same account.

Users can optionally register on the portal with email/password — if they want to log in via browser without Telegram. Currently these are separate accounts; to link them, a user would need to verify ownership of both.

## Setup

### 1. Clone and install
```bash
git clone <repo>
cd fixmyhyd
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env — fill in TELEGRAM_BOT_TOKEN and GOOGLE_API_KEY_* at minimum
```

### 3. Run the portal
```bash
python app.py
# Visit http://localhost:5001
# Default admin: admin / admin123
```

### 4. Run the bot (separate terminal)
```bash
python bot.py
```

## Bot Commands

To use the bot: Open the Telegram and search for **@FixMyHYDbot** and send `/start` to begin.

| Command | Description |
|---------|-------------|
| `/start` | Register and see welcome message |
| `/report` | Start a new complaint (photo → description → location) |
| `/mystatus` | See your 5 most recent complaints |
| `/portal` | Get link to your dashboard |
| `/cancel` | Cancel current report |

Direct photo sends also trigger the report flow automatically.

## Portal Routes

| Route | Access | Description |
|-------|--------|-------------|
| `/` | Public | Home / stats |
| `/user/login` | Public | Citizen login |
| `/user/register` | Public | Citizen registration |
| `/user/dashboard` | Citizen | View own complaints |
| `/report-issue` | Citizen | Submit via web form |
| `/admin/login` | Public | Municipal login |
| `/admin/dashboard` | Admin | All complaints + filters |

## API Endpoints

### Bot API (called by bot.py)
- `POST /api/bot/register-user` — upsert user by telegram_id
- `POST /api/bot/submit-complaint` — submit with image + multipart data
- `GET  /api/bot/user-complaints/<telegram_id>` — fetch recent complaints

### Portal API
- `POST /api/report-issue` — submit complaint (session auth)
- `GET  /api/user/complaints` — list own complaints
- `GET  /api/user/complaints/<id>` — complaint detail

### Admin API
- `GET  /api/admin/complaints` — all complaints
- `GET  /api/admin/complaints/<id>` — detail
- `PUT  /api/admin/complaints/<id>/status` — update status
- `DELETE /api/admin/complaints/<id>` — delete

## Database Schema

```sql
users          — id, email, password_hash, name, phone, telegram_id
admins         — id, username, password_hash, name
complaints     — id, ghmc_id, category, priority, subject, description,
                 location, zone, gps_lat, gps_lng, status, submitted_by,
                 source (telegram|portal), user_id, created_at, updated_at
status_history — complaint_id, old_status, new_status, changed_by, comments
```

## Deployment (Render)

1. Create a Web Service pointing to this repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Add a PostgreSQL database and set `DATABASE_URL`
5. Set all env vars from `.env.example`

Run the bot separately as a Background Worker with start command: `python bot.py`
