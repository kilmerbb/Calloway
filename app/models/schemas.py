"""Pydantic models for all data types in the Solo Realtor AI system."""
from datetime import datetime, date, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# Core Data Models (mirror database tables)
# ============================================================

class AgentConfig(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    brokerage: str | None = None
    market: str | None = None
    timezone: str = "America/New_York"
    twilio_number: str
    google_oauth: dict | None = None
    vapi_assistant: str | None = None
    scheduling_prefs: dict = Field(default_factory=dict)
    style_profile: dict = Field(default_factory=dict)
    autonomy_rules: dict = Field(default_factory=dict)
    listing_rules: dict = Field(default_factory=dict)
    system_prompt: str | None = None
    google_review_link: str | None = None
    briefing_time: time = time(7, 30)
    current_status: str = "available"
    status_until: datetime | None = None
    voice_daily_cap_minutes: int = 30
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Contact(BaseModel):
    id: UUID
    agent_id: UUID
    name: str
    phone: str
    email: str | None = None
    role: str = "lead"
    lifecycle_stage: str = "new_lead"
    linked_listing_id: UUID | None = None
    preferences: dict = Field(default_factory=dict)
    notes: str | None = None
    last_contact_at: datetime | None = None
    silent_mode: bool = False
    consent_status: str = "pending"
    consent_granted_at: datetime | None = None
    consent_revoked_at: datetime | None = None
    consent_method: str | None = None
    consent_message: str | None = None
    consent_response: str | None = None
    lead_source: str | None = None
    language_detected: str = "en"
    interaction_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LeadPreferences(BaseModel):
    contact_id: UUID
    areas: list[str] | None = None
    timeline: str | None = None
    preapproved: bool | None = None
    property_type: str | None = None
    bedrooms_min: int | None = None
    bathrooms_min: Decimal | None = None
    price_min: int | None = None
    price_max: int | None = None


class Listing(BaseModel):
    id: UUID
    agent_id: UUID
    address: str
    price: int
    beds: int | None = None
    baths: Decimal | None = None
    sqft: int | None = None
    hoa: int | None = None
    features: list[str] = Field(default_factory=list)
    showing_instructions: str | None = None
    lockbox: str | None = None
    access_rules: dict = Field(default_factory=dict)
    open_house_dates: list[dict] = Field(default_factory=list)
    list_date: date | None = None
    status: str = "active"
    notes: str | None = None
    last_updated_at: datetime | None = None
    created_at: datetime | None = None
    freshness_warning: str | None = None


class Conversation(BaseModel):
    id: UUID
    agent_id: UUID
    contact_id: UUID | None = None
    channel: str
    stage: str = "open"
    active_handler: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None


class Message(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    conversation_id: UUID
    sender_type: str
    body: str
    intent: str | None = None
    ai_generated: bool = False
    model_used: str | None = None
    tokens_used: int | None = None
    provider_message_id: str | None = None
    delivery_status: str = "pending"
    delivered_at: datetime | None = None
    failure_reason: str | None = None
    feedback_score: int | None = None
    created_at: datetime | None = None


class Showing(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    contact_id: UUID
    listing_id: UUID
    start_time: datetime
    end_time: datetime
    status: str = "hold"
    hold_expires_at: datetime | None = None
    calendar_event_id: str | None = None
    requesting_agent_id: UUID | None = None
    feedback: str | None = None
    created_at: datetime | None = None


class Trigger(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    entity_type: str
    entity_id: UUID
    trigger_type: str
    scheduled_at: datetime
    recurrence: str | None = None
    action_type: str
    message_template: str | None = None
    autonomy_level: str = "ask_agent"
    status: str = "pending"
    notes: str | None = None
    created_at: datetime | None = None


class Transaction(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    contact_id: UUID
    listing_id: UUID | None = None
    transaction_type: str = "purchase"
    status: str = "pending_offer"
    offer_price: int | None = None
    final_price: int | None = None
    offer_date: date | None = None
    contract_date: date | None = None
    closing_date: date | None = None
    inspection_date: date | None = None
    appraisal_date: date | None = None
    financing_deadline: date | None = None
    earnest_money: int | None = None
    commission_pct: Decimal | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DripCampaign(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    name: str
    description: str | None = None
    trigger_type: str = "nurture"
    steps: list[dict] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None


class DripEnrollment(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    campaign_id: UUID
    contact_id: UUID
    current_step: int = 0
    status: str = "active"
    enrolled_at: datetime | None = None
    completed_at: datetime | None = None
    paused_at: datetime | None = None


class ConversationSummary(BaseModel):
    id: UUID | None = None
    tenant_id: UUID
    contact_id: UUID
    conversation_id: UUID
    summary_text: str
    messages_summarized_count: int = 0
    last_message_id: UUID | None = None
    token_estimate: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Email(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    from_address: str | None = None
    to_address: str | None = None
    subject: str | None = None
    body: str | None = None
    received_at: datetime | None = None
    classification: str | None = None
    linked_contact_id: UUID | None = None
    linked_listing_id: UUID | None = None
    action_taken: str | None = None
    created_at: datetime | None = None


class ToolExecution(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    conversation_id: UUID | None = None
    tool_name: str
    input_json: dict
    output_json: dict | None = None
    status: str
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: datetime | None = None


class UsageMetrics(BaseModel):
    id: UUID | None = None
    agent_id: UUID
    date: date
    messages_sent: int = 0
    messages_received: int = 0
    llm_calls: int = 0
    llm_tokens_used: int = 0
    llm_cost_cents: int = 0
    voice_minutes: Decimal = Decimal("0")
    sms_segments_sent: int = 0
    sms_segments_received: int = 0
    sms_cost_cents: int = 0
    voice_cost_cents: int = 0
    showings_booked: int = 0
    triggers_fired: int = 0


# ============================================================
# Pipeline Models
# ============================================================

class NormalizedEvent(BaseModel):
    sender_phone: str
    sender_name: str | None = None
    channel: Literal["rcs", "sms", "sms_command", "vapi", "email", "portal"]
    body: str
    timestamp: datetime
    provider_message_id: str
    raw_payload: dict
    agent_id: UUID


class IntentClassification(BaseModel):
    intent: Literal[
        "scheduling", "listing_qa", "lead_qualification",
        "agent_command", "transaction", "personal", "escalation", "noise",
        "feedback"
    ]
    sender_type: Literal[
        "known_client", "known_agent", "unknown_listing_inquiry",
        "unknown_general", "agent_command"
    ]
    confidence: float
    needs_full_context: bool
    language_code: str = "en"


class AssembledContext(BaseModel):
    agent: AgentConfig
    contact: Contact | None = None
    listings: list[Listing] = Field(default_factory=list)
    calendar_slots: list[dict] | None = None
    triggers: list[Trigger] = Field(default_factory=list)
    conversation_history: list[Message] = Field(default_factory=list)
    conversation_summary: str | None = None
    intent: IntentClassification


class AgentDecision(BaseModel):
    response_text: str | None = None
    tool_calls: list[dict] = Field(default_factory=list)
    triggers_to_create: list[dict] = Field(default_factory=list)
    notifications: list[dict] = Field(default_factory=list)
    model_used: str = "template"
    tokens_used: int = 0
