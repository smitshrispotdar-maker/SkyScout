# SkyScout - Flight Search AI Agent

SkyScout is an educational AI-powered flight search assistant built with **FastAPI** and a **static HTML/CSS/JavaScript frontend**. It demonstrates a multi-agent workflow for extracting travel requests, searching a sample flight inventory, ranking affordable options, verifying outputs, and generating email previews.

> **Important:** This project uses a **demo flight inventory only**. It is not a live airline search, booking, or payment system. Prices, routes, and availability are sample data for academic demonstration.

## Problem Statement

Travel planning often requires users to provide multiple details, compare options, and understand constraints such as budget and date. This project demonstrates how an AI-assisted, multi-agent system can collect travel intent, validate inputs, search sample flight data, rank suitable options, and present results in a clear dashboard.

## Project Objectives

- Accept natural-language and form-based flight search requests.
- Extract key travel details: origin, destination, date, budget, and email.
- Validate user input safely and clearly.
- Filter and rank the top 3 cheapest flights within budget from demo inventory.
- Coordinate specialized agents with a visible activity trace.
- Support session-based memory with explicit save/reuse/clear controls.
- Provide email preview by default and optional SMTP delivery when configured.
- Present a professional, responsive, and accessible dashboard UI.

## Main Features

- **Natural-language extraction** with form fallback for missing details.
- **Multi-agent coordination**: a Coordinator plans the steps and delegates to Security, Extractor, Validation, Search, Ranking, Verifier, Email and Memory agents. Each is a separate class and appears by name in the activity trace.
- **Input validation**: ISO date, no past dates, budget limits, email format, origin/destination checks.
- **Demo flight search**: 12 routes and 31 sample flights, date-aware (each flight operates on certain weekdays), budget filtering and utility ranking from the bundled inventory.
- **Memory & preferences**: session-based JSON storage, explicit save, reuse toggle, and clear action.
- **Email handling**: preview mode by default; optional SMTP send; clear failure status when SMTP fails.
- **Safety controls**: basic rule-based prompt-injection detection and output verification.
- **Responsive UI**: desktop/tablet/mobile layout with accessible navigation and status messages.

## Agent Roles

| Agent | Responsibility | Course unit |
|---|---|---|
| Coordinator | Decomposes the goal into the active plan steps and delegates each | II, IV |
| Security Agent | Rule-based prompt-injection scan of all input | V |
| Extractor Agent | Reads free text: cities, budget (`under 30000`, `Rs. 25,000`, `30k`), date, email | I |
| Validation Agent | Date, budget, email, route checks | I |
| Search Agent | Finds sample flights for the route and weekday | IV |
| Ranking Agent | Budget filter and cheapest-first top 3 | IV |
| Verifier Agent | Re-checks results against inventory, route and budget | V |
| Email Agent | Email preview, optional SMTP send | IV |
| Memory Agent | Explicit save / reuse / clear of preferences | III |

Extraction is rule-based by default. If a Groq API key is configured, the LLM extractor may be used with deterministic fallback.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic, Uvicorn |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Storage | JSON files per session (demo memory) |
| Testing | pytest, FastAPI TestClient |
| Email | `smtplib` with STARTTLS (optional) |

## Project Structure

```text
SkyScout/
├── backend/
│   ├── agent.py            # All agents + Coordinator, memory, email
│   ├── main.py             # FastAPI app and API routes
│   └── safety.py           # Prompt-injection scan and output verification
├── data/
│   └── memory/             # Session JSON memory files (created at runtime)
├── frontend/
│   ├── index.html          # Dashboard UI
│   ├── styles.css          # Responsive styling
│   └── app.js              # UI behavior, validation, API calls
├── tests/
│   └── test_agent.py       # Automated tests
├── .env.example            # Optional SMTP configuration reference
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Runtime + test dependencies (pytest, httpx)
├── start.bat               # Windows convenience launcher
└── README.md
```

## Installation

### Prerequisites

- Python 3.10+ recommended
- Windows PowerShell (commands below use Windows paths)

### Setup

