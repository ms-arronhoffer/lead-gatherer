import time
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> int:
    return int(time.time())


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    total_places: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    processed_places: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    leads_found: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    job_leads: Mapped[list["JobLead"]] = relationship("JobLead", back_populates="job", cascade="all, delete-orphan")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    place_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    place_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    employee_count_min: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    employee_count_max: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revenue_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="new", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="google_places")
    enrichment_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scraped_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    emails: Mapped[list["LeadEmail"]] = relationship("LeadEmail", back_populates="lead", cascade="all, delete-orphan")
    contacts: Mapped[list["LeadContact"]] = relationship("LeadContact", back_populates="lead", cascade="all, delete-orphan")
    job_leads: Mapped[list["JobLead"]] = relationship("JobLead", back_populates="lead", cascade="all, delete-orphan")


class LeadEmail(Base):
    __tablename__ = "lead_emails"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="emails")

    __table_args__ = (
        UniqueConstraint("lead_id", "email_normalized", name="uq_lead_email_normalized"),
    )


class LeadContact(Base):
    __tablename__ = "lead_contacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="contacts")


class JobLead(Base):
    __tablename__ = "job_leads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)

    job: Mapped["Job"] = relationship("Job", back_populates="job_leads")
    lead: Mapped["Lead"] = relationship("Lead", back_populates="job_leads")

    __table_args__ = (
        UniqueConstraint("job_id", "lead_id", name="uq_job_lead"),
    )
