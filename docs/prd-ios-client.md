# PRD: Calloway iOS Client App — V1

**Author:** Mara, Product Manager
**Date:** 2026-03-22
**Status:** Draft
**Version:** 1.0

---

## 1. Overview & Goals

Calloway's iOS client gives solo real estate agents a mobile command center for their AI-powered assistant. V1 delivers three core capabilities: a daily briefing with schedule, conversation monitoring with takeover, and a content portal for new listing intake.

### Goals

1. **Reduce time-to-action** — Agent sees what the assistant did overnight and what's on the calendar within 5 seconds of opening the app.
2. **Enable supervision on the go** — Agent can review AI-handled conversations, read message history, and take over a thread from their phone.
3. **Streamline listing intake** — Agent can input new listing details from a showing without switching to a desktop.
4. **Drive daily engagement** — The briefing screen is the natural "open the app" hook each morning.

### Success Metrics

- Daily active usage rate > 70% of subscribed agents
- Average session length: 2–4 minutes (quick check-in pattern)
- Conversation takeover used at least 1x/week per agent
- Listing created via mobile at least 1x/month per agent

---

## 2. User Stories

### Daily Briefing

| ID | Story | Acceptance Criteria |
|----|-------|-------------------|
| US-001 | As an agent, I want to see a personalized greeting and date so I feel oriented when I open the app. | Shows agent's first name, current date formatted as weekday + month + day. |
| US-002 | As an agent, I want to see a summary of what my AI assistant did since my last session so I know what happened overnight. | Purple gradient card lists 3–5 bullet points of recent assistant actions (leads qualified, follow-ups scheduled, messages sent). |
| US-003 | As an agent, I want to see today's schedule so I know where I need to be. | Schedule section shows event count badge and cards for each event with time, type, address, and contact name. |
| US-004 | As an agent, I want to tap an event card to see its details so I can prepare for the appointment. | Tapping a schedule card navigates to an event detail view (V1: deep link to calendar or simple detail sheet). |
| US-005 | As an agent, I want to tap "View All Chats" to jump to the chats screen. | Button navigates to the Assistant Chats tab. |

### Assistant Chats

| ID | Story | Acceptance Criteria |
|----|-------|-------------------|
| US-006 | As an agent, I want to see all conversations my assistant is handling so I can monitor communication. | List shows all conversations sorted by most recent message, with contact name, avatar, timestamp, and message preview. |
| US-007 | As an agent, I want to filter chats by unread or bot-handled so I can focus on what needs attention. | Filter chips for "All Chats", "Unread", and "Bot Handled" filter the list in place. |
| US-008 | As an agent, I want to search conversations by contact name or message content. | Search bar filters conversation list as the agent types. |
| US-009 | As an agent, I want to see an unread count badge so I know which conversations have new messages. | Purple badge with count appears on cards with unread messages. |

### Chat Detail

| ID | Story | Acceptance Criteria |
|----|-------|-------------------|
| US-010 | As an agent, I want to read the full message history of a conversation so I have context before responding. | Shows all messages in chronological order with sender type (contact, assistant, agent), timestamps, and bubble styling. |
| US-011 | As an agent, I want to see that the assistant is monitoring a thread so I know it's being handled. | Amber banner at bottom reads "Assistant is actively monitoring this thread." when `active_handler = 'assistant'`. |
| US-012 | As an agent, I want to take over a conversation by sending a message so the assistant stops auto-responding. | Typing and sending a message sets `active_handler = 'agent'` and sends the message via the backend. Banner updates accordingly. |
| US-013 | As an agent, I want to see which messages were sent by the assistant vs. the contact so I can follow the thread. | Assistant messages show "ASSISTANT" label in purple, left-aligned on dark card. Contact messages are right-aligned in purple. Agent messages are right-aligned in a distinct style. |

### Content Portal

| ID | Story | Acceptance Criteria |
|----|-------|-------------------|
| US-014 | As an agent, I want to input a new listing's details (address, price, beds/baths, description) from my phone. | Form with fields for address (text), price (currency), beds/baths (text), and description (multiline). Validates required fields before submit. |
| US-015 | As an agent, I want to upload photos for a listing so the assistant can use them in marketing. | Media upload section accepts photos from camera roll or camera. Stored and associated with the listing. |
| US-016 | As an agent, I want to toggle between "New Listing" and "My Content" tabs so I can review existing listings. | Tab toggle switches between the creation form and a list of the agent's active listings. |

### Navigation

| ID | Story | Acceptance Criteria |
|----|-------|-------------------|
| US-017 | As an agent, I want a bottom tab bar so I can quickly switch between Briefing, Chats, and Content. | Three tabs: Briefing (calendar grid icon), Chats (speech bubble icon), Content (image icon). Active tab highlighted in purple. |
| US-018 | As an agent, I want the Chats tab to show an unread badge so I know there are new messages without switching tabs. | Chats tab icon shows aggregate unread count badge. |

---

## 3. Screen-by-Screen Feature Specs

### 3.1 Daily Briefing

