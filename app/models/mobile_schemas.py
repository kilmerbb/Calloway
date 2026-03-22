"""Pydantic models for mobile API request/response schemas."""
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# Auth
# ============================================================

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    agent: "AgentProfile"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AgentProfile(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str
    brokerage: str | None = None
    market: str | None = None
    timezone: str = "America/New_York"


# ============================================================
# Briefing
# ============================================================

class BriefingShowing(BaseModel):
    time: str
    client: str
    address: str
    status: str


class BriefingTrigger(BaseModel):
    type: str
    message: str
    time: str


class BriefingGap(BaseModel):
    name: str
    days: int
    action: str


class BriefingNewLead(BaseModel):
    name: str
    phone: str


class BriefingDomAlert(BaseModel):
    address: str
    dom: int
    price: int


class BriefingResponse(BaseModel):
    greeting: str
    date: str
    summary_bullets: list[str] = Field(default_factory=list)
    showings_today: list[BriefingShowing] = Field(default_factory=list)
    triggers_today: list[BriefingTrigger] = Field(default_factory=list)
    gaps: list[BriefingGap] = Field(default_factory=list)
    new_leads: list[BriefingNewLead] = Field(default_factory=list)
    dom_alerts: list[BriefingDomAlert] = Field(default_factory=list)


# ============================================================
# Schedule
# ============================================================

class ScheduleEvent(BaseModel):
    id: UUID
    type: str  # "showing" or "trigger"
    title: str
    subtitle: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    status: str
    location: str | None = None
    contact_name: str | None = None
    listing_address: str | None = None


class ScheduleResponse(BaseModel):
    date: str
    events: list[ScheduleEvent] = Field(default_factory=list)
    total_count: int = 0


class ShowingDetailResponse(BaseModel):
    id: UUID
    contact_name: str
    contact_phone: str
    listing_address: str
    listing_price: int | None = None
    start_time: datetime
    end_time: datetime
    status: str
    lockbox: str | None = None
    showing_instructions: str | None = None
    feedback: str | None = None
    calendar_event_id: str | None = None
    created_at: datetime | None = None


# ============================================================
# Conversations
# ============================================================

class ConversationListItem(BaseModel):
    id: UUID
    contact_id: UUID | None = None
    contact_name: str
    contact_phone: str | None = None
    channel: str
    last_message_body: str | None = None
    last_message_at: datetime | None = None
    last_message_sender: str | None = None
    unread_count: int = 0
    active_handler: str | None = None
    stage: str = "open"


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem] = Field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20


class ConversationDetail(BaseModel):
    id: UUID
    contact_id: UUID | None = None
    contact_name: str
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_role: str | None = None
    contact_lifecycle_stage: str | None = None
    channel: str
    stage: str
    active_handler: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None


class MessageItem(BaseModel):
    id: UUID
    sender_type: str
    body: str
    ai_generated: bool = False
    model_used: str | None = None
    intent: str | None = None
    created_at: datetime | None = None


class MessageListResponse(BaseModel):
    messages: list[MessageItem] = Field(default_factory=list)
    cursor: str | None = None  # ISO timestamp of last message for cursor pagination
    has_more: bool = False


class SendMessageRequest(BaseModel):
    body: str


class SendMessageResponse(BaseModel):
    message_id: UUID | None = None
    status: str
    twilio_sid: str | None = None


class UnreadCountResponse(BaseModel):
    unread_count: int = 0


# ============================================================
# Listings
# ============================================================

class CreateListingRequest(BaseModel):
    address: str
    price: int
    beds: int | None = None
    baths: Decimal | None = None
    sqft: int | None = None
    hoa: int | None = None
    features: list[str] = Field(default_factory=list)
    showing_instructions: str | None = None
    lockbox: str | None = None
    notes: str | None = None
    description: str | None = None  # free-text for AI parsing (V2)


class UpdateListingRequest(BaseModel):
    address: str | None = None
    price: int | None = None
    beds: int | None = None
    baths: Decimal | None = None
    sqft: int | None = None
    hoa: int | None = None
    features: list[str] | None = None
    showing_instructions: str | None = None
    lockbox: str | None = None
    status: str | None = None
    notes: str | None = None


class ListingListItem(BaseModel):
    id: UUID
    address: str
    price: int
    beds: int | None = None
    baths: Decimal | None = None
    sqft: int | None = None
    status: str = "active"
    list_date: date | None = None
    dom: int | None = None  # days on market, computed
    created_at: datetime | None = None


class ListingResponse(BaseModel):
    id: UUID
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
    dom: int | None = None
    freshness_warning: str | None = None
    last_updated_at: datetime | None = None
    created_at: datetime | None = None


class ListingListResponse(BaseModel):
    listings: list[ListingListItem] = Field(default_factory=list)
    total_count: int = 0
