🤖 Smart Email Assistant (Agentic AI)

An enterprise-grade, intelligent email management system powered by Agentic AI. It seamlessly bridges the Gmail API with a Telegram bot interface, allowing users to manage, read, summarize, and draft emails using natural language text or voice notes. Backed by a secure React admin dashboard and a robust, fully asynchronous FastAPI/Supabase infrastructure.

✨ Core Features

🧠 Agentic AI Engine

Google Gemini LLM Integration: Advanced natural language processing for complex queries.

Context-Aware Summarization: Converts long email threads into concise, professional bullet points.

Intelligent Reply Generation: Contextual drafting of responses based on email history.

Human-in-the-Loop (HITL) Drafting: Autonomously detects missing information (e.g., recipient email) and smoothly asks the user for input without crashing.

Conversation Memory: Maintains context across multiple interactions for a seamless chat experience.

📱 Premium Telegram Interface

Clean MarkdownV2 Layouts: Professionally structured notifications and summaries without raw JSON leaks.

Interactive Inline Keyboards: Quick actions for Read, Summarize, Reply, and Trash directly within the chat.

Multi-Attachment Staging: Upload files directly in chat to stage them for email drafts.

Secure Downloading: Conditional 'Get Attachments' buttons with batch-limited guardrails to prevent memory overload.

🔊 Advanced Voice Processing

Speech-to-Text (STT): Process voice commands and dictate emails naturally.

Text-to-Speech (TTS): Generates high-quality auditory email summaries using Edge TTS / Google Cloud Speech.

Auto-Cleanup: Temporary overlay messages (e.g., "Generating audio...") are instantly deleted upon completion to keep the chat clean.

👨‍💼 Secure Admin Dashboard (React/Vite)

Smart Authentication: Google OAuth 2.0 integration that safely bypasses manual password checks for verified providers.

User Management: Granular controls for user provisioning, approval, and temporary/permanent suspensions (ban days).

Real-Time System Stats: Monitor active scheduled emails, STT usage tracking, and blocked threats.

Auto-Inactivity Timeouts: Secure session handling that logs out inactive admins after 10 minutes.

⚡ 100% Async Architecture

Non-Blocking Event Loops: Background crons for auto-fetching new emails and dispatching scheduled emails.

Supabase PostgREST: Utilizes the asynchronous Supabase Python Client (db_manager.db.run()) to ensure crash-free relational queries without blocking the API.

🏗️ Architecture

Database Layer

Supabase (PostgreSQL): Primary database with Row Level Security (RLS).

Async Operations: Completely non-blocking, eliminating traditional SQLAlchemy Session bottlenecks.

Contact Mapping: Relationship tracking and intelligent extraction between contacts.

API Layer

FastAPI: Modern, high-performance web framework.

Webhook Integration: Direct production binding to Telegram API updates.

JWT Auth: Secure, token-based endpoints for the React dashboard.

Bot Layer

python-telegram-bot (v22+): Handles structured command processing and callback queries.

Background Jobs: Managed queue for pinging, email checking, and schedule dispatching.

📂 Project Structure

Smart-Email-Assistant-Using-Agentic-AI/
├── backend/
│   ├── main.py                 # FastAPI application ka entry point (Server engine)
│   ├── config.py               # Settings aur Environment configuration management
│   ├── requirements.txt         # Python backend dependencies (FastAPI, PyJWT, etc.)
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── telegram_handler.py # Core Telegram bot logic, layouts, aur 100% clean UI code
│   │   ├── ai_engine.py        # Gemini Agentic AI processing engine (with HITL loops)
│   │   ├── gmail_client.py     # Google OAuth 2.0 aur Gmail API backend wrapper
│   │   ├── voice_handler.py    # Text-to-Speech (TTS) aur Speech-to-Text (STT) handler
│   │   └── contact_manager.py  # Contact list mapping aur intelligent extraction logic
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py             # User authentication endpoints (Telegram login logs)
│   │   ├── admin.py            # Admin router (Supabase password change + async bypass check)
│   │   └── user.py             # User profile preferences aur dynamic contacts CRUD endpoints
│   └── db/
│       ├── __init__.py
│       ├── models.py           # Supabase async database thread operations (db_manager logic)
│       └── memory.py           # AI agent conversation memory aur context storage handlers
│
├── frontend/                   # React + Vite + Tailwind Admin Dashboard cluster
│   ├── package.json            # Node.js dependencies aur scripts compilation framework
│   ├── vite.config.ts          # Vite asset pipeline aur proxy definitions configuration
│   ├── tsconfig.json           # TypeScript strict type compiler matching parameters
│   ├── tailwind.config.js      # Tailwind UI design colors aur transition criteria grid
│   └── src/
│       ├── main.tsx            # Application DOM mounting entry pivot
│       ├── App.tsx             # Main routing registry, Google auth interception, & route locks
│       ├── index.css           # Global core styles allocation matrix
│       ├── components/
│       │   └── Navbar.tsx      # Multi-mode clean responsive navigation layout matrix
│       └── pages/
│           ├── Landing.tsx     # Public promotional landing frame screen
│           ├── About.tsx       # System description matrix info window
│           ├── AdminLogin.tsx  # Admin access gateway validation layout portal
│           ├── Dashboard.tsx   # Core stats view, accordions layout, & auto inactivity timeout hook
│           └── Settings.tsx    # Secure change password component (Google login layout conditional bypass)
│
├── database/                   # Cloud persistence schema scripts
│   ├── schema.sql              # Supabase PostgreSQL structural tables setup guidelines
│   └── seed.sql                # Core initialization data setup scripts (Default Super Admin entry)
│
├── LICENSE                     # MIT License structural validation file
├── .gitignore
└── README.md                   # Production grade comprehensive documentation text manual