**Route:** Default/home screen (Briefing tab)

| Element | Spec |
|---------|------|
| Header | "Daily Briefing" — static title |
| Date | Formatted: `SATURDAY, MARCH 21ST` — uppercase weekday, month, ordinal day |
| Greeting | "Good morning/afternoon/evening, {agent.first_name}." — time-of-day aware |
| Assistant Summary | Purple gradient card. Bulleted list of 3–5 recent assistant actions from the last 24 hours. Data source: tool_executions + messages where ai_generated = true, grouped and summarized by the backend. |
| View All Chats | Button navigates to Chats tab |
| Today's Schedule | Section header with event count badge ("3 events"). List of event cards. |
| Event Card | Time (HH:MM), event type (Showing, Appraisal, etc.), address with pin icon, contact name with calendar icon, chevron for detail. |

**Pull-to-refresh:** Reloads briefing and schedule data.

### 3.2 Today's Schedule (scrolled state)

Same screen as 3.1 — the schedule section is below the fold. The event list scrolls vertically. No separate screen needed; this is the scrolled state of the briefing.

### 3.3 Assistant Chats

**Route:** Chats tab

| Element | Spec |
|---------|------|
| Header | "Assistant Chats" — static title |
| Search | Text field, placeholder "Search conversations...", filters on contact name and message body |
| Filter chips | "All Chats" (default active), "Unread", "Bot Handled". Single-select. Active chip: purple fill + white text. Inactive: outlined. |
| Conversation card | Avatar (photo URL or colored initials circle), contact name, relative timestamp ("8 minutes ago"), bot icon + last message preview (truncated to 2 lines), unread badge (purple circle + count), green dot if contact was active in last 15 min. |
| Sort | By `last_message_at` descending |
| Tap action | Navigate to Chat Detail |

**Pagination:** Infinite scroll, 25 conversations per page.

### 3.4 Chat Detail

**Route:** Push from Chats list

| Element | Spec |
|---------|------|
| Header | Back arrow, contact avatar, contact name, subtitle showing handler status ("Assistant handling" / "You're handling"), phone + video call action icons (V1: phone icon initiates tel: link, video icon is placeholder/disabled). |
| Message list | Scrollable, chronological. Contact messages: purple bubble, right-aligned. Assistant messages: dark card, left-aligned, "ASSISTANT" label in purple above body. Agent messages: blue/indigo bubble, right-aligned. Timestamps below each message. |
| Monitoring banner | Amber/orange bar: "Assistant is actively monitoring this thread." Shown when `active_handler = 'assistant'`. Hidden when agent has taken over. |
| Input | Text field with placeholder "Take over conversation...", send button (purple). Sending a message: POST to backend, sets `active_handler = 'agent'`, appends message to thread. |
| Real-time updates | Poll every 5 seconds for new messages while on this screen. (V1: polling. V2: WebSocket.) |

### 3.5 Content Portal

**Route:** Content tab

| Element | Spec |
|---------|------|
| Header | "Content Portal" — static title |
| Tab toggle | "New Listing" (default active) / "My Content". Segmented control style. |
| New Listing form | ADDRESS: text input, required. PRICE: currency input (numeric keyboard, formatted as $X,XXX). BEDS/BATHS: text input, placeholder "e.g. 3B/2B". DESCRIPTION: multiline textarea. All fields map to the `listings` table. |
| Upload Media | Section below form. Tap to select from photo library or take photo. Show thumbnail grid of selected media. V1: upload to backend storage (S3/Supabase Storage). |
| Submit | "Create Listing" button. Validates required fields (address, price). POSTs to backend. Shows success confirmation. |
| My Content tab | List of agent's active listings. Each card shows address, price, beds/baths, status. Tap to view/edit. |

### 3.6 Bottom Tab Bar

| Tab | Icon | Badge |
|-----|------|-------|
| Briefing | Calendar grid | None |
| Chats | Speech bubble | Unread message count |
| Content | Landscape/image | None |

Active tab: purple icon + label. Inactive: gray.

---

## 4. API Endpoints Needed

The iOS app will call a new set of mobile-facing REST endpoints. These sit alongside the existing console API but are authenticated via agent JWT (not operator auth).

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/mobile/auth/login` | Email + password or magic link. Returns JWT. |
| POST | `/api/mobile/auth/refresh` | Refresh expired JWT. |
| POST | `/api/mobile/auth/device` | Register APNs device token for push notifications. |

### Briefing

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mobile/briefing` | Returns greeting, assistant summary bullets, today's schedule events. Query: `date` (defaults to today in agent's timezone). |

### Schedule

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mobile/schedule` | Returns events for a date range. Query: `start_date`, `end_date`. Sources: showings table + Google Calendar sync. |
| GET | `/api/mobile/schedule/{event_id}` | Event detail (showing or calendar event). |

### Conversations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mobile/conversations` | Paginated conversation list. Query: `page`, `per_page`, `filter` (all/unread/bot_handled), `search`. |
| GET | `/api/mobile/conversations/{conversation_id}` | Conversation detail with contact info and handler status. |
| GET | `/api/mobile/conversations/{conversation_id}/messages` | Paginated messages. Query: `before` (cursor), `limit`. |
| POST | `/api/mobile/conversations/{conversation_id}/messages` | Send a message (agent takeover). Body: `{ "body": "..." }`. Side effect: sets `active_handler = 'agent'`. |
| GET | `/api/mobile/conversations/unread-count` | Returns total unread count for tab badge. |

