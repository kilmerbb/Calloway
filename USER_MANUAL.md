# Calloway Admin Console — User Manual

## Overview

Calloway is an AI operational assistant for solo real estate agents. The Admin Console lets you manage tenants (agent accounts), monitor conversations, control scheduled triggers, track costs, and check system health — all from your browser.

**URL:** `https://web-production-aa6f.up.railway.app/console`

---

## Login

**URL:** `/console/login`

- Enter the console password (set via the `CONSOLE_PASSWORD` environment variable).
- Click **Sign In** to authenticate.
- Sessions last 24 hours. After that, you'll be redirected back to login.

---

## Sidebar Navigation

The left sidebar is present on every page. Each item links to a major section:

| Nav Item         | Description |
|------------------|-------------|
| **Dashboard**    | System overview with key metrics and live activity feed |
| **Tenants**      | Manage real estate agent accounts |
| **Conversations**| View all SMS, RCS, voice, and email conversations |
| **Triggers**     | Scheduled actions like follow-ups, reminders, and briefings |
| **Errors**       | Tool execution failures and application errors |
| **Costs**        | LLM spend, token usage, and per-agent cost breakdown |
| **Health**       | Service connectivity, latency metrics, and manual scans |
| **Harness**      | Test harness for simulating conversations (separate tool) |
| **Logout**       | End your session and return to the login screen |

**Health Status Dot** (top-right corner): A colored dot that auto-refreshes every 30 seconds. Green = all systems healthy, Yellow = degraded, Red = critical issue.

---

## Dashboard

**URL:** `/console/dashboard`

### Pulse Cards (top row)

Five summary cards show real-time system metrics:

| Card             | What It Shows |
|------------------|---------------|
| **Active Tenants** | Total registered agent accounts |
| **Messages Today** | Messages sent/received since midnight (server time) |
| **Messages 24h**   | Messages in the last 24-hour rolling window |
| **Errors 24h**     | Tool + application errors in the last 24 hours. Turns red if > 0. |
| **LLM Cost Today** | Estimated LLM API spend across all tenants today |

### Recent Activity (left panel)

A live feed of the most recent messages across all tenants. Auto-refreshes every 15 seconds via HTMX.

Each entry shows:
- **Timestamp** — when the message was sent/received
- **Agent name** — which tenant it belongs to
- **Sender badge** — green "inbound" for client messages, blue "ai" for AI responses, gray for system messages
- **Message preview** — first 80 characters of the message body
- **Contact name** (if available)

### Needs Attention (right panel)

Flags tenants that may need manual intervention:

- **Errors** (red): Tenants with errors in the last 24 hours. Click the tenant name to investigate.
- **Inactive 48h+** (yellow): Tenants with no message activity for 48+ hours. May indicate a Twilio issue or inactive agent.
- **All clear**: Shown when no tenants need attention.

---

## Tenants

**URL:** `/console/tenants`

### Tenant List

A table of all registered agent accounts with key stats.

**Search bar**: Filter tenants by name or market area. Type your query and click **Filter**.

**New Tenant button**: Opens the form to register a new agent account.

#### Table Columns

| Column       | Description |
|--------------|-------------|
| **Name**     | Agent's display name. Click to view full profile. |
| **Brokerage**| The agent's brokerage firm |
| **Market**   | Primary geographic market area (e.g. "Philadelphia") |
| **Twilio #** | The Twilio phone number assigned to this tenant |
| **Contacts** | Total contacts (leads, clients, etc.) in the agent's CRM |
| **Msgs Today** | Messages sent/received today |
| **Last Active** | Timestamp of most recent activity |
| **Status**   | **Active** (green) = recent activity, **Inactive** (yellow) = no activity 48h+, **Deactivated** (red) = manually disabled |
| **Errors 24h** | Error count in last 24 hours. Red badge if > 0. |

### New Tenant

**URL:** `/console/tenants/new`

Form to register a new real estate agent tenant. Fields marked * are required.

#### Agent Profile Section
- **Name*** — Full name of the real estate agent
- **Email*** — Email address for notifications
- **Phone*** — Personal phone in E.164 format (e.g. `+15551234567`)
- **Brokerage** — Brokerage firm name
- **Market** — Primary geographic area (e.g. "Philadelphia")
- **Timezone** — Used for scheduling triggers and daily briefings. Options: Eastern, Central, Mountain, Pacific.

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
- **System Prompt Override** — Custom system prompt that overrides the default AI instructions for this tenant

