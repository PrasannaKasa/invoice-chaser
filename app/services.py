from datetime import date, timedelta, datetime
import os, re
import httpx
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.config import GROQ_API_KEY, GROQ_MODEL, WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_API_VERSION
from app.models import Invoice, ReminderLog, Client, Payment, ClientReply

SCHEDULE = [(-3, "Friendly"), (0, "Friendly"), (3, "Polite"), (7, "Firm"), (14, "Final")]

def invoice_status(invoice: Invoice, today: date | None = None) -> str:
    today = today or date.today()
    if invoice.status_override in ("Paid", "Cancelled", "Payment claimed"):
        return invoice.status_override
    balance = max(0, round(invoice.amount - invoice.amount_paid, 2))
    if balance <= 0:
        return "Paid"
    if invoice.amount_paid > 0:
        return "Partially Paid"
    if today < invoice.due_date - timedelta(days=3):
        return "Upcoming"
    if today <= invoice.due_date:
        return "Due Soon"
    return "Overdue"

def balance(invoice: Invoice) -> float:
    return round(max(0, invoice.amount - invoice.amount_paid), 2)

def fallback_message(invoice: Invoice, tone: str, days_overdue: int) -> str:
    client = invoice.client.name
    amount = f"₹{balance(invoice):,.2f}"
    number = invoice.invoice_number
    due = invoice.due_date.strftime("%d %b %Y")
    payment = f" Payment details: {invoice.payment_link}." if invoice.payment_link else ""
    if tone == "Friendly":
        body = f"Just a friendly reminder that invoice {number} for {amount} is due on {due}."
    elif tone == "Polite":
        body = f"Our records show invoice {number} for {amount}, due on {due}, is still pending. Could you please share the payment status?"
    elif tone == "Firm":
        body = f"Invoice {number} for {amount}, due on {due}, is {days_overdue} days overdue. Kindly arrange payment or let us know your expected payment date."
    else:
        body = f"This is a final reminder for invoice {number} for {amount}, due on {due}. Please arrange payment or contact us to discuss."
    return f"Hi {client}, {body}{payment} If you have already paid, please ignore this message. Reply STOP to opt out."

def generate_message(invoice: Invoice, tone: str, days_overdue: int) -> str:
    template = fallback_message(invoice, tone, days_overdue)
    if not GROQ_API_KEY:
        return template
    prompt = (
        "Rewrite this invoice reminder professionally. Never threaten, shame, or claim legal action. "
        "Keep exact invoice number, amount, and due date. Return only the message.\n"
        f"Required invoice number: {invoice.invoice_number}\nRequired amount: ₹{balance(invoice):,.2f}\n"
        f"Required due date: {invoice.due_date.strftime('%d %b %Y')}\nTone: {tone}\nTemplate: {template}"
    )
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=15,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]["content"].strip()
        required = [invoice.invoice_number, f"₹{balance(invoice):,.2f}", invoice.due_date.strftime("%d %b %Y")]
        if all(x in message for x in required):
            return message
    except Exception:
        pass
    return template

def classify_reply(message: str) -> str:
    value = message.strip().lower()
    if value in {"stop", "unsubscribe", "cancel"} or "stop messaging" in value:
        return "STOP"
    if any(x in value for x in ["dispute", "wrong amount", "incorrect", "not agreed", "not correct"]):
        return "dispute"
    if any(x in value for x in ["paid", "payment done", "sent payment", "transferred"]):
        return "payment_claimed"
    if any(x in value for x in ["more time", "delay", "later", "extension"]):
        return "need_time"
    if "will pay" in value or "pay on" in value or "by friday" in value or "by monday" in value:
        return "promise_date"
    return "other"

def send_whatsapp(client: Client, message: str) -> str:
    if client.opted_out:
        return "skipped_opted_out"
    if not client.consent:
        return "skipped_no_consent"
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID or not client.whatsapp_number:
        return "demo"
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": client.whatsapp_number, "type": "text", "text": {"body": message}}
    try:
        response = httpx.post(url, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}, json=payload, timeout=20)
        response.raise_for_status()
        return "sent"
    except Exception:
        return "failed"

def run_reminders(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    sent, skipped = 0, 0
    invoices = db.query(Invoice).all()
    for invoice in invoices:
        status = invoice_status(invoice, today)
        if status in ("Paid", "Cancelled", "Payment claimed") or balance(invoice) <= 0:
            skipped += 1
            continue
        if invoice.paused_until and today <= invoice.paused_until:
            skipped += 1
            continue
        client = invoice.client
        if client.opted_out:
            skipped += 1
            continue
        for step_no, (offset, tone) in enumerate(SCHEDULE, start=1):
            target_date = invoice.due_date + timedelta(days=offset)
            if target_date != today:
                continue
            if db.query(ReminderLog).filter_by(invoice_id=invoice.id, step_no=step_no).first():
                continue
            days_overdue = max(0, (today - invoice.due_date).days)
            message = generate_message(invoice, tone, days_overdue)
            channel_status = send_whatsapp(client, message)
            if channel_status.startswith("skipped"):
                skipped += 1
                continue
            log = ReminderLog(invoice_id=invoice.id, step_no=step_no, channel="whatsapp" if channel_status == "sent" else "demo",
                              tone_level=tone, message_text=message, status=channel_status)
            db.add(log)
            try:
                db.commit()
                sent += 1
            except IntegrityError:
                db.rollback()
    return {"processed": sent, "skipped": skipped}

def record_payment(db: Session, invoice: Invoice, amount: float, paid_on: date, note: str = ""):
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    if amount > balance(invoice) + 0.0001:
        raise ValueError("Payment cannot exceed the remaining balance.")
    payment = Payment(invoice_id=invoice.id, amount=amount, paid_on=paid_on, note=note)
    invoice.amount_paid = round(invoice.amount_paid + amount, 2)
    if balance(invoice) <= 0:
        invoice.status_override = "Paid"
    else:
        invoice.status_override = ""
    db.add(payment)
    db.commit()
    db.refresh(invoice)
    return payment

def recovered_total(db: Session, user_id: int, month_only: bool = False) -> float:
    today = date.today()
    start = today.replace(day=1)
    total = 0.0
    invoices = db.query(Invoice).filter(Invoice.user_id == user_id).all()
    for inv in invoices:
        if not inv.payments or not inv.reminder_logs:
            continue
        first_reminder = min(log.sent_at.date() for log in inv.reminder_logs if log.status in ("sent", "demo")) if any(log.status in ("sent", "demo") for log in inv.reminder_logs) else None
        if not first_reminder:
            continue
        for p in inv.payments:
            if p.paid_on >= first_reminder and (not month_only or p.paid_on >= start):
                total += p.amount
    return round(total, 2)