### Listings / Content

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/mobile/listings` | Agent's listings. Query: `status`, `page`, `per_page`. |
| POST | `/api/mobile/listings` | Create a new listing. Body: address, price, beds, baths, description. |
| GET | `/api/mobile/listings/{listing_id}` | Listing detail. |
| PUT | `/api/mobile/listings/{listing_id}` | Update listing. |
| POST | `/api/mobile/listings/{listing_id}/media` | Upload media files. Multipart form data. |

### Push Notifications

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/mobile/notifications/preferences` | Agent's notification preferences. |

---

## 5. Data Models

### Briefing Response

```json
{
  "date": "2026-03-22",
  "greeting": "Good morning, Alex.",
  "assistant_summary": [
    "Qualified 3 new leads from Zillow.",
    "Scheduled a follow-up call with John Doe for Friday.",
    "Sent property details of '123 Maple St' to 5 interested buyers."
  ],
  "schedule": {
    "event_count": 3,
    "events": [
      {
        "id": "uuid",
        "start_time": "2026-03-22T10:00:00-04:00",
        "end_time": "2026-03-22T10:45:00-04:00",
        "type": "showing",
        "address": "123 Maple Street",
        "contact_name": "Sarah Jenkins",
        "listing_id": "uuid"
      }
    ]
  }
}
```

### Conversation List Item

```json
{
  "id": "uuid",
  "contact": {
    "id": "uuid",
    "name": "John Doe",
    "phone": "+1234567890",
    "avatar_url": null,
    "initials": "JD",
    "initials_color": "#7C3AED"
  },
  "last_message": {
    "body": "Thanks, I'll be there at 10.",
    "sender_type": "contact",
    "ai_generated": false,
    "created_at": "2026-03-22T09:15:00Z"
  },
  "active_handler": "assistant",
  "unread_count": 2,
  "last_message_at": "2026-03-22T09:15:00Z"
}
```

### Message

```json
{
  "id": "uuid",
  "body": "Hi, I'm interested in the Maple St property.",
  "sender_type": "contact",
  "ai_generated": false,
  "created_at": "2026-03-22T09:12:00Z"
}
```

`sender_type` values: `"contact"`, `"assistant"`, `"agent"`

### Listing (Create Request)

```json
{
  "address": "123 Maple Street",
  "price": 450000,
  "beds": 3,
  "baths": 2.0,
  "description": "Property features and highlights..."
}
```

---

## 6. Navigation Structure

```
TabBar
├── Briefing (default)
│   ├── Daily Briefing Screen
│   │   ├── Assistant Summary Card
│   │   ├── "View All Chats" → navigates to Chats tab
│   │   └── Today's Schedule (scrollable)
│   │       └── Event Card → Event Detail Sheet
│
├── Chats
│   ├── Conversation List Screen
│   │   ├── Search bar
│   │   ├── Filter chips (All / Unread / Bot Handled)
│   │   └── Conversation Card → Chat Detail (push)
│   │
│   └── Chat Detail Screen (push)
│       ├── Message list
│       ├── Monitoring banner
│       └── Message input (takeover)
│
└── Content
    ├── New Listing Tab (default)
    │   ├── Property Details Form
    │   ├── Upload Media
    │   └── Submit → Success confirmation
    │
    └── My Content Tab
        └── Listing Card → Listing Detail (push)
```

**Deep links:** Push notifications for new messages deep-link to the specific Chat Detail screen.

---

## 7. Out of Scope for V1

| Feature | Rationale |
|---------|-----------|
| Voice/video calling within the app | Complex; V1 uses `tel:` link to phone app. |
| WebSocket real-time messaging | V1 uses polling (5s interval). WebSocket in V2. |
| Agent-to-agent messaging | Single-agent product; no peer chat needed. |
| Offline mode / local caching | V1 requires connectivity. Offline in V2. |
| Push notification preferences UI | V1 sends all notifications. Preferences in V2. |
| Listing editing from the Content Portal | V1 is create-only. Edit in V2. |
| Analytics / dashboard on mobile | Stay in the web console for now. |
| Onboarding / account creation | Agents onboard via web; mobile is post-onboard. |
| Apple Watch companion | No. |
| iPad-optimized layout | V1 is iPhone-only. iPad layout in V2. |
| Dark mode | Will follow system setting eventually, but not designed for V1. |
| Contact detail / CRM views | Contacts are viewed in conversation context only for V1. |
| Calendar integration (write) | V1 reads from schedule; creating events stays on backend/assistant. |
| Media editing / listing marketing generation | The content portal captures input; AI marketing generation is backend-only for V1. |