**Create Tenant** button saves the tenant. **Cancel** discards and returns to the list.

### Tenant Detail

**URL:** `/console/tenants/{agent_id}`

Full profile view for a single tenant.

#### Action Buttons (top-right)

| Button         | What It Does |
|----------------|--------------|
| **Edit Config** | Opens the edit form to change profile, tone, autonomy, etc. |
| **Test SMS**    | Sends a test SMS to the tenant's phone to verify Twilio is working |
| **Deactivate**  | Disables the tenant — stops all AI responses and scheduled triggers. Requires confirmation. Only shown for active tenants. |

#### Left Panel

**Profile** — Table showing name, email, phone, brokerage, market, timezone, and Twilio number.

**Configuration** — Expandable sections (click to toggle):
- *Style Profile* — Tone, emoji, and communication style settings (JSON)
- *Autonomy Rules* — What the AI can do autonomously vs. requiring approval (JSON)
- *Scheduling Prefs* — Showing times, buffer windows, availability (JSON)
- *Raw Agent Record* — Complete database record for debugging (JSON)

**Recent Messages** — The 20 most recent messages for this tenant. Each shows:
- Timestamp
- Sender badge: green for client messages, blue for AI (with model name), gray for system
- Message preview (first 100 characters)

#### Right Sidebar

**This Month** — Three stat cards:
- *Cost* — LLM API cost this calendar month
- *Messages* — Total messages this month
- *Errors 24h* — Errors in last 24 hours (red if > 0)

**Contacts** — Up to 15 contacts with lifecycle stage badges (e.g. "lead", "active_client"). Red "revoked" badge indicates TCPA consent was revoked — no automated messages allowed.

**Listings** — Up to 10 real estate listings with address, price, and status badge (green = active).

**Pending Triggers** — Scheduled actions waiting to fire, with type, time, and action badge.

### Edit Tenant

**URL:** `/console/tenants/{agent_id}/edit`

Pre-filled form to modify an existing tenant's settings. Same fields as New Tenant minus Twilio number. Click **Save Changes** to apply or **Cancel** to discard.

---

## Conversations

**URL:** `/console/conversations`

### Conversation List

Browse all conversations across all tenants.

#### Filters (top)
- **Agent** dropdown — Filter by a specific tenant
- **Channel** dropdown — Filter by communication channel: SMS, RCS, Vapi (voice), Email
- **Search** text — Filter by contact name or phone number
- **Filter** button — Apply the selected filters

#### Table Columns

| Column        | Description |
|---------------|-------------|
| **Agent**     | Which tenant this conversation belongs to |
| **Contact**   | The contact (lead/client). Click to view full thread. |
| **Phone**     | Contact's phone number |
| **Channel**   | Communication channel (SMS, RCS, Vapi, Email) |
| **Messages**  | Total message count in this conversation |
| **Last Message** | Preview of the most recent message (first 80 characters) |
| **Time**      | Timestamp of the most recent message |

### Conversation Detail

**URL:** `/console/conversations/{conversation_id}`

#### Chat Thread (left panel)

Full message history rendered as a chat thread:
- **Green messages** — Inbound from the contact (client)
- **Blue messages** — AI-generated responses
- **Gray messages** — System messages

Each message shows metadata below it:
- **Sender type** (client/ai/system)
- **Model** — Which LLM model generated the response (for AI messages)
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

**Active Triggers** — Scheduled follow-ups and actions related to this conversation.

---

## Triggers

**URL:** `/console/triggers`

Triggers are scheduled actions the AI creates automatically (e.g. follow-up texts, review requests, daily briefings).

### Filters
- **Status** dropdown — Pending, Completed, Error, Cancelled, or All
- **Agent** dropdown — Filter by tenant

### Table Columns

| Column        | Description |
|---------------|-------------|
| **Agent**     | Which tenant this trigger belongs to |
| **Type**      | Trigger category (e.g. `follow_up`, `review_request`, `daily_briefing`) |
| **Scheduled** | Date and time when the trigger will fire |
| **Status**    | **Pending** (blue) = waiting, **Completed** (green) = done, **Error** (red) = failed, **Cancelled** (gray) = manually cancelled |
| **Action**    | What happens when it fires (e.g. `send_sms`, `send_email`) |
| **Autonomy**  | Whether it fires automatically or requires approval |
| **Recurrence** | Repeat schedule (e.g. "daily", "weekly") or one-time |
| **Actions**   | Available action buttons (see below) |

