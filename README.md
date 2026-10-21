# Invoice Chaser AI

A beginner-friendly Python full-stack MVP for tracking invoices, recording partial/full payments, viewing cash-flow metrics, and generating polite reminder messages. Built from the supplied PRD. Defaults to SQLite and demo mode so you can run it without paid APIs.

## Features
- Registration/login with hashed passwords and signed session cookie
- User-scoped client and invoice dashboard
- Invoice statuses: Upcoming, Due Soon, Overdue, Partially Paid, Paid, Cancelled, Payment claimed
- Partial and full payments
- Reminder preview and 5-step due-date schedule with duplicate protection
- Groq AI message writing when configured; deterministic template fallback
- WhatsApp Cloud API integration when configured and consent is recorded; otherwise demo logs
- STOP opt-out webhook endpoint and basic reply classification
- Outstanding, overdue, due-this-week and recovered metrics
- Responsive dashboard UI
- Basic service tests

## Requirements
Python 3.11–3.13 recommended. If you currently have Python 3.14, install packages in a fresh virtual environment and check whether each dependency supports it. If a dependency install fails, use Python 3.12 for the most predictable setup.

## Windows PowerShell setup
```powershell
cd path\to\invoice_chaser
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 in your browser. Register an account, add a client, then add an invoice.

If you only have Python 3.14, try:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## MySQL option
Install a MySQL driver:
```powershell
pip install pymysql
```
Create the database in MySQL Workbench:
```sql
CREATE DATABASE invoice_chaser CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Then edit `.env`:
```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/invoice_chaser
```
Restart the app. Never commit `.env` or real client data.

## Optional Groq AI
Add `GROQ_API_KEY` and `GROQ_MODEL` in `.env`. If not configured or the API fails, the app uses a safe fallback template. Verify messages before enabling live delivery.

## Optional WhatsApp Cloud API
Set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and `WHATSAPP_API_VERSION` in `.env`. Only clients with recorded consent can receive messages. Configure the provider webhook to `/webhooks/whatsapp` using a publicly reachable HTTPS URL. For local testing, use a secure tunnel and a test number; never send unsolicited reminders.

**Important:** The webhook is a minimal MVP endpoint, not a fully hardened production webhook. Production use needs provider signature verification, WhatsApp verification challenge, CSRF protections, rate limits, retries, a proper user/tenant scope for every query, HTTPS, backups, monitoring and a transactional outbox. Do not use real customer data until those controls are implemented.

## Run tests
```powershell
pytest -q
```

## API
- `GET /health`
- `GET /api/invoices` (login required)
- `POST /api/reminders/run` (login required)
- `POST /webhooks/whatsapp` (provider webhook; minimal demo implementation)
- Interactive docs: http://127.0.0.1:8000/docs

## Project layout
```text
invoice_chaser/
  app/
    main.py
    config.py
    database.py
    models.py
    security.py
    services.py
    templates/
    static/
  tests/
  .env.example
  requirements.txt
  README.md
```