```powershell
cd path\to\SkyScout
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

## Environment Configuration

The app runs in **email preview mode** by default. No `.env` file is required.

For optional real SMTP delivery, set environment variables before starting:

```powershell
$env:SMTP_HOST="smtp.example.com"
$env:SMTP_PORT="587"
$env:SMTP_USER="your_smtp_user"
$env:SMTP_PASSWORD="your_app_password"
$env:SMTP_FROM="you@example.com"
```

Optional memory directory:

```powershell
$env:MEMORY_DIR="./data/memory"
```

See `.env.example` for reference. **Do not commit real credentials.**

## Run the Application (Windows)

```powershell
python -m uvicorn backend.main:app --reload
```

Open: **http://127.0.0.1:8000**

API docs: **http://127.0.0.1:8000/docs**

You can also use `start.bat` on Windows.

## Application Usage

1. **Search**: Enter a request or fill form fields (From, To, Date, Budget, Email).
2. **Sample request**: Click "Use sample request" to prefill a valid demo search.
3. **Validation**: The app rejects past dates, invalid emails, invalid budgets, and unsupported routes.
4. **Results**: View top 3 ranked demo flights under budget.
5. **Memory**: Enable "Remember my preferences" to explicitly save preferences. Use "Use saved preferences" to reuse them. Clear memory anytime.
6. **Agent Activity**: Inspect the actual multi-agent trace for the request.
7. **Email**: Review preview/sent/failed status. SMTP failure never reports as sent.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health/status and email mode |
| POST | `/api/session` | Create anonymous session ID |
| POST | `/api/search` | Run flight search workflow |
| GET | `/api/memory/{session_id}` | Retrieve saved preferences |
| DELETE | `/api/memory/{session_id}` | Clear saved preferences |

### Search Request Body

```json
{
  "session_id": "32-char-hex",
  "query": "Find flights from Pune to Singapore under 30000",
  "origin": "Pune",
  "destination": "Singapore",
  "date": "2026-12-15",
  "budget": 30000,
  "email": "demo@example.com",
  "reuse_memory": true,
  "save_memory": false
}
```

## Memory Functionality

- Memory is **session-based** and stored as JSON files in `data/memory/`.
- The anonymous session ID is stored in the browser's `localStorage`, so saved preferences survive new tabs and browser restarts (long-term memory).
- Session files older than 30 days are deleted automatically when the app starts.
- Preferences are saved **only when `save_memory` is true** (explicit user choice).
- Saved fields: origin, destination, budget, email.
- Users can reuse or clear saved preferences at any time.
- Memory is demo data and not encrypted/authenticated.

## Email Preview and SMTP

- **Preview mode (default):** No SMTP credentials configured; email body/subject generated and shown.
- **Sent:** SMTP configured and delivery succeeds.
- **Failed:** SMTP configured but delivery fails after retry; response status is `success_email_failed`, flight results remain visible, and preview is preserved.
- The system **never claims delivery** when SMTP fails.

## Demo Inventory Limitations

- Flight data is static sample inventory in `backend/agent.py`.
- Supported cities: Pune, Mumbai, Delhi, Singapore. Routes are limited to the configured inventory (see `/api/routes`).
- Each sample flight has an operating-weekday list; the travel date selects the flights that run that day. Schedules are invented for the demo.
- Prices are not real-time and not bookable.
- FX rates and weather advisories are static demo tables, not live provider data.
- The app does not perform live airline API calls, payments, or ticketing.

## Safety Limitations

- Prompt-injection detection is **basic rule-based** pattern matching for demonstration.
- Output safety verification checks results against demo inventory/rules, not real-world booking safety.
- These controls reduce obvious risks but **do not guarantee complete protection**.
- Do not enter sensitive personal data beyond what is needed for demo.

## Testing

Install the test dependencies, then run all tests:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover extraction, validation, route handling, memory behavior, safety checks, briefing/PDF output, and API endpoints. Run tests with `GROQ_API_KEY` and SMTP environment variables unset; the default test environment makes no real network/email calls.

## Windows Quick Start Commands

```powershell
cd path\to\SkyScout
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m uvicorn backend.main:app --reload
```
## Running SkyScout on macOS

Follow these steps to set up and run the SkyScout project on macOS.

### Prerequisites

- macOS (Intel or Apple Silicon)
- Python 3 installed
- Git
- VS Code (recommended)

### Step 1: Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd SkyScout
```

### Step 2: Create a Virtual Environment

```bash
python3 -m venv .venv
```

### Step 3: Activate the Virtual Environment

```bash
source .venv/bin/activate
```

### Step 4: Upgrade pip

```bash
python -m pip install --upgrade pip
```

### Step 5: Install Dependencies

```bash
python -m pip install -r requirements-dev.txt
```

### Step 6: Run Tests

```bash
python -m pytest -q
```

### Step 7: Start the FastAPI Server

```bash
python -m uvicorn backend.main:app --reload
```

### Step 8: Access the Application

Once the server starts successfully, open:

- **API:** http://127.0.0.1:8000
- **Swagger Documentation:** http://127.0.0.1:8000/docs
- **ReDoc Documentation:** http://127.0.0.1:8000/redoc

### Deactivate the Virtual Environment

After finishing your work, run:

```bash
deactivate
```

### Troubleshooting

**If Python is not installed:**

Install Python 3 using Homebrew:

```bash
brew install python
```

**If pytest is missing:**

```bash
python -m pip install pytest
```

**If Uvicorn is missing:**

```bash
python -m pip install uvicorn
```

**If you encounter permission issues while activating the environment:**

```bash
chmod +x .venv/bin/activate
source .venv/bin/activate
```

**Note:** Always activate the virtual environment before installing dependencies or running the application.