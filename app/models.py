from datetime import date, datetime
from sqlalchemy import String, Integer, Float, Date, DateTime, Boolean, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    business_name: Mapped[str] = mapped_column(String(180), default="My Business")
    payment_info: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    clients: Mapped[list["Client"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    company: Mapped[str] = mapped_column(String(180), default="")
    whatsapp_number: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    preferred_channel: Mapped[str] = mapped_column(String(20), default="demo")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="clients")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="client", cascade="all, delete-orphan")

class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[float] = mapped_column(Float)
    amount_paid: Mapped[float] = mapped_column(Float, default=0)
    issue_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date] = mapped_column(Date)
    status_override: Mapped[str] = mapped_column(String(30), default="")
    payment_link: Mapped[str] = mapped_column(String(500), default="")
    paused_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    client: Mapped["Client"] = relationship(back_populates="invoices")
    user: Mapped["User"] = relationship(back_populates="invoices")
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    reminder_logs: Mapped[list["ReminderLog"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    replies: Mapped[list["ClientReply"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")

class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    paid_on: Mapped[date] = mapped_column(Date, default=date.today)
    note: Mapped[str] = mapped_column(String(255), default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invoice: Mapped["Invoice"] = relationship(back_populates="payments")

class ReminderLog(Base):
    __tablename__ = "reminder_logs"
    __table_args__ = (UniqueConstraint("invoice_id", "step_no", name="uq_invoice_reminder_step"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20), default="demo")
    tone_level: Mapped[str] = mapped_column(String(20))
    message_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="sent")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invoice: Mapped["Invoice"] = relationship(back_populates="reminder_logs")

class ClientReply(Base):
    __tablename__ = "client_replies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    message_text: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(40), default="other")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invoice: Mapped["Invoice"] = relationship(back_populates="replies")
