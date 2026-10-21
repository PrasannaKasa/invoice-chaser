from datetime import date, timedelta
from types import SimpleNamespace
from app.services import invoice_status, balance, classify_reply, fallback_message

def inv(due, amount=1000, paid=0, override=""):
    return SimpleNamespace(due_date=due, amount=amount, amount_paid=paid, status_override=override,
                           client=SimpleNamespace(name="Rohit"), invoice_number="INV-1", payment_link="")

def test_status_upcoming_due_soon_overdue():
    today = date(2026, 10, 21)
    assert invoice_status(inv(today + timedelta(days=10)), today) == "Upcoming"
    assert invoice_status(inv(today + timedelta(days=2)), today) == "Due Soon"
    assert invoice_status(inv(today - timedelta(days=1)), today) == "Overdue"

def test_payment_statuses():
    today = date(2026, 10, 21)
    assert invoice_status(inv(today - timedelta(days=2), paid=100), today) == "Partially Paid"
    assert invoice_status(inv(today - timedelta(days=2), paid=1000), today) == "Paid"
    assert invoice_status(inv(today, override="Cancelled"), today) == "Cancelled"

def test_classify_reply():
    assert classify_reply("STOP") == "STOP"
    assert classify_reply("I have paid") == "payment_claimed"
    assert classify_reply("This amount is wrong") == "dispute"

def test_message_contains_required_fields():
    invoice = inv(date(2026, 10, 25))
    text = fallback_message(invoice, "Friendly", 0)
    assert "INV-1" in text and "₹1,000.00" in text and "25 Oct 2026" in text