🚀 Setup Instructions

Prerequisites

Python 3.10+

Node.js (for frontend)

Supabase Account (PostgreSQL)

Google Cloud Console Account (Gmail API, OAuth2)

Telegram Bot Token (via @BotFather)

1. Environment Configuration

Create a .env file in the backend/ directory:

# Database (Supabase)
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
RENDER_WEB_SERVICE_URL=[https://your-production-url.com](https://your-production-url.com)

# Google APIs (OAuth & Gemini)
GOOGLE_API_KEY=your_gemini_api_key
GOOGLE_CLIENT_ID=your_oauth_client_id
GOOGLE_CLIENT_SECRET=your_oauth_client_secret
GOOGLE_REDIRECT_URI=[https://your-domain.com/api/auth/oauth/callback](https://your-domain.com/api/auth/oauth/callback)

# Security & App Config
JWT_SECRET=your_secure_jwt_secret


2. Backend Installation

git clone https://github.com/SalmanW2/Smart-Email-Assistant-Using-Agentic-AI.git
cd Smart-Email-Assistant-Using-Agentic-AI/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload


3. Frontend Installation

cd ../frontend
npm install
npm run dev


4. Telegram Bot Configuration

Go to Telegram and search for @BotFather.

Create a new bot and copy the HTTP API Token.

Add the token to your .env file.

Note: In production, the bot automatically binds its webhook to ${RENDER_WEB_SERVICE_URL}/webhook/telegram.

🌐 API Endpoints

Authentication

POST /api/auth/start-auth - Initiates the OAuth flow.

GET /api/auth/oauth/callback - Google OAuth return redirect.

POST /api/admin/login - Secure manual admin login.

Admin Dashboard

GET /api/admin/stats - Fetch real-time system metrics.

GET /api/admin/users - List all connected Telegram users.

POST /api/admin/users/{id}/permissions - Update AI/Voice permissions or suspend users.

POST /api/admin/change-password - Modify admin credentials safely.

🛡️ Security & Reliability

No SQLAlchemy Crashes: The backend strictly uses the Supabase Python Client to ensure non-blocking, crash-free relational queries.

Attachment Guardrails: Telegram attachment downloads are capped (e.g., max 10 files or 20MB per batch) with instant local thread-cleanup os.remove() to prevent server storage leaks.

Strict Frontend Routing: React protected routes intercept unauthorized access, tying session validation strictly to JWT expiries and browser interaction events.

Role-Based Access Control (RBAC): Distinct privileges for admin and super_admin roles to prevent unauthorized system modifications.

🐳 Deployment (Docker)

FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]


Ensure all environment variables from .env are injected into your production container (e.g., via Render, Heroku, or AWS secrets).

🤝 Contributing

Fork the repository

Create a feature branch (git checkout -b feature/NewFeature)

Commit your changes (git commit -m 'Add NewFeature')

Push to the branch (git push origin feature/NewFeature)

Open a Pull Request

📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

📞 Support & Roadmap

Current Roadmap:

[x] Integrate Agentic AI Engine for HITL drafting.

[x] Migrate to 100% Async Supabase operations.

[x] Refine Telegram UI/Typography.

[ ] Implement email threading and conversation grouping.

[ ] Add multi-language dynamic translation support.

For support, please open an issue on the GitHub repository.