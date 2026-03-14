# Calloway Admin Console — User Manual

## Overview

Calloway is an AI operational assistant for solo real estate agents. The Admin Console lets you manage customers (agent accounts), monitor conversations, control scheduled automations, track billing and AI costs, and check system health — all from your browser.

**URL:** `https://web-production-aa6f.up.railway.app/console`

---

## Login

**URL:** `/console/login`

- Enter the console password (set via the `CONSOLE_PASSWORD` environment variable).
- Click **Sign In** to authenticate.
- Sessions last 24 hours. After that, you'll be redirected back to login.

---

## Sidebar Navigation

The left sidebar is present on every page. It is split into two groups with a divider between them. On mobile, tap the hamburger menu (top-left) to open the sidebar; tap the overlay or any nav link to close it.

At the top of the sidebar is a **+ New Agent** button that links to the onboarding wizard for registering a new real estate agent customer.

### Main Navigation

| Nav Item | Description |
|----------|-------------|
| **Home** | System overview with key metrics and live activity feed (Dashboard) |
| **Customers** | Manage real estate agent accounts |
| **Messages** | View all SMS, RCS, voice, and email conversations |
| **Automations** | Scheduled follow-ups, reminders, and automated actions |

### Operations Navigation

| Nav Item | Description |
|----------|-------------|
| **Billing** | Subscriptions, revenue tracking, and AI cost breakdown |
| **System Health** | Consolidated view: service connectivity, response times, errors, and manual actions |
| **Testing** | Test harness for simulating conversations |
| **Help** | User guide and feature documentation (coming soon) |
| **Logout** | End your session and return to the login screen |

**Health Status Dot** (top-right corner): A colored dot that auto-refreshes every 30 seconds. Green = all systems healthy, Yellow = degraded, Red = critical issue.

---

## Dashboard (Home)

**URL:** `/console/dashboard`

### Pulse Cards (top row)

Five summary cards show real-time system metrics:

| Card | What It Shows |
|------|---------------|
| **Active Customers** | Total registered agent accounts |
| **Messages Today** | Messages sent/received since midnight (server time) |
| **Messages 24h** | Messages in the last 24-hour rolling window |
| **Errors 24h** | Integration and system errors in the last 24 hours. Turns red if > 0. |
| **AI Cost Today** | Estimated AI spend across all customers today |

### Recent Activity (left panel)

A live feed of the most recent messages across all customers. Auto-refreshes every 15 seconds via HTMX.

Each entry shows:
- **Timestamp** — when the message was sent/received
- **Customer name** — which customer it belongs to
- **Sender badge** — green "inbound" for client messages, blue "ai" for AI responses, gray for system messages
- **Message preview** — first 80 characters of the message body
- **Contact name** (if available)

### Needs Attention (right panel)

Flags customers that may need manual intervention:

- **Errors** (red): Customers with errors in the last 24 hours. Click the customer name to investigate.
- **Inactive 48h+** (yellow): Customers with no message activity for 48+ hours. May indicate a Twilio issue or inactive agent.
- **All clear**: Shown when no customers need attention.

---

## Customers

**URL:** `/console/tenants`

### Customer List

A table of all registered agent accounts with key stats.

**Search bar**: Filter customers by name or market area. Type your query and click **Filter**.

**New Customer button**: Opens the form to register a new agent account.

#### Table Columns

| Column | Description |
|--------|-------------|
| **Name** | Agent's display name. Click to view full profile. |
| **Brokerage** | The agent's brokerage firm |
| **Market** | Primary geographic market area (e.g. "Philadelphia") |
| **Twilio #** | The Twilio phone number assigned to this customer |
| **Contacts** | Total contacts (leads, clients, etc.) in the agent's CRM |
| **Msgs Today** | Messages sent/received today |
| **Last Active** | Timestamp of most recent activity |
| **Status** | **Active** (green) = recent activity, **Inactive** (yellow) = no activity 48h+, **Deactivated** (red) = manually disabled |
| **Errors 24h** | Error count in last 24 hours. Red badge if > 0. |

### New Customer

**URL:** `/console/tenants/new`

Form to register a new real estate agent customer. Fields marked * are required.

#### Agent Profile Section
- **Name*** — Full name of the real estate agent
- **Email*** — Email address for notifications
- **Phone*** — Personal phone in E.164 format (e.g. `+15551234567`)
- **Brokerage** — Brokerage firm name
- **Market** — Primary geographic area (e.g. "Philadelphia")
- **Timezone** — Used for scheduling automations and daily briefings. Options: Eastern, Central, Mountain, Pacific.

#### Twilio Configuration Section
- **Twilio Phone Number*** — The Twilio number contacts will text to reach this agent's AI. Must be provisioned in your Twilio account first.

#### Style & Autonomy Section
- **Tone** — Controls the AI's communication style. Options:
  - *Professional* — Formal, business-like language
  - *Friendly* — Warm and approachable
  - *Casual* — Relaxed and informal
- **Emoji Usage** — Whether the AI should include emojis in messages
- **Autonomy Level** — How independently the AI operates:
  - *Supervised* — AI drafts messages, agent approves before sending
  - *Autonomous* — AI sends messages directly without approval
  - *Manual* — AI only responds when explicitly prompted
- **Buffer Minutes** — Minimum minutes between scheduled showings to allow travel time (default: 30)

#### Optional Section
- **Google Review Link** — URL to the agent's Google Business review page. The AI may share this with satisfied clients.
- **Briefing Time** — Time of day (in agent's timezone) to send the daily briefing summary (default: 07:30)
- **System Prompt Override** — Custom system prompt that overrides the default AI instructions for this customer

**Create Customer** button saves the customer. **Cancel** discards and returns to the list.

### Customer Detail

**URL:** `/console/tenants/{agent_id}`

Full profile view for a single customer, organized into six tabs.

#### Action Buttons (top-right)

| Button | What It Does |
|--------|--------------|
| **Edit Settings** | Opens the edit form to change profile, tone, autonomy, etc. |
| **Test SMS** | Sends a test SMS to the customer's phone to verify Twilio is working |
| **Deactivate** | Disables the customer — stops all AI responses and scheduled automations. Requires confirmation. Only shown for active customers. |

A status badge (green for available, yellow for other statuses, red for deactivated) appears at the top-left.

#### Profile Tab

The default tab when you open a customer's detail page. Contains two sections:

**Stats Cards** — Three cards at the top:
- *Cost* — Estimated AI cost this calendar month
- *Messages* — Total messages this month
- *Errors 24h* — Errors in last 24 hours (red if > 0)

**Two-Column Layout:**

*Left column — Profile:*
- Name, email, phone, brokerage, market, timezone, and Twilio number displayed in a table.

*Right column — Configuration:*
Expandable sections (click to toggle):
- *Style Profile* — Tone, emoji, and communication style settings (JSON)
- *Autonomy Rules* — What the AI can do autonomously vs. requiring approval (JSON)
- *Scheduling Prefs* — Showing times, buffer windows, availability (JSON)
- *Raw Agent Record* — Complete database record for debugging (JSON)

#### Messages Tab

Full conversation feed across all contacts for this customer. Shows a list of contacts with their recent messages, loaded via HTMX for fast performance. Click **Refresh** to reload with the latest messages.

#### Knowledge Base Tab

Upload and manage documents that the AI can use to answer customer-specific questions (RAG-powered retrieval).

**+ Add Document** button opens an inline form with:
- **Title*** — A descriptive name for the document
- **Content*** — Paste the full document text (up to 50,000 characters). The text will be chunked and embedded for AI retrieval.
- **Expiration** (optional) — Set an expiration date after which the document is no longer used

Documents are loaded via HTMX when you first click the Knowledge Base tab. Each document shows its metadata and can be deleted.

#### Contacts Tab

A full table of all contacts associated with this customer, including:

| Column | Description |
|--------|-------------|
| **Name** | Contact's name |
| **Phone** | Phone number |
| **Email** | Email address |
| **Role** | Relationship type (e.g. buyer, seller, vendor) |
| **Stage** | CRM lifecycle stage (e.g. lead, active_client) |
| **Consent** | TCPA consent status — **granted** (green), **pending** (yellow), **revoked** (red, no automated messages allowed) |
| **Last Contact** | Timestamp of most recent interaction |
| **Silent** | Whether automated messaging is paused for this contact |
| **Interactions** | Total interaction count |

#### Listings Tab

A table of real estate listings associated with this customer:

| Column | Description |
|--------|-------------|
| **Address** | Property address |
| **Price** | Listing price |
| **Status** | Green badge for active listings |
| **Beds** | Number of bedrooms |
| **Baths** | Number of bathrooms |
| **Sqft** | Square footage |
| **List Date** | Date the listing was published |

#### Automations Tab

Customer-specific scheduled actions (follow-ups, reminders, briefings). Includes a status filter dropdown to show All, Pending, Completed, or Cancelled automations.

| Column | Description |
|--------|-------------|
| **Trigger Type** | Category of automation (e.g. `follow_up`, `review_request`, `daily_briefing`) |
| **Scheduled At** | When the automation will fire |
| **Action Type** | What happens when it runs (e.g. `send_sms`, `send_email`) |
| **Entity Type** | Related entity type (if applicable) |
| **Status** | **Pending** (blue), **Completed** (green), **Cancelled** (gray) |
| **Created At** | When the automation was created |

### Edit Customer

**URL:** `/console/tenants/{agent_id}/edit`

Pre-filled form to modify an existing customer's settings. Same fields as New Customer minus Twilio number. Click **Save Changes** to apply or **Cancel** to discard.

---

## Messages (Conversations)

**URL:** `/console/conversations`

### Conversation List

Browse all conversations across all customers.

#### Filters (top)
- **Customer** dropdown — Filter by a specific customer
- **Channel** dropdown — Filter by communication channel: SMS, RCS, Vapi (voice), Email
- **Search** text — Filter by contact name or phone number
- **Filter** button — Apply the selected filters

#### Table Columns

| Column | Description |
|--------|-------------|
| **Customer** | Which customer this conversation belongs to |
| **Contact** | The contact (lead/client). Click to view full thread. |
| **Phone** | Contact's phone number |
| **Channel** | Communication channel (SMS, RCS, Vapi, Email) |
| **Messages** | Total message count in this conversation |
| **Last Message** | Preview of the most recent message (first 80 characters) |
| **Time** | Timestamp of the most recent message |

### Conversation Detail

**URL:** `/console/conversations/{conversation_id}`

#### Chat Thread (left panel)

Full message history rendered as a chat thread:
- **Green messages** — Inbound from the contact (client)
- **Blue messages** — AI-generated responses
- **Gray messages** — System messages

Each message shows metadata below it:
- **Sender type** (client/ai/system)
- **Model** — Which AI model generated the response (for AI messages)
- **Tokens** — Token count consumed
- **Intent** — Detected intent of the inbound message (e.g. "schedule_showing", "price_inquiry")
- **Feedback score** — Quality score if available
- **Timestamp**

**Tool execution blocks** appear inline between messages as expandable `<details>` elements. Click to see:
- Tool name and status (green "ok" or red "error")
- Input JSON sent to the tool
- Output JSON returned
- Error message (if failed)
- Latency in milliseconds

#### Right Sidebar

**Contact** — Contact info table: name, phone, role (buyer/seller/vendor), lifecycle stage.

**Active Automations** — Scheduled follow-ups and actions related to this conversation.

---

## Automations (Triggers)

**URL:** `/console/triggers`

Automations are scheduled actions the AI creates automatically (e.g. follow-up texts, review requests, daily briefings).

### Filters
- **Status** dropdown — Pending, Completed, Error, Cancelled, or All
- **Customer** dropdown — Filter by customer

### Table Columns

| Column | Description |
|--------|-------------|
| **Customer** | Which customer this automation belongs to |
| **Type** | Automation category (e.g. `follow_up`, `review_request`, `daily_briefing`) |
| **Scheduled** | Date and time when the automation will fire |
| **Status** | **Pending** (blue) = waiting, **Completed** (green) = done, **Error** (red) = failed, **Cancelled** (gray) = manually cancelled |
| **Action** | What happens when it fires (e.g. `send_sms`, `send_email`) |
| **Autonomy** | Whether it fires automatically or requires approval |
| **Recurrence** | Repeat schedule (e.g. "daily", "weekly") or one-time |
| **Actions** | Available action buttons (see below) |

### Action Buttons

| Button | When Shown | What It Does |
|--------|------------|--------------|
| **Retry** | Error automations | Reset to pending and attempt execution again |
| **Run Now** | Pending automations | Execute immediately instead of waiting for scheduled time. Sends a real message — requires confirmation. |
| **Cancel** | Pending automations | Cancel the automation — it will not fire. Red danger button, requires confirmation. |

---

## System Health

**URL:** `/console/health`

A consolidated view of system status, performance metrics, errors, and manual actions, organized into four tabs. The page auto-refreshes every 30 seconds.

### Services Tab

Cards showing the live status of each external service:
- **Green** = healthy and connected
- **Yellow** = degraded or slow
- **Red** = unreachable or down

Services typically include: Database, Redis, Anthropic (AI), Twilio, Vapi, etc.

### Response Times Tab

Three latency cards measuring the message processing pipeline over the last 24 hours:

| Card | Description |
|------|-------------|
| **Avg Response Time** | Average end-to-end time from receiving a message to sending a response |
| **Typical (Median)** | Median latency — 50% of requests are faster than this |
| **Slowest 5%** | 95th percentile — 95% of requests are faster than this |

### Errors Tab

Two error categories are displayed, with a **Customer** dropdown to filter errors by customer.

**Integration Errors** — Errors from external tool calls (calendar, MLS, CRM integrations, etc.):

| Column | Description |
|--------|-------------|
| **Time** | When the error occurred |
| **Customer** | Which customer triggered the error |
| **Tool** | The tool that failed (e.g. `calendar_lookup`, `mls_search`) |
| **Error** | Click to expand: full error message, input JSON, output JSON |
| **Latency** | How long the tool call took before failing |

**System Errors** — Internal application errors and warnings logged by the system:

| Column | Description |
|--------|-------------|
| **Time** | When the error occurred |
| **Customer** | Which customer was involved (if applicable) |
| **Module** | Code module that raised the error |
| **Severity** | **Error** (red) = requires investigation, **Warning** (yellow) = non-critical |
| **Message** | Click to expand: full error message and stack trace |

### Actions Tab

**Run Check** — Manually trigger the daily check for a specific customer. This reviews contacts, automations, and health metrics.

1. Select a customer from the dropdown
2. Click **Run Check**
3. Confirm the action in the dialog
4. The page will reload after the check completes

---

## Billing

**URL:** `/console/billing`

A consolidated view of subscriptions, revenue, and AI costs, organized into two tabs.

### Subscriptions Tab

**Plan Tiers** — Cards showing each available subscription plan with its monthly price and feature list.

**Active Subscriptions** — A table of all customer subscriptions:

| Column | Description |
|--------|-------------|
| **Customer** | Customer name and email. Click to view their profile. |
| **Plan** | Current subscription tier (blue badge) |
| **Status** | **Active** (green), **Trial** (yellow), **Past Due** (red), **Canceled** (gray). A "canceling" badge appears if the subscription will cancel at the end of the billing period. |
| **Messages Used** | Messages used out of plan limit, with a colored progress bar (green = normal, yellow = 70%+, red = 90%+) |
| **Monthly Revenue** | Monthly subscription price |
| **Period Ends** | End date of the current billing period |
| **Actions** | **Change Plan** dropdown to switch tiers or cancel the subscription |

**Revenue Summary** — Four cards:
- *Monthly Recurring Revenue* — Total MRR from active and trial subscriptions
- *Active Subscribers* — Count of active and trial subscriptions
- *Trial Subscribers* — Count of trial-only subscriptions
- *Past Due* — Count of past-due subscriptions (red if > 0)

### AI Costs Tab

**Summary Cards** (top row):

| Card | Description |
|------|-------------|
| **Total AI Cost (30d)** | Estimated AI spend across all customers in the last 30 days |
| **Total Messages** | Total messages sent/received in 30 days |
| **Voice Minutes** | Total Vapi voice call minutes in 30 days |
| **Showings Booked** | Property showings booked by the AI in 30 days |
| **AI Requests** | Total number of AI requests in 30 days |

**Daily Cost Chart** — A CSS bar chart showing daily AI spend over the last 30 days. Hover each bar to see the exact date and dollar amount.

**AI Model Usage** — Shows the distribution of AI requests by model tier:

| Model | Description |
|-------|-------------|
| **template** | Pre-built templates — no AI cost |
| **haiku** | Fast, low-cost model for simple tasks |
| **sonnet** | More capable model for complex reasoning |

**Cost by Customer (30 days)** — Detailed cost breakdown by customer:

| Column | Description |
|--------|-------------|
| **Customer** | Customer name |
| **Messages** | Total messages |
| **AI Requests** | Number of AI requests |
| **Tokens** | Total tokens consumed |
| **Cost** | Estimated AI cost. Highlighted in red if over $15. |
| **Voice Min** | Vapi voice call minutes |
| **Cost/Message** | Average cost per message |

---

## Testing (Harness)

**URL:** `/harness/`

The Test Harness is a separate tool for simulating conversations. Use it to test how the AI responds to various scenarios without involving real contacts or Twilio.

---

## Help (Docs)

**URL:** `/console/manual`

Links to product documentation, architecture reference, and research. This section is coming soon.

---

## Keyboard Shortcuts & Tips

- **Hover any element** for a tooltip explaining what it does
- **Click `<details>` elements** (triangles) to expand configuration, error details, or tool executions
- **Use tabs** on the Customer Detail, System Health, and Billing pages to switch between sections. Arrow keys navigate between tabs when focused.
- Use **browser back/forward** to navigate between pages
- The console uses **HTMX** for live updates — no manual refresh needed on Dashboard and System Health pages
- Sessions expire after **24 hours** — you'll be redirected to login automatically
- On the Customer Detail page, the URL hash updates when you switch tabs (e.g. `#knowledge-base`), so you can bookmark or share links to specific tabs
