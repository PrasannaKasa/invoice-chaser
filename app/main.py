from datetime import date, timedelta
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from apscheduler.schedulers.background import BackgroundScheduler
from app.database import Base, engine, get_db, SessionLocal
from app.models import User, Client, Invoice, Payment, ReminderLog, ClientReply
from app.security import hash_password, verify_password, make_session, read_session
from app.services import invoice_status, balance, record_payment, run_reminders, recovered_total, classify_reply, generate_message

Base.metadata.create_all(bind=engine)
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not scheduler.running:
        scheduler.add_job(_scheduled_reminders, "interval", hours=12, id="invoice-reminders", replace_existing=True)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)

def _scheduled_reminders():
    db = SessionLocal()
    try:
        run_reminders(db)
    finally:
        db.close()

app = FastAPI(title="Invoice Chaser AI", version="1.0.0", lifespan=lifespan)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

def current_user(request: Request, db: Session):
    token = request.cookies.get("invoice_chaser_session")
    user_id = read_session(token) if token else None
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()

def require_user(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    invoices = db.query(Invoice).filter(Invoice.user_id == user.id).order_by(Invoice.due_date.asc()).all()
    for inv in invoices:
        inv.display_status = invoice_status(inv)
        inv.remaining_balance = balance(inv)
    clients = db.query(Client).filter(Client.user_id == user.id).order_by(Client.name).all()
    outstanding = sum(balance(i) for i in invoices if invoice_status(i) not in ("Paid", "Cancelled"))
    overdue = sum(balance(i) for i in invoices if invoice_status(i) == "Overdue")
    due_week = sum(1 for i in invoices if date.today() <= i.due_date <= date.today() + timedelta(days=7) and invoice_status(i) not in ("Paid", "Cancelled"))
    context = {"request": request, "user": user, "invoices": invoices, "clients": clients,
               "outstanding": round(outstanding, 2), "overdue": round(overdue, 2), "due_week": due_week,
               "recovered": recovered_total(db, user.id), "recovered_month": recovered_total(db, user.id, True),
               "today": date.today()}
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={"request": request, "error": ""})

@app.post("/register")
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...), business_name: str = Form("My Business"), db: Session = Depends(get_db)):
    email = email.strip().lower()
    if len(password) < 8:
        return templates.TemplateResponse(request=None, name="register.html", context={"request": None, "error": "Password must be at least 8 characters."}, status_code=400)
    if db.query(User).filter(User.email == email).first():
        return RedirectResponse("/login?exists=1", status_code=303)
    user = User(name=name.strip(), email=email, password_hash=hash_password(password), business_name=business_name.strip() or "My Business")
    db.add(user); db.commit(); db.refresh(user)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("invoice_chaser_session", make_session(user.id), httponly=True, samesite="lax", secure=False, max_age=604800)
    return response

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": ""})

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": "Invalid email or password."}, status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("invoice_chaser_session", make_session(user.id), httponly=True, samesite="lax", secure=False, max_age=604800)
    return response

@app.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("invoice_chaser_session")
    return response

@app.post("/clients")
def create_client(request: Request, name: str = Form(...), company: str = Form(""), whatsapp_number: str = Form(""), email: str = Form(""), preferred_channel: str = Form("demo"), consent: str | None = Form(None), db: Session = Depends(get_db)):
    user = require_user(request, db)
    client = Client(user_id=user.id, name=name.strip(), company=company.strip(), whatsapp_number=whatsapp_number.strip(),
                    email=email.strip(), preferred_channel=preferred_channel, consent=bool(consent))
    db.add(client); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/clients/{client_id}/toggle-consent")