### Action Buttons

| Button      | When Shown | What It Does |
|-------------|------------|--------------|
| **Retry**   | Error triggers | Reset to pending and attempt execution again |
| **Fire Now** | Pending triggers | Execute immediately instead of waiting for scheduled time |
| **Cancel**  | Pending triggers | Cancel the trigger — it will not fire. Red danger button. |

---

## Errors

**URL:** `/console/errors`

Two error categories are displayed:

### Filter
- **Agent** dropdown — Filter errors by tenant

### Tool Execution Errors

Errors from external tool calls (calendar, MLS, CRM integrations, etc.).

| Column    | Description |
|-----------|-------------|
| **Time**  | When the error occurred |
| **Agent** | Which tenant triggered the error |
| **Tool**  | The tool that failed (e.g. `calendar_lookup`, `mls_search`) |
| **Error** | Click to expand: full error message, input JSON, output JSON |
| **Latency** | How long the tool call took before failing |

### Application Errors

Internal application errors and warnings logged by the system.

| Column      | Description |
|-------------|-------------|
| **Time**    | When the error occurred |
| **Agent**   | Which tenant was involved (if applicable) |
| **Module**  | Code module that raised the error |
| **Severity** | **Error** (red) = requires investigation, **Warning** (yellow) = non-critical |
| **Message** | Click to expand: full error message and stack trace |

---

## Costs

**URL:** `/console/costs`

### Summary Cards (top row)

| Card              | Description |
|-------------------|-------------|
| **Total LLM Cost (30d)** | Estimated LLM API spend across all tenants in the last 30 days |
| **Total Messages** | Total messages sent/received in 30 days |
| **Voice Minutes**  | Total Vapi voice call minutes in 30 days |
| **Showings Booked** | Property showings booked by the AI in 30 days |
| **LLM Calls**     | Total number of LLM API calls in 30 days |

### Daily Cost Chart

A CSS bar chart showing daily LLM spend over the last 30 days. Hover each bar to see the exact date and dollar amount.

### Model Tier Breakdown

Shows the distribution of LLM calls by model tier:

| Model      | Description |
|------------|-------------|
| **template** | Pre-built templates — no LLM cost |
| **haiku**    | Fast, low-cost model for simple tasks |
| **sonnet**   | More capable model for complex reasoning |

### Per-Agent Costs (30 days)

Detailed cost breakdown by tenant:

| Column     | Description |
|------------|-------------|
| **Agent**  | Tenant name |
| **Messages** | Total messages |
| **LLM Calls** | Number of LLM API calls |
| **Tokens** | Total tokens consumed |
| **Cost**   | Estimated LLM cost. Highlighted in red if over $15. |
| **Voice Min** | Vapi voice call minutes |
| **$/msg**  | Average cost per message |

---

## Health

**URL:** `/console/health`

Auto-refreshes every 30 seconds.

### Service Connectivity

Cards showing the live status of each external service:
- **Green** = healthy and connected
- **Yellow** = degraded or slow
- **Red** = unreachable or down

Services typically include: Database, Redis, Anthropic (LLM), Twilio, Vapi, etc.

### Pipeline Performance (24h)

Three latency cards measuring the message processing pipeline:

| Card          | Description |
|---------------|-------------|
| **Avg Latency** | Average end-to-end time from receiving a message to sending a response |
| **p50**        | Median latency — 50% of requests are faster than this |
| **p95**        | 95th percentile — 95% of requests are faster than this |

### Manual Actions

**Run Scan** — Manually trigger the daily scan for a specific tenant. This checks contacts, triggers, and health metrics.

1. Select a tenant from the dropdown
2. Click **Run Scan**
3. The page will reload after the scan completes

---

## Harness

**URL:** `/harness/`

The Test Harness is a separate tool for simulating conversations. Use it to test how the AI responds to various scenarios without involving real contacts or Twilio.

---

## Keyboard Shortcuts & Tips

- **Hover any element** for a tooltip explaining what it does
- **Click `<details>` elements** (triangles) to expand configuration, error details, or tool executions
- Use **browser back/forward** to navigate between pages
- The console uses **HTMX** for live updates — no manual refresh needed on Dashboard and Health pages
- Sessions expire after **24 hours** — you'll be redirected to login automatically
