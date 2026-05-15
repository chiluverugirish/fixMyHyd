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

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL (for production) or SQLite (development)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Gemini API Keys
- Cloudinary Account (free tier available)

### 1. Clone and setup virtual environment

```bash
# Clone repository
git clone <repo>
cd fixmyhyd

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

- `TELEGRAM_BOT_TOKEN` - Get from [@BotFather](https://t.me/botfather)
- `GOOGLE_API_KEY_*` - Get from [Google AI Studio](https://aistudio.google.com/app/apikey)
- `CLOUDINARY_CLOUD_NAME` - Your Cloudinary account name
- `CLOUDINARY_API_KEY` - Your Cloudinary API key
- `CLOUDINARY_API_SECRET` - Your Cloudinary API secret
- `SECRET_KEY` - Generate a random key: `python -c "import secrets; print(secrets.token_hex(32))"`

### 3. Run the application

**Development (SQLite):**

```bash
# Terminal 1: Run Flask portal
python app.py
# Visit http://localhost:5001
# Default admin credentials: admin / admin123

# Terminal 2: Run Telegram bot
python bot.py
```

**Production (Render with PostgreSQL):**

- Push to GitHub
- Create new Web Service on [Render](https://render.com)
- Set Environment Variables in Render dashboard:
  - `DATABASE_URL` - Auto-provided by Render
  - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
  - All Gemini API keys
  - `TELEGRAM_BOT_TOKEN`
  - `FLASK_ENV=production`
  - `PORTAL_BASE_URL=https://your-app.onrender.com`
- Render will automatically run migrations and start the app

## Deployment to Render

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Production ready with Cloudinary"
git push
```

### Step 2: Create Render Web Service

1. Go to [render.com](https://render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `gunicorn app:app`

### Step 3: Add Environment Variables

In Render dashboard → Environment:

```
FLASK_ENV=production
DATABASE_URL=(auto-provided by Render PostgreSQL)
CLOUDINARY_CLOUD_NAME=your_cloudinary_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
GOOGLE_API_KEY_IMAGE=your_gemini_key
GOOGLE_API_KEY_AUDIO=your_gemini_key
GOOGLE_API_KEY_TEXT=your_gemini_key
GOOGLE_API_KEY_REPORT=your_gemini_key
TELEGRAM_BOT_TOKEN=your_bot_token
SECRET_KEY=generate_random_key
PORTAL_BASE_URL=https://your-app.onrender.com
```

### Step 4: Database Setup

- Render PostgreSQL is auto-provisioned
- Migrations run automatically on app startup
- Default admin: `admin` / `admin123`

**👉 For complete deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)**

## Tech Stack

| Component         | Technology                       | Purpose                  |
| ----------------- | -------------------------------- | ------------------------ |
| **Frontend**      | HTML5, CSS3, JavaScript          | Web UI                   |
| **Backend**       | Flask 2.3, Python 3.11           | REST API                 |
| **Database**      | SQLite (dev) / PostgreSQL (prod) | Data storage             |
| **Image Storage** | Cloudinary                       | Cloud CDN                |
| **AI/ML**         | Google Gemini                    | Analysis & transcription |
| **Bot**           | Telegram Bot API                 | Chat interface           |
| **Hosting**       | Render                           | Production deployment    |

## Features

### ✨ Telegram Bot

- Auto-registers citizen on first `/start`
- Quick photo + voice complaint reporting
- GPS auto-extraction from EXIF metadata
- Multi-language support (Telugu, Hindi, English)
- Real-time complaint tracking
- Status notifications

### 🌐 Web Portal

- Citizen dashboard for tracking complaints
- Admin dashboard with advanced filtering
- Complaint submission with image upload
- Status history and comments
- CSV export for reports
- User & role management

### 🤖 AI Pipeline (Gemini)

- Image analysis & categorization
- Voice transcription & translation
- Priority assessment (Low/Medium/High)
- Formal complaint generation
- Zone/location intelligence

### ☁️ Cloud Services

- **Cloudinary**: Image hosting & CDN
- **Render**: Web hosting & PostgreSQL
- **Google Gemini**: Multi-modal AI
- **Telegram**: Bot integration

## Quick Navigation

- **Setup**: [Quick Start](#quick-start) above
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Architecture**: [STRUCTURE.md](STRUCTURE.md)
- **Configuration**: [.env.example](.env.example)
- **Database**: See schema below

## Bot Commands

To use the bot: Open Telegram and search for **@FixMyHYDbot**, then send `/start`.

| Command     | Description               |
| ----------- | ------------------------- |
| `/start`    | Register & see welcome    |
| `/report`   | Start new complaint       |
| `/mystatus` | Check 5 recent complaints |
| `/portal`   | Link to web dashboard     |
| `/cancel`   | Cancel current action     |
| (photo)     | Auto-trigger report flow  |

## Web Portal Routes

| Route              | Access  | Purpose               |
| ------------------ | ------- | --------------------- |
| `/`                | Public  | Home page             |
| `/user/login`      | Public  | Citizen login         |
| `/user/register`   | Public  | Citizen signup        |
| `/user/dashboard`  | Citizen | Track complaints      |
| `/report-issue`    | Citizen | Submit new complaint  |
| `/admin/login`     | Public  | Admin login           |
| `/admin/dashboard` | Admin   | Manage all complaints |
| `/health`          | Public  | Health check          |

## API Reference

### Telegram Bot Endpoints

- `POST /api/bot/register-user` — Auto-create citizen account
- `POST /api/bot/submit-complaint` — Process complaint from bot
- `GET /api/bot/user-complaints/<telegram_id>` — Fetch user complaints

### Portal Endpoints

- `POST /api/report-issue` — Submit complaint from web
- `GET /api/user/complaints` — List own complaints
- `GET /api/user/complaints/<id>` — Get complaint details

### Admin Endpoints

- `GET /api/admin/complaints` — List all complaints
- `GET /api/admin/complaints/<id>` — Get details
- `PUT /api/admin/complaints/<id>/status` — Update status
- `DELETE /api/admin/complaints/<id>` — Delete complaint

### Health Endpoint

- `GET /health` — Service status check

## Database Schema

### users table

```
id (PK) | email | password_hash | name | phone | telegram_id | created_at
```

### admins table

```
id (PK) | username | password_hash | name | created_at
```

### complaints table

```
id (PK) | ghmc_id | category | priority | subject | description |
location | zone | gps_lat | gps_lng | status | submitted_by | source |
user_id (FK) | image_path | created_at | updated_at
```

### status_history table

```
id (PK) | complaint_id (FK) | old_status | new_status | changed_by |
comments | created_at
```

## Deployment Checklist

- [ ] GitHub repository created & code pushed
- [ ] Render account created
- [ ] Render Web Service configured
- [ ] Render PostgreSQL created
- [ ] Cloudinary account & credentials obtained
- [ ] Telegram Bot Token obtained
- [ ] Gemini API keys created
- [ ] All environment variables set in Render
- [ ] Deployment successful (check logs)
- [ ] App accessible at `https://your-app.onrender.com`
- [ ] Telegram bot deployed (separate service)
- [ ] End-to-end testing complete