def toggle_consent(client_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    client = db.query(Client).filter_by(id=client_id, user_id=user.id).first()
    if not client: raise HTTPException(404, "Client not found")
    client.consent = not client.consent
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/clients/{client_id}/delete")
def delete_client(client_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    client = db.query(Client).filter_by(id=client_id, user_id=user.id).first()
    if not client: raise HTTPException(404, "Client not found")
    db.delete(client); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/invoices")
def create_invoice(request: Request, client_id: int = Form(...), invoice_number: str = Form(...), description: str = Form(""), amount: float = Form(...), issue_date: date = Form(...), due_date: date = Form(...), payment_link: str = Form(""), db: Session = Depends(get_db)):
    user = require_user(request, db)
    client = db.query(Client).filter_by(id=client_id, user_id=user.id).first()
    if not client: raise HTTPException(404, "Client not found")
    if amount <= 0 or due_date < issue_date:
        raise HTTPException(400, "Amount must be positive and due date cannot precede issue date.")
    if db.query(Invoice).filter_by(user_id=user.id, invoice_number=invoice_number.strip()).first():
        raise HTTPException(400, "Invoice number already exists.")
    invoice = Invoice(user_id=user.id, client_id=client.id, invoice_number=invoice_number.strip(), description=description.strip(),
                      amount=amount, issue_date=issue_date, due_date=due_date, payment_link=payment_link.strip())
    db.add(invoice); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/invoices/{invoice_id}/payment")
def add_payment(invoice_id: int, request: Request, amount: float = Form(...), paid_on: date = Form(...), note: str = Form(""), db: Session = Depends(get_db)):
    user = require_user(request, db)
    invoice = db.query(Invoice).filter_by(id=invoice_id, user_id=user.id).first()
    if not invoice: raise HTTPException(404, "Invoice not found")
    try: record_payment(db, invoice, amount, paid_on, note.strip())
    except ValueError as exc: raise HTTPException(400, str(exc))
    return RedirectResponse("/", status_code=303)

@app.post("/invoices/{invoice_id}/status")
def set_status(invoice_id: int, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    user = require_user(request, db)
    invoice = db.query(Invoice).filter_by(id=invoice_id, user_id=user.id).first()
    if not invoice: raise HTTPException(404, "Invoice not found")
    if status not in ("Cancelled", "Payment claimed", ""): raise HTTPException(400, "Unsupported status")
    invoice.status_override = status
    db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/invoices/{invoice_id}/remind")
def remind_now(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    invoice = db.query(Invoice).filter_by(id=invoice_id, user_id=user.id).first()
    if not invoice: raise HTTPException(404, "Invoice not found")
    if invoice_status(invoice) in ("Paid", "Cancelled", "Payment claimed") or invoice.client.opted_out:
        raise HTTPException(400, "Reminder is paused for this invoice/client.")
    step = (max([x.step_no for x in invoice.reminder_logs], default=0) + 1)
    tone = ["Friendly", "Polite", "Firm", "Final"][min(step - 1, 3)]
    days = max(0, (date.today() - invoice.due_date).days)
    message = generate_message(invoice, tone, days)
    log = ReminderLog(invoice_id=invoice.id, step_no=1000 + step, channel="demo", tone_level=tone, message_text=message, status="demo")
    db.add(log); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/invoices/{invoice_id}/delete")
def delete_invoice(invoice_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    invoice = db.query(Invoice).filter_by(id=invoice_id, user_id=user.id).first()
    if not invoice: raise HTTPException(404, "Invoice not found")
    db.delete(invoice); db.commit()
    return RedirectResponse("/", status_code=303)

@app.post("/clients/{client_id}/opt-out")
def opt_out(client_id: int, db: Session = Depends(get_db)):
    client = db.query(Client).filter_by(id=client_id).first()
    if not client: raise HTTPException(404, "Client not found")
    client.opted_out = True
    db.commit()
    return {"status": "opted_out"}

@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    messages = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [])
    results = []
    for msg in messages:
        text = msg.get("text", {}).get("body", "")
        phone = msg.get("from", "")
        client = db.query(Client).filter(Client.whatsapp_number == phone).first()
        if not client: continue
        classification = classify_reply(text)
        invoice = db.query(Invoice).filter(Invoice.client_id == client.id, Invoice.status_override.notin_(["Paid", "Cancelled"])).order_by(Invoice.due_date.asc()).first()
        if classification == "STOP":
            client.opted_out = True
        elif invoice:
            db.add(ClientReply(invoice_id=invoice.id, client_id=client.id, message_text=text, classification=classification))
            if classification == "payment_claimed":
                invoice.status_override = "Payment claimed"
                invoice.paused_until = date.today() + timedelta(days=3)
            elif classification in ("dispute", "other", "need_time"):
                invoice.paused_until = date.today() + timedelta(days=7)
        db.commit()
        results.append({"client": client.name, "classification": classification})
    return {"processed": results}

@app.post("/api/reminders/run")
def api_run_reminders(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    # Scope to the current user's invoices for this manual run.
    result = run_reminders(db, date.today())
    return JSONResponse(result)

@app.get("/health")
def health():
    return {"status": "ok", "service": "Invoice Chaser AI"}

@app.get("/api/invoices")
def api_invoices(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    invoices = db.query(Invoice).filter_by(user_id=user.id).all()
    return [{"id": i.id, "invoice_number": i.invoice_number, "client": i.client.name, "amount": i.amount,
             "paid": i.amount_paid, "balance": balance(i), "status": invoice_status(i), "due_date": i.due_date.isoformat()} for i in invoices]
