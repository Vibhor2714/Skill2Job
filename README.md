# Skills2Job 🚀

> *"Turn Your Skills Into Your Next Opportunity."*

Skills2Job is an intelligent, full-stack career matchmaking and talent acquisition platform built to solve algorithmic rejection. The platform ingests candidate resumes, analyzes connected GitHub repositories, evaluates career preferences, and compares them against multi-tiered job requirements to provide **5-factor explainable compatibility scores**, **eligibility evaluation**, **skill-gap diagnostics**, **personalized 4-week learning roadmaps**, and **interactive recruitment pipelines**.

All user profiles, resumes, skills, GitHub connections, and applications are dynamically persisted in an SQLite relational database with real-time recalculation of compatibility and ATS scores.

---

## 🌟 Key Capabilities

### 1. Explainable AI Matching Engine
- **5-Factor Compatibility Score (0–100%)**:
  - **Required Skill Match (40%)**: Explicit comparison against mandatory role requirements with synonym clustering.
  - **Experience Match (20%)**: Tenure and seniority comparison.
  - **Education Match (15%)**: Degree and field of study alignment.
  - **Project & GitHub Relevance (15%)**: Practical repository evidence and tech stack detection.
  - **ATS / Keyword Semantics (10%)**: Token cosine similarity and industry taxonomy matching.
- **Explainable Answers on Every Job**:
  - **WHAT?**: Match tier (*e.g. Strong Match 87%*).
  - **WHY?**: *9/10 required skills matched, 3 relevant GitHub projects detected, experience requirement satisfied.*
  - **WHAT'S MISSING?**: *Docker, AWS.*
  - **WHAT SHOULD I DO?**: *Learn Docker fundamentals and build one containerized project.*
  - **WHAT HAPPENS IF I DO?**: *Estimated match improvement: +7%, unlocking additional jobs.*

### 2. Eligibility Engine vs Compatibility
- Prevents candidates from being penalized for lacking non-mandatory preferred or bonus skills.
- Classifies positions into:
  - `ELIGIBLE ✓`
  - `PARTIALLY ELIGIBLE`
  - `LOW MATCH`
- Separates skills into **Required**, **Preferred**, and **Bonus**.

### 3. Dynamic User Persistence & Session Management
- **Stateless JWT Authentication**: Secure password hashing with persistent sessions.
- **6-Digit Email OTP Verification**: Real email verification flow with countdown timers and resend throttling.
- **Persistent SQLite Database**: Dynamic storage of user profiles, skills, resumes, and applications without dummy-data fallbacks.
- **Dynamic Compatibility Recalculation**: Authenticated job seekers see personalized compatibility scores dynamically computed against their own profile.

### 4. Interactive Resume Management & Re-Evaluation
- **Multi-Format Ingestion**: Upload resumes in `.pdf`, `.docx`, `.doc`, or `.txt`.
- **Automated Text & Skill Extraction**: Extracts technical competencies, tenure, and ATS score.
- **Resume Viewer & Re-upload in `/profile`**: Inspect current uploaded resume metadata and re-upload new iterations to immediately re-evaluate candidate compatibility across all active listings.

### 5. Real GitHub Profile Intelligence
- **Custom Profile Input**: Connect any public GitHub profile via URL (`https://github.com/username`) or handle (`@username`).
- **Public API Integration**: Fetches real repository counts, language distribution, and profile avatars.
- **Resume Project Synthesizer**: Converts open-source projects into impact-driven resume bullet points.

### 6. Career Accelerator Tools
- **Skill Gap & 4-Week Roadmap**: Converts missing competencies into structured project milestones.
- **AI Cover Letter Generator**: Generates customized cover letters referencing real projects with Tone and Length controls.
- **AI Mock Interview Simulator**: Dynamic technical and behavioral questions with comprehensive score reports.
- **Kanban Application Tracker**: Interactive stages (`Saved`, `Applied`, `Assessment`, `Interview`, `Offer`, `Rejected`) with conversion analytics.
- **Career Insights**: Interactive Recharts telemetry (compatibility trends, market skill demand, application funnels).

### 7. Unified Global Dark Mode
- Full system-wide Dark and Light mode support with persistent state across all 15+ pages.
- Accessible via Navbar and centralized Settings modal.

### 8. Recruiter & Admin Portals
- **Recruiter Dashboard**: Manage job postings with 3-tier skill requirements (Required, Preferred, Bonus).
- **Candidate Ranking**: Rank applicants by compatibility score with candidate detail drawers and interview scheduling.
- **Superadmin Telemetry & Viva Visualizer**: System health telemetry and interactive vector pipeline visualizer (`/viva`).

---

## 🛠️ Technology Stack

- **Frontend**: Next.js 14+ (App Router), TypeScript, Tailwind CSS, Lucide React, Recharts.
- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, Uvicorn.
- **Database**: SQLite (Production-ready for PostgreSQL + pgvector).
- **NLP / Matching**: Scikit-Learn (TF-IDF & Cosine Similarity), PDF/DOCX parsing, Regex tokenizers.

---

## 🚀 Quick Start Guide (Windows & macOS)

### Option A: One-Command Launchers
- **macOS (Intel & Apple Silicon) / Linux**:
  ```bash
  chmod +x start.sh
  ./start.sh
  ```
- **Windows 10/11**:
  Double-click `start.bat` or run `start.bat` in Command Prompt.
- **Universal Python Launcher (Windows & macOS)**:
  ```bash
  python3 start.py   # or: python start.py
  ```

---

## 🪟 Windows Setup (Windows 10 / 11)