**See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed step-by-step guide.**

## Troubleshooting

**Q: Bot not responding?**  
A: Check bot.py is running and TELEGRAM_BOT_TOKEN is correct in .env

**Q: Images not uploading?**  
A: Verify Cloudinary credentials and free tier limits

**Q: Database connection failed?**  
A: Check DATABASE_URL is set correctly in production

**Q: "Admin login failed"?**  
A: Default credentials are admin / admin123 (change immediately)

**Q: Getting rate-limited?**  
A: Check Gemini API quota or use separate API keys for different services

## Performance & Security

### ⚡ Optimizations

- Cloudinary CDN for global image delivery
- PostgreSQL connection pooling
- Caching for static assets
- Lazy loading for images

### 🔒 Security

- SHA256 password hashing with salt
- Secure session management
- HTTPS enforced in production
- Input validation on all endpoints
- Environment-based secrets management

## Support & Resources

- **Render Docs**: https://render.com/docs
- **PostgreSQL**: https://www.postgresql.org/docs/
- **Cloudinary**: https://cloudinary.com/documentation
- **Telegram Bot API**: https://core.telegram.org/bots
- **Flask**: https://flask.palletsprojects.com/
- **Google Gemini**: https://ai.google.dev

## Project Status

| Component     | Status              | Notes                    |
| ------------- | ------------------- | ------------------------ |
| Telegram Bot  | ✅ Production Ready | Multi-language support   |
| Web Portal    | ✅ Production Ready | Admin dashboard included |
| AI Pipeline   | ✅ Production Ready | Gemini integration       |
| Cloud Storage | ✅ Production Ready | Cloudinary CDN           |
| Database      | ✅ Production Ready | PostgreSQL + SQLite      |
| Deployment    | ✅ Production Ready | Render ready             |

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Test your changes locally
4. Submit a pull request

## License

[Specify your license - MIT, GPL, etc.]

## Acknowledgments

- Built with Flask, Telegram Bot API, and Google Gemini
- Deployed on Render with PostgreSQL
- Images hosted on Cloudinary
- Open source community

Run the bot separately as a Background Worker with start command: `python bot.py`
