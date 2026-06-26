import time
from typing import Any

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> int:
    return int(time.time())


lead_tags = Table(
    "lead_tags",
    Base.metadata,
    Column("lead_id", String(64), ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(64), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


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
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    attempt: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
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
    phone_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
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
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    last_touched_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    last_touched_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    score: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # Split scores: fit = ICP match quality, intent = buying-signal strength,
    # priority = freshness-decayed blend used for ranking + hot-lead alerts.
    fit_score: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    intent_score: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    priority_score: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    matched_segment_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_generated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fit_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    fit_reasons_generated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    emails: Mapped[list["LeadEmail"]] = relationship("LeadEmail", back_populates="lead", cascade="all, delete-orphan")
    contacts: Mapped[list["LeadContact"]] = relationship("LeadContact", back_populates="lead", cascade="all, delete-orphan")
    job_leads: Mapped[list["JobLead"]] = relationship("JobLead", back_populates="lead", cascade="all, delete-orphan")
    activities: Mapped[list["LeadActivity"]] = relationship(
        "LeadActivity", back_populates="lead", cascade="all, delete-orphan",
        order_by="desc(LeadActivity.created_at)",
    )
    signals: Mapped[list["LeadSignal"]] = relationship(
        "LeadSignal", back_populates="lead", cascade="all, delete-orphan",
        order_by="desc(LeadSignal.detected_at)", lazy="selectin",
    )
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to_user_id])
    last_touched_by: Mapped["User | None"] = relationship("User", foreign_keys=[last_touched_by_user_id])
    tags: Mapped[list["Tag"]] = relationship("Tag", secondary=lead_tags, back_populates="leads", lazy="selectin")


class LeadEmail(Base):
    __tablename__ = "lead_emails"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(256), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)
    mx_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    role_based: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    disposable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    smtp_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    validated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(48), nullable=True)
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


class Webhook(Base):
    __tablename__ = "webhooks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    webhook_id: Mapped[str] = mapped_column(String(64), ForeignKey("webhooks.id"), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempt: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status_code: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    delivered_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)

    webhook: Mapped["Webhook"] = relationship("Webhook", back_populates="deliveries")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entra_oid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    last_seen_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[int] = mapped_column(BigInteger, nullable=False, default=50)
    rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    leads: Mapped[list["Lead"]] = relationship("Lead", secondary=lead_tags, back_populates="tags")


class LeadActivity(Base):
    __tablename__ = "lead_activities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")
    user: Mapped["User | None"] = relationship("User")


class LeadSignal(Base):
    """A first-class buying/intent signal attached to a lead.

    Signals are emitted by the buying-signal layer (web visits, news/press
    classification, future web-monitoring jobs) and feed the lead's
    ``intent_score``. Keeping them as their own rows makes them queryable,
    auditable, and individually weightable.
    """
    __tablename__ = "lead_signals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    # e.g. funding_round, leadership_hire, expansion, product_launch, layoffs,
    # m_and_a, hiring, web_visit
    type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # Points this signal contributes toward intent_score (before recency decay).
    strength: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Where the signal came from, e.g. news, visitor_pixel, manual.
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # Optional stable key used to dedupe repeat detections of the same event.
    dedupe_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    detected_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="signals")

    __table_args__ = (
        UniqueConstraint("lead_id", "type", "dedupe_key", name="uq_lead_signal_dedupe"),
    )


class LeadCandidate(Base):
    """Staging tier — non-Lead discoveries waiting on human review.

    Sources: url_harvester (LLM-extracted from search), visitor_pixel (resolved
    from anonymous web traffic), and any future low-confidence pipeline.
    """
    __tablename__ = "lead_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_fit_score: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    discovered_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)
    reviewed_by_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    promoted_lead_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("leads.id"), nullable=True)

    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_user_id])

    __table_args__ = (
        UniqueConstraint("source", "source_ref", name="uq_candidate_source_ref"),
    )


class VisitorEvent(Base):
    """Raw hit recorded by the first-party pixel."""
    __tablename__ = "visitor_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    anonymous_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)
    resolved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolved_company: Mapped[str | None] = mapped_column(String(256), nullable=True)


class Sequence(Base):
    """Outbound sequence template. Steps is a list of step dicts."""
    __tablename__ = "sequences"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, onupdate=_now)

    owner: Mapped["User | None"] = relationship("User")
    enrollments: Mapped[list["SequenceEnrollment"]] = relationship(
        "SequenceEnrollment", back_populates="sequence", cascade="all, delete-orphan"
    )


class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    sequence_id: Mapped[str] = mapped_column(String(64), ForeignKey("sequences.id"), nullable=False, index=True)
    enrolled_by_user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    step_idx: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enrolled", index=True)
    next_send_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    lead: Mapped["Lead"] = relationship("Lead")
    sequence: Mapped["Sequence"] = relationship("Sequence", back_populates="enrollments")
    enrolled_by: Mapped["User"] = relationship("User")
    messages: Mapped[list["OutboundMessage"]] = relationship(
        "OutboundMessage", back_populates="enrollment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("lead_id", "sequence_id", name="uq_lead_sequence"),
    )


class OutboundMessage(Base):
    __tablename__ = "outbound_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(String(64), ForeignKey("sequence_enrollments.id"), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    step_idx: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    to_email: Mapped[str] = mapped_column(String(256), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    sent_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    graph_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    graph_conversation_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    reply_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    bounce_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=_now, index=True)

    enrollment: Mapped["SequenceEnrollment"] = relationship("SequenceEnrollment", back_populates="messages")