### 1. Required Software
- **Python 3.11+** (recommended 3.12+): Download from [python.org](https://www.python.org/downloads/windows/) and check **"Add python.exe to PATH"** during installation.
- **Node.js 18+ LTS** (includes `npm`): Download from [nodejs.org](https://nodejs.org/).

### 2. Python & Node.js Verification
```cmd
python --version
node --version
npm --version
```

### 3. Virtual Environment & Backend Installation
```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

### 4. Frontend Installation
Open a second terminal at the project root:
```cmd
cd frontend
npm install
```

### 5. Environment Variables
Copy `.env.example` to `.env` in the project root (optional for local development):
```cmd
copy .env.example .env
```
- `APP_ENV=development` uses safe local defaults.
- If `APP_ENV=production`, you must set a strong `JWT_SECRET_KEY`.
- Optional: set `INTERVIEW_LLM_API_KEY` for LLM-based mock interview grading (otherwise the deterministic rubric evaluator is used).

### 6. Database Setup
No manual database setup is required. On first startup, FastAPI automatically creates and seeds `backend\skills2job.db` with demo accounts and sample jobs while preserving any existing records.

### 7. Running & Stopping the Application
- **Start via launcher**: Run `start.bat` or `python start.py` from the project root.
- **Or start manually**:
  - Terminal 1 (`backend\`): `.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
  - Terminal 2 (`frontend\`): `npm run dev`
- **Access**:
  - Web App: [http://localhost:3000](http://localhost:3000)
  - API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Stop servers**: Press `Ctrl+C` in each terminal window (or close the launched Command Prompt windows).

### 8. Windows Troubleshooting
- **`python` not recognized**: Re-run the Python installer and enable "Add python.exe to PATH", or use `py -m venv .venv`.
- **Port 8000 or 3000 already in use**: Find the PID with `netstat -ano | findstr :8000` and stop it with `taskkill /PID <PID> /F`.
- **Execution policy error activating `.venv` in PowerShell**: Use Command Prompt (`.venv\Scripts\activate.bat`) or invoke `.venv\Scripts\python.exe` directly without activating.

---

## 🍎 macOS Setup (Intel & Apple Silicon M1–M5)

### 1. Required Software
- **Python 3.11+** (recommended 3.12+): Install via Homebrew (`brew install python`) or [python.org](https://www.python.org/downloads/macos/).
- **Node.js 18+ LTS** (includes `npm`): Install via Homebrew (`brew install node`) or [nodejs.org](https://nodejs.org/).

### 2. Python & Node.js Verification
```bash
python3 --version
node --version
npm --version
```

### 3. Virtual Environment & Backend Installation
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 4. Frontend Installation
Open a second Terminal tab/window at the project root:
```bash
cd frontend
npm install
```

### 5. Environment Variables
Copy `.env.example` to `.env` in the project root (optional for local development):
```bash
cp .env.example .env
```
- `APP_ENV=development` uses safe local defaults.
- If `APP_ENV=production`, you must set a strong `JWT_SECRET_KEY`.
- Optional: set `INTERVIEW_LLM_API_KEY` for LLM-based mock interview grading.

### 6. Database Setup
No manual database setup is required. FastAPI resolves `backend/skills2job.db` automatically using `pathlib` regardless of your current working directory, creating and seeding it on first run without overwriting existing data.

### 7. Running & Stopping the Application
- **Start via launcher**:
  ```bash
  chmod +x start.sh
  ./start.sh
  ```
  Or using the universal Python launcher:
  ```bash
  python3 start.py
  ```
- **Or start manually**:
  - Terminal 1 (`backend/`):
    ```bash
    cd backend
    source .venv/bin/activate
    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    ```
  - Terminal 2 (`frontend/`):
    ```bash
    cd frontend
    npm run dev
    ```
- **Access**:
  - Web App: [http://localhost:3000](http://localhost:3000)
  - API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Stop servers**: Press `Ctrl+C` in the terminal running `./start.sh` or `start.py` (both backend and frontend processes are terminated cleanly), or press `Ctrl+C` in each manual terminal tab.

### 8. macOS Troubleshooting
- **Permission denied (`./start.sh`)**: Grant execute permission without `sudo`:
  ```bash
  chmod +x start.sh
  ```
- **Port already in use (8000 or 3000)**: Find and stop the process using the port:
  ```bash
  lsof -i :8000
  kill <PID>
  ```
- **Missing Python packages / `ModuleNotFoundError`**: Ensure you are using the virtual environment's Python (`source backend/.venv/bin/activate` or `backend/.venv/bin/python`) and re-run `python3 -m pip install -r requirements.txt`. Avoid installing globally with `sudo`.
- **Node.js version incompatibility**: Next.js 14 requires Node.js 18.17+. Check `node -v` and upgrade via Homebrew (`brew upgrade node`) or `nvm` (`nvm install --lts && nvm use --lts`).
- **Environment variable errors (`Missing required production secret`)**: Either set `APP_ENV=development` in `.env` for local runs, or set a strong `JWT_SECRET_KEY` in `.env` when `APP_ENV=production`.
- **SQLite database errors (`unable to open database file` or `readonly database`)**: Ensure you own the `backend/` folder (`ls -ld backend`) and are not running from a read-only disk image/DMG. If a stale lock file remains after a crash, stop all `uvicorn` processes before restarting.

---

## ⚡ Instant Demo Access
The platform includes 1-click demo accounts built into the Settings modal and login page:
- **Job Seeker**: Alex Sharma (`alex.sharma@example.com` / `DemoAlex2026!`)
- **HR Recruiter**: Sarah Jenkins (`sarah.jenkins@techcorp.example.com` / `DemoRecruiter2026!`)
- **Superadmin**: Admin (`admin@skills2job.example.com` / `AdminSkills2026!`)

---
