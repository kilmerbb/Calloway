# Calloway Console — First-Time Onboarding Design Spec

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Design Spec — Ready for Engineering Review

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Scenario 1: First-Time Operator Login](#2-scenario-1-first-time-operator-login)
3. [Scenario 2: First Customer Setup (Onboard Wizard Enhancements)](#3-scenario-2-first-customer-setup)
4. [Scenario 3: Ongoing Orientation](#4-scenario-3-ongoing-orientation)
5. [Empty State Designs](#5-empty-state-designs)
6. [Setup Checklist Widget](#6-setup-checklist-widget)
7. [HTML/CSS Component Patterns](#7-htmlcss-component-patterns)
8. [HTMX Integration Notes](#8-htmx-integration-notes)
9. [Copy Guide](#9-copy-guide)
10. [Accessibility](#10-accessibility)

---

## 1. Design Philosophy

**Principle:** The first 5 minutes determine whether an operator trusts this tool. Every empty screen is an opportunity, not a void.

**Guiding references:** Stripe's dashboard onboarding (task checklist, inline guidance, clear next action), Linear's first-run experience (minimal, fast, opinionated defaults). Both share a quality we want: they never make you feel lost, even when there is nothing to look at yet.

**Key constraints:**
- HTMX + Jinja2 server-rendered — no client-side router, no SPA state management
- Must degrade gracefully without JavaScript (progressive enhancement)
- Dark theme (existing `--bg: #121212` palette) — onboarding should feel native, not a separate branded experience
- Per-customer setup must stay efficient for operators managing 100+ agents — no slow, mandatory walkthroughs after the first time

**Tone vocabulary:** Confident, warm, encouraging, concise. Never cute, never condescending.

---

## 2. Scenario 1: First-Time Operator Login

### 2.1 Flow Diagram

```
Login Page
    |
    v
[POST /console/login] -- password valid?
    |                            |
    no --> login page            yes --> check: is_first_login?
           with error                        |
                                     yes             no
                                      |               |
                                      v               v
                              Welcome Screen     Dashboard
                              (/console/welcome)   (normal)
                                      |
                                      v
                              Setup Checklist
                              (embedded in welcome)
                                      |
                                      v
                              CTA: "Create your first customer"
                                      |
                                      v
                              Onboard Wizard
                              (/console/onboard)
                                      |
                                      v
                              Success Page
                              (/console/onboard/success)
                                      |
                                      v
                              Dashboard (now populated)
                              + Setup checklist persists
                                in sidebar until complete
```

### 2.2 Detecting First Login

The backend determines first-login state by checking:
1. Total tenant count is 0
2. No `operator_welcomed` flag in the session/cookie or a lightweight `operator_settings` table

Store a `welcomed_at` timestamp so we only show the full welcome screen once. After that, the setup checklist (Section 6) handles ongoing guidance.

### 2.3 Welcome Screen — Wireframe

```
+------------------------------------------------------------------+
|  Sidebar (normal)          |  Main Content                       |
|                            |                                     |
|  Calloway                  |  +------------------------------+   |
|  Admin Console             |  |                              |   |
|                            |  |  Welcome to Calloway         |   |
|  [+ New Agent]             |  |                              |   |
|                            |  |  You're setting up something |   |
|  Home  (active)            |  |  great. Let's get your first |   |
|  Customers                 |  |  AI agent running.           |   |
|  Messages                  |  |                              |   |
|  Automations               |  |  +------------------------+  |   |
|                            |  |  | SETUP CHECKLIST        |  |   |
|  ---                       |  |  |                        |  |   |
|  Billing                   |  |  | [ ] Create first       |  |   |
|  System Health             |  |  |     customer           |  |   |
|  Testing                   |  |  | [ ] Verify Twilio      |  |   |
|  Help                      |  |  |     connection         |  |   |
|                            |  |  | [ ] Send test SMS      |  |   |
|  ---                       |  |  | [ ] Review AI          |  |   |
|  Logout                    |  |  |     response           |  |   |
|                            |  |  +------------------------+  |   |
|                            |  |                              |   |
|                            |  |  [Create Your First Agent]   |   |
|                            |  |  (primary button)            |   |
|                            |  |                              |   |
|                            |  |  Takes about 5 minutes.      |   |
|                            |  |  You can always edit later.  |   |
|                            |  |                              |   |
|                            |  +------------------------------+   |
|                            |                                     |
+------------------------------------------------------------------+
```

### 2.4 Welcome Screen — Copy

**Headline:** Welcome to Calloway

**Subhead:** You're setting up something great. Let's get your first AI agent live and responding to clients.

**Checklist header:** Your setup checklist

**Checklist items:**
1. Create your first customer
2. Verify the Twilio connection
3. Send a test SMS
4. Review an AI response

**Primary CTA:** Create Your First Agent

**Supporting text:** Takes about 5 minutes. You can always change everything later.

**Secondary link (bottom):** Or explore the dashboard first (links to /console/dashboard with `?skip_welcome=1`)

### 2.5 Welcome Screen — Template

File: `app/templates/console/welcome.html`

```html
{% extends "base.html" %}
{% block content %}

<div class="welcome-container">
    <div class="welcome-hero">
        <h2 class="welcome-title">Welcome to Calloway</h2>
        <p class="welcome-subtitle">
            You're setting up something great. Let's get your first AI agent
            live and responding to clients.
        </p>
    </div>

    <div class="welcome-checklist-card">
        <div class="checklist-header">
            <span class="checklist-header-label">Your setup checklist</span>
            <span class="checklist-progress">0 of 4</span>
        </div>
        <div class="checklist-items">
            <div class="checklist-row">
                <span class="checklist-bullet"></span>
                <span class="checklist-text">Create your first customer</span>
            </div>
            <div class="checklist-row">
                <span class="checklist-bullet"></span>
                <span class="checklist-text">Verify the Twilio connection</span>
            </div>
            <div class="checklist-row">
                <span class="checklist-bullet"></span>
                <span class="checklist-text">Send a test SMS</span>
            </div>
            <div class="checklist-row">
                <span class="checklist-bullet"></span>
                <span class="checklist-text">Review an AI response</span>
            </div>
        </div>
    </div>

    <div class="welcome-actions">
        <a href="/console/onboard" class="btn btn-primary btn-lg">
            Create Your First Agent
        </a>
        <p class="welcome-reassurance">
            Takes about 5 minutes. You can always change everything later.
        </p>
    </div>

    <div class="welcome-skip">
        <a href="/console/dashboard?skip_welcome=1" class="text-link">
            Or explore the dashboard first
        </a>
    </div>
</div>

{% endblock %}
```

---

## 3. Scenario 2: First Customer Setup

The existing onboard wizard (`/console/onboard`) is well-structured with 7 steps. The enhancements below make the *first* run through it feel guided without slowing down repeat usage.

### 3.1 Enhanced Flow Diagram

```
/console/onboard
    |
    v
Step 1: Agent Profile
  "Who is your new client?"
  [Name*, Email*, Phone*, Brokerage, Market, Timezone]
    |
    v
Step 2: Communication Style
  "How does this agent communicate?"
  [Tone (card select), Emoji, Greeting, Sign-off, Notes]
    |
    v
Step 3: Scheduling & Availability
  "When and how do they work?"
  [Showing duration, Buffer, Hours, After-hours mode, Briefing time]
    |
    v
Step 4: Autonomy & Trust Level
  "How much control should the AI have?"
  [Operating mode (card select), Escalation rules, Notifications]
    |
    v
Step 5: Active Listings
  "What listings are they working?"
  [Dynamic listing entries — skippable]
    |
    v
Step 6: Active Clients
  "Who are their active clients?"
  [Dynamic client entries — skippable]
    |
    v
Step 7: Channel Setup & Review
  "Final setup and review"
  [Twilio #, Google Review link, System prompt, Review summary]
    |
    v
[Submit: POST /console/onboard]
    |
    v
Success Page (/console/onboard/success)
  "Sarah Mitchell is set up!"
  [Build checklist + Next steps + CTAs]
```

### 3.2 First-Run Enhancements

For the **first customer only** (detected via `tenant_count == 0` when page loads), add contextual guidance that does not appear on subsequent wizard runs.

#### A. Intro Card (Before Step 1)

Only shown when `tenant_count == 0`. A brief orientation card that appears above the wizard:

```
+------------------------------------------------------+
|  Your first agent setup                              |
|                                                      |
|  This wizard collects everything the AI needs to     |
|  represent your client authentically. Most fields     |
|  are editable later — focus on getting the basics    |
|  right: name, phone, Twilio number, and tone.       |
|                                                      |
|  [Got it, let's start]                               |
+------------------------------------------------------+
```

Implementation: Render conditionally in the template:

```html
{% if first_agent %}
<div class="wizard-intro-banner" id="introCard">
    <div class="wizard-intro-content">
        <strong>Your first agent setup</strong>
        <p>This wizard collects everything the AI needs to represent your
        client authentically. Most fields are editable later — focus on
        getting the basics right: name, phone, Twilio number, and tone.</p>
    </div>
    <button class="btn btn-outline btn-sm"
            onclick="document.getElementById('introCard').remove()">
        Got it, let's start
    </button>
</div>
{% endif %}
```

#### B. Inline Help Tooltips

Add `form-hint` text below fields that are commonly confusing. These already exist in the current wizard for some fields. Add to these additional fields:

| Field | Hint Text |
|-------|-----------|
| Autonomy Level | "Most operators start new agents in Supervised mode. You can upgrade to Autonomous once the agent trusts the AI — usually after 1-2 weeks." |
| After Hours Mode | "Acknowledge & Queue is safest for new setups. Clients get a response, and nothing happens without the agent reviewing it." |
| System Prompt Override | "You almost never need this. The tone and autonomy settings above generate the system prompt automatically." |
| Twilio Phone Number | "This must be provisioned in your Twilio account first. The webhook URL will be configured automatically." |

#### C. Step-Specific Encouragement

After each step transition, show a brief, dismissible micro-message:

- After Step 1: "Good start. The AI will use this info to introduce itself naturally."
- After Step 2: "Nice — this is what makes each agent's AI feel personal, not generic."
- After Step 4: "Smart choice. You can always adjust the autonomy level from the customer detail page."
- After Step 6: "Almost there. One more step."

Implementation: A transient toast that fades after 3 seconds.

```html
<div class="wizard-toast" id="wizardToast" role="status" aria-live="polite">
    <span id="wizardToastText"></span>
</div>
```

```javascript
const stepToasts = {
    2: "Good start. The AI will use this info to introduce itself naturally.",
    3: "Nice — this is what makes each agent's AI feel personal, not generic.",
    5: "Smart choice. You can always adjust autonomy from the customer detail page.",
    7: "Almost there. One more step."
};

function showStepToast(step) {
    const msg = stepToasts[step];
    if (!msg) return;
    const toast = document.getElementById('wizardToast');
    const text = document.getElementById('wizardToastText');
    text.textContent = msg;
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 3500);
}
```

### 3.3 Success Page Enhancements

The existing `onboard_success.html` is solid. Enhance it for the first-agent case:

#### First Agent — Extra Celebration

```
+------------------------------------------------------+
|                                                      |
|                    (checkmark icon)                   |
|                                                      |
|     Sarah Mitchell is set up!                        |
|                                                      |
|     Your first AI agent is ready. Here's what's      |
|     done and what's left before the handoff call.    |
|                                                      |
+------------------------------------------------------+
|                                                      |
|  BUILD CHECKLIST                                     |
|  [check] Agent profile created                       |
|  [check] Communication style configured              |
|  [check] Autonomy rules set                          |
|  [  ] Google Calendar connected                      |
|  [  ] Voice agent configured (Vapi)                  |
|  [  ] Test SMS verified                              |
|                                                      |
+------------------------------------------------------+
|                                                      |
|  WHAT HAPPENS NEXT                                   |
|                                                      |
|  1. Send a test SMS from the customer detail page    |
|     to verify Twilio is working.                     |
|                                                      |
|  2. Connect Google Calendar so the AI can check      |
|     availability and book showings.                  |
|                                                      |
|  3. Schedule the handoff call. Walk the agent        |
|     through their AI number and help them intro      |
|     the AI to 2-3 active clients.                    |
|                                                      |
+------------------------------------------------------+
|                                                      |
|  [View Customer Details]  [Onboard Another Agent]    |
|                           [Back to Customers]        |
|                                                      |
+------------------------------------------------------+
```

### 3.4 "You're Live!" Confirmation

After the operator sends a successful test SMS (via the Test SMS button on tenant_detail), show a confirmation banner:

```html
<div class="success-banner" role="alert">
    <span class="success-banner-icon">&#10003;</span>
    <div>
        <strong>Test SMS sent successfully.</strong>
        <span class="text-muted">
            {{ agent.name }}'s AI is live and ready to respond.
        </span>
    </div>
</div>
```

---

## 4. Scenario 3: Ongoing Orientation

### 4.1 Coach Marks System

Coach marks are small, dismissible tooltips anchored to specific UI elements. They appear once per operator and are tracked via a `dismissed_hints` cookie or lightweight DB column.

#### Coach Mark Targets

| ID | Element | Trigger | Message |
|----|---------|---------|---------|
| `hint-autonomy` | Autonomy selector on tenant_edit | First visit to edit page | "Agents typically graduate from Supervised to Autonomous after 1-2 weeks of trust-building." |
| `hint-test-sms` | Test SMS button on tenant_detail | First visit to detail page | "Send a test SMS to verify the Twilio channel before the handoff call." |
| `hint-knowledge-base` | Knowledge Base tab on tenant_detail | First visit after creating a tenant | "Upload listing details, FAQs, and agent-specific info here. The AI retrieves this during conversations." |
| `hint-automations` | Automations nav item | After first tenant has been live for 24h | "Check here for scheduled follow-ups, reminders, and briefings the AI has queued." |
| `hint-billing` | Billing nav item | After 3+ tenants exist | "Track subscription revenue and AI costs per customer here." |

#### Coach Mark Wireframe

```
                    +-----------------------------------+
                    | Upload listing details, FAQs,     |
 [Knowledge Base]<--| and agent-specific info here.     |
      tab           | The AI retrieves this during      |
                    | conversations.                    |
                    |                                   |
                    | [Got it]              [1 of 3]    |
                    +-----------------------------------+
```

### 4.2 Feature Hints — "Did You Know?" Pattern

Subtle inline hints that appear on pages the operator has visited but where they have not used a specific feature. These are **not** modal or blocking — they sit inline within the page content.

#### Implementation Pattern

```html
{% if not operator_has_used_knowledge_base %}
<div class="feature-hint" data-hint-id="kb-upload"
     hx-delete="/console/hints/kb-upload"
     hx-swap="outerHTML">
    <span class="feature-hint-badge">Tip</span>
    <span class="feature-hint-text">
        Upload the agent's active listings and FAQs to the Knowledge Base.
        The AI uses this to answer client questions accurately.
    </span>
    <button class="feature-hint-dismiss" aria-label="Dismiss tip"
            hx-delete="/console/hints/kb-upload"
            hx-target="closest .feature-hint"
            hx-swap="outerHTML">
        &times;
    </button>
</div>
{% endif %}
```

### 4.3 What's New Section

A lightweight changelog accessible from the Help page. Not a modal, not a badge counter — just a clean list.

#### Location

Add a "What's New" section to the existing `/console/manual` page, or link to it from the sidebar Help item.

#### Wireframe

```
+------------------------------------------------------+
|  WHAT'S NEW                                          |
|                                                      |
|  Mar 2026                                            |
|  --------                                            |
|  - Knowledge Base: Upload documents directly from    |
|    the customer detail page. AI retrieves relevant   |
|    chunks during conversations.                      |
|                                                      |
|  - Billing Dashboard: Track subscriptions, revenue,  |
|    and AI costs per customer.                        |
|                                                      |
|  Feb 2026                                            |
|  --------                                            |
|  - Onboard Wizard: 7-step guided setup for new      |
|    agents replaces the old single-page form.         |
|                                                      |
+------------------------------------------------------+
```

#### Data Source

A static Jinja2 include or a simple JSON/YAML file read at render time. No database needed.

```
app/data/changelog.json
```

---

## 5. Empty State Designs

Every page with a table or data list needs a purposeful empty state. The pattern: icon/illustration (text-based) + explanation + single primary action.

### 5.1 Dashboard (0 Customers)

*This is replaced by the Welcome Screen (Section 2) on true first login. On subsequent visits with 0 customers, show:*

```
+------------------------------------------------------+
|  Pulse Cards: all zeros (grayed out)                 |
|                                                      |
|  +------------------------------------------------+  |
|  |                                                |  |
|  |                  (house icon)                  |  |
|  |                                                |  |
|  |    No customers yet                            |  |
|  |                                                |  |
|  |    Create your first real estate agent         |  |
|  |    customer to start seeing activity here.     |  |
|  |                                                |  |
|  |    [Create First Customer]                     |  |
|  |                                                |  |
|  +------------------------------------------------+  |
+------------------------------------------------------+
```

### 5.2 Customers Page (Empty)

Replace the current "No customers found." single row:

```
+------------------------------------------------------+
|  [Search...]                [New Customer]            |
|                                                       |
|  +--------------------------------------------------+|
|  |                                                   ||
|  |               (people icon)                       ||
|  |                                                   ||
|  |   No customers yet                                ||
|  |                                                   ||
|  |   Each customer is a real estate agent whose      ||
|  |   AI assistant you manage. Create one to get      ||
|  |   started.                                        ||
|  |                                                   ||
|  |   [+ Create Your First Customer]                  ||
|  |                                                   ||
|  +--------------------------------------------------+|
+------------------------------------------------------+
```

**Template change** — In `tenants.html`, replace:

```html
{% if not agents %}
<tr><td colspan="9" style="color: var(--text-muted); text-align: center;">
    No customers found.</td></tr>
{% endif %}
```

With:

```html
{% if not agents %}
</table>
<div class="empty-state">
    <div class="empty-state-icon">&#9830;</div>
    <div class="empty-state-title">No customers yet</div>
    <div class="empty-state-desc">
        Each customer is a real estate agent whose AI assistant you manage.
        Create one to get started.
    </div>
    <a href="/console/onboard" class="btn btn-primary">
        + Create Your First Customer
    </a>
</div>
{% endif %}
```

### 5.3 Messages Page (Empty)

```
+------------------------------------------------------+
|  [Customer: All]  [Channel: All]  [Search...]        |
|                                                       |
|  +--------------------------------------------------+|
|  |                                                   ||
|  |               (chat bubble icon)                  ||
|  |                                                   ||
|  |   No conversations yet                            ||
|  |                                                   ||
|  |   Conversations appear here when contacts         ||
|  |   text your customers' AI numbers. Create a       ||
|  |   customer and send a test SMS to see it work.    ||
|  |                                                   ||
|  |   [Go to Customers]                               ||
|  |                                                   ||
|  +--------------------------------------------------+|
+------------------------------------------------------+
```

### 5.4 Automations Page (Empty)

```
+------------------------------------------------------+
|  [Status: Pending]  [Customer: All]  [Filter]         |
|                                                       |
|  +--------------------------------------------------+|
|  |                                                   ||
|  |               (clock icon)                        ||
|  |                                                   ||
|  |   No automations scheduled                        ||
|  |                                                   ||
|  |   Follow-ups, review requests, and daily          ||
|  |   briefings show up here once your customers'     ||
|  |   AI agents start handling conversations.         ||
|  |                                                   ||
|  +--------------------------------------------------+|
+------------------------------------------------------+
```

### 5.5 Tenant Detail — Empty Sub-Tabs

**Contacts tab (empty):**
```
No contacts yet.
Contacts are created automatically when someone texts this agent's
Twilio number. You can also add them during the onboard wizard.
```

**Listings tab (empty):**
```
No listings yet.
Add this agent's active listings so the AI can answer
showing requests and provide property details.
[+ Add Listing]
```

**Automations tab (empty):**
```
No scheduled automations.
The AI creates automations (follow-ups, reminders, briefings)
as it handles conversations. They'll appear here.
```

**Messages tab (empty):**
Already has a good empty state via the `messages-empty` class. Keep as-is.

---

## 6. Setup Checklist Widget

A persistent, collapsible checklist that tracks operator progress across sessions. Lives on the dashboard and optionally in the sidebar.

### 6.1 Checklist Items

| # | Item | Completion Trigger | Backend Check |
|---|------|--------------------|---------------|
| 1 | Create your first customer | `tenant_count >= 1` | SQL count on tenants table |
| 2 | Verify Twilio connection | Test SMS button clicked successfully | `test_sms_sent_at IS NOT NULL` on any tenant |
| 3 | Send a test SMS | Same as above (combined with #2 for simplicity) | -- |
| 4 | Review an AI response | Operator viewed a conversation detail page | Session/cookie flag `viewed_conversation = true` |
| 5 | Connect Google Calendar | OAuth completed for any tenant | `google_calendar_connected = true` on any tenant |

For the MVP, items 2 and 3 can be combined: "Verify Twilio by sending a test SMS."

### 6.2 Dashboard Checklist — Wireframe

Shown on the dashboard when checklist is incomplete. Replaces the "Needs Attention" sidebar when there is nothing to attend to.

```
+------------------------------------------+
|  GETTING STARTED           2 of 4 done   |
|                                          |
|  [====--------] 50%                      |
|                                          |
|  [x] Create your first customer          |
|  [x] Send a test SMS                     |
|  [ ] Review an AI conversation  ->       |
|  [ ] Connect Google Calendar    ->       |
|                                          |
+------------------------------------------+
```

The `->` arrow on incomplete items links to the relevant page.

### 6.3 Template Pattern

```html
{% if not setup_complete %}
<div class="setup-checklist" id="setupChecklist"
     hx-get="/console/dashboard/setup-progress"
     hx-trigger="load"
     hx-swap="innerHTML">
    <!-- Server renders checklist state -->
</div>
{% endif %}
```

Partial: `app/templates/console/partials/setup_checklist.html`

```html
<div class="checklist-header">
    <span class="checklist-header-label">Getting started</span>
    <span class="checklist-progress">{{ done_count }} of {{ total_count }}</span>
</div>
<div class="setup-progress-bar">
    <div class="setup-progress-fill"
         style="width: {{ (done_count / total_count * 100)|int }}%"></div>
</div>
<div class="checklist-items">
    {% for item in checklist_items %}
    <div class="checklist-row {{ 'done' if item.done else '' }}">
        <span class="checklist-bullet {{ 'checked' if item.done else '' }}">
            {{ '&#10003;' if item.done else '&#9675;' }}
        </span>
        <span class="checklist-text">{{ item.label }}</span>
        {% if not item.done and item.link %}
        <a href="{{ item.link }}" class="checklist-action"
           aria-label="{{ item.label }}">&#8594;</a>
        {% endif %}
    </div>
    {% endfor %}
</div>
{% if done_count == total_count %}
<div class="checklist-complete">
    <span class="checklist-complete-icon">&#10003;</span>
    <span>All set! You're ready to scale.</span>
    <button class="btn btn-outline btn-sm"
            hx-post="/console/dismiss-setup-checklist"
            hx-target="#setupChecklist"
            hx-swap="outerHTML">Dismiss</button>
</div>
{% endif %}
```

### 6.4 Backend Endpoint

```
GET /console/dashboard/setup-progress
```

Returns the checklist partial with current completion state. Called via HTMX on dashboard load.

```
POST /console/dismiss-setup-checklist
```

Sets `setup_checklist_dismissed = true` in the operator session/settings. Returns empty response (HTMX removes the element).

---

## 7. HTML/CSS Component Patterns

### 7.1 Welcome Container

```css
/* Welcome Screen */
.welcome-container {
    max-width: 560px;
    margin: 4rem auto 0;
    text-align: center;
}

.welcome-hero {
    margin-bottom: 2rem;
}

.welcome-title {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 0.5rem;
}

.welcome-subtitle {
    font-size: 16px;
    color: var(--text-muted);
    line-height: 1.6;
    max-width: 440px;
    margin: 0 auto;
}

.welcome-checklist-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.25rem;
    text-align: left;
    margin-bottom: 2rem;
}

.welcome-actions {
    margin-bottom: 1.5rem;
}

.btn-lg {
    padding: 0.75rem 2rem;
    font-size: 16px;
}

.welcome-reassurance {
    font-size: 13px;
    color: var(--text-muted);
    margin-top: 0.75rem;
}

.welcome-skip {
    font-size: 13px;
}

.text-link {
    color: var(--text-muted);
    text-decoration: underline;
    text-underline-offset: 2px;
}
.text-link:hover {
    color: var(--text);
}
```

### 7.2 Empty State Component

```css
/* Empty States */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem 2rem;
    text-align: center;
}

.empty-state-icon {
    font-size: 40px;
    opacity: 0.3;
    margin-bottom: 1rem;
}

.empty-state-title {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

.empty-state-desc {
    font-size: 14px;
    color: var(--text-muted);
    max-width: 380px;
    line-height: 1.5;
    margin-bottom: 1.5rem;
}
```

### 7.3 Setup Progress Bar

```css
/* Setup Progress */
.setup-checklist {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.25rem;
    margin-bottom: 1.5rem;
}

.checklist-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
}

.checklist-header-label {
    font-size: 14px;
    font-weight: 600;
    letter-spacing: -0.2px;
}

.checklist-progress {
    font-size: 12px;
    color: var(--text-muted);
}

.setup-progress-bar {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin-bottom: 1rem;
    overflow: hidden;
}

.setup-progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.4s ease;
}

.checklist-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
}
.checklist-row:last-child {
    border-bottom: none;
}

.checklist-row.done {
    color: var(--text-muted);
}
.checklist-row.done .checklist-text {
    text-decoration: line-through;
    text-decoration-color: var(--border);
}

.checklist-bullet {
    width: 20px;
    text-align: center;
    font-size: 14px;
    flex-shrink: 0;
}
.checklist-bullet.checked {
    color: var(--green);
}

.checklist-action {
    margin-left: auto;
    color: var(--text-muted);
    font-size: 16px;
}
.checklist-action:hover {
    color: var(--accent);
    text-decoration: none;
}

.checklist-complete {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 1rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border);
    font-size: 14px;
    color: var(--green);
}
.checklist-complete-icon {
    font-size: 18px;
}
```

### 7.4 Coach Marks

```css
/* Coach Marks */
.coach-mark {
    position: absolute;
    z-index: 50;
    background: var(--bg-card);
    border: 1px solid var(--accent);
    border-radius: 8px;
    padding: 1rem;
    max-width: 320px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
    animation: fadeIn 0.25s ease;
}

.coach-mark::before {
    content: '';
    position: absolute;
    top: -6px;
    left: 24px;
    width: 12px;
    height: 12px;
    background: var(--bg-card);
    border-left: 1px solid var(--accent);
    border-top: 1px solid var(--accent);
    transform: rotate(45deg);
}

.coach-mark-body {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text);
    margin-bottom: 0.75rem;
}

.coach-mark-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.coach-mark-count {
    font-size: 12px;
    color: var(--text-muted);
}
```

### 7.5 Feature Hints

```css
/* Feature Hints (inline, non-blocking) */
.feature-hint {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: rgba(30, 215, 96, 0.05);
    border: 1px solid rgba(30, 215, 96, 0.15);
    border-radius: 8px;
    margin-bottom: 1rem;
    font-size: 13px;
}

.feature-hint-badge {
    background: var(--accent);
    color: #000;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    flex-shrink: 0;
}

.feature-hint-text {
    flex: 1;
    color: var(--text);
    line-height: 1.4;
}

.feature-hint-dismiss {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
    flex-shrink: 0;
}
.feature-hint-dismiss:hover {
    color: var(--text);
}
```

### 7.6 Wizard Toast (Micro-encouragement)

```css
/* Wizard Toast */
.wizard-toast {
    position: fixed;
    bottom: 2rem;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1.25rem;
    font-size: 13px;
    color: var(--text);
    opacity: 0;
    transition: opacity 0.3s, transform 0.3s;
    z-index: 100;
    pointer-events: none;
    max-width: 480px;
    text-align: center;
}

.wizard-toast.visible {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
}

@media (prefers-reduced-motion: reduce) {
    .wizard-toast {
        transition: none;
    }
}
```

### 7.7 Success Banner

```css
/* Success Banner */
.success-banner {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: rgba(30, 215, 96, 0.1);
    border: 1px solid rgba(30, 215, 96, 0.2);
    border-radius: 8px;
    margin-bottom: 1rem;
    animation: fadeIn 0.25s ease;
}

.success-banner-icon {
    color: var(--green);
    font-size: 20px;
    flex-shrink: 0;
}
```

### 7.8 Wizard Intro Banner (First Agent Only)

```css
/* Wizard Intro Banner */
.wizard-intro-banner {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.25rem;
    background: rgba(30, 215, 96, 0.05);
    border: 1px solid rgba(30, 215, 96, 0.15);
    border-radius: 8px;
    margin-bottom: 1.5rem;
}

.wizard-intro-content strong {
    display: block;
    margin-bottom: 0.25rem;
    font-size: 14px;
}

.wizard-intro-content p {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.5;
    margin: 0;
}
```

---

## 8. HTMX Integration Notes

### 8.1 Architecture

All onboarding state is server-authoritative. The client uses HTMX for partial updates; the wizard steps themselves are pure client-side JavaScript (already implemented) since the form is a single POST.

#### State Tracking

| State | Storage | Persistence |
|-------|---------|-------------|
| `operator_welcomed` | `operator_settings` table or signed cookie | Permanent |
| `setup_checklist_dismissed` | Session cookie | Until dismissed |
| `dismissed_hints` | Signed cookie (`calloway_hints`) | 90 days |
| Wizard step progress | Client-side JS (already works) | Per page load |
| Checklist completion items | Derived from DB queries | Real-time |

#### Cookie Format for Hints

```
calloway_hints = "hint-autonomy,hint-test-sms,hint-knowledge-base"
```

Comma-separated list of dismissed hint IDs. Read server-side in Jinja2 context to conditionally render hints.

### 8.2 HTMX Endpoints

| Endpoint | Method | Purpose | Returns |
|----------|--------|---------|---------|
| `/console/dashboard/setup-progress` | GET | Fetch current checklist state | Partial HTML |
| `/console/dismiss-setup-checklist` | POST | Hide checklist permanently | Empty (204) |
| `/console/hints/{hint_id}` | DELETE | Dismiss a specific hint | Empty (204), sets cookie |

### 8.3 Wizard Enhancement — No HTMX Needed

The wizard already works as a single client-side multi-step form. The enhancements (intro banner, tooltips, toasts) are all:
- Server-rendered conditionally via `{% if first_agent %}`
- Dismissed via pure JS (DOM removal) or cookie writes
- No additional HTMX round-trips needed during the wizard flow

### 8.4 Dashboard Conditional Rendering

```python
# In the dashboard route handler:
async def dashboard(request: Request):
    # ... existing logic ...
    tenant_count = await get_tenant_count()
    is_first_login = tenant_count == 0 and not request.cookies.get("calloway_welcomed")

    if is_first_login:
        response = _render(request, "welcome.html",
                           page_title="Welcome",
                           active_nav="dashboard")
        response.set_cookie("calloway_welcomed", "1",
                            max_age=86400*365*5, httponly=True)
        return response

    # Normal dashboard rendering...
    setup_complete = (
        tenant_count >= 1
        and await has_sent_test_sms()
        and request.cookies.get("calloway_viewed_conversation")
    )
    # Pass setup_complete to template context
```

---

## 9. Copy Guide

All user-facing copy, collected for editorial review and translation readiness.

### Welcome Screen
| Element | Copy |
|---------|------|
| Title | Welcome to Calloway |
| Subtitle | You're setting up something great. Let's get your first AI agent live and responding to clients. |
| Checklist header | Your setup checklist |
| CTA button | Create Your First Agent |
| Reassurance | Takes about 5 minutes. You can always change everything later. |
| Skip link | Or explore the dashboard first |

### Wizard (First Run Only)
| Element | Copy |
|---------|------|
| Intro banner title | Your first agent setup |
| Intro banner body | This wizard collects everything the AI needs to represent your client authentically. Most fields are editable later — focus on getting the basics right: name, phone, Twilio number, and tone. |
| Intro dismiss | Got it, let's start |
| Toast after Step 1 | Good start. The AI will use this info to introduce itself naturally. |
| Toast after Step 2 | Nice — this is what makes each agent's AI feel personal, not generic. |
| Toast after Step 4 | Smart choice. You can always adjust autonomy from the customer detail page. |
| Toast after Step 6 | Almost there. One more step. |

### Empty States
| Page | Title | Description | CTA |
|------|-------|-------------|-----|
| Dashboard (no tenants) | No customers yet | Create your first real estate agent customer to start seeing activity here. | Create First Customer |
| Customers | No customers yet | Each customer is a real estate agent whose AI assistant you manage. Create one to get started. | + Create Your First Customer |
| Messages | No conversations yet | Conversations appear here when contacts text your customers' AI numbers. Create a customer and send a test SMS to see it work. | Go to Customers |
| Automations | No automations scheduled | Follow-ups, review requests, and daily briefings show up here once your customers' AI agents start handling conversations. | (none) |
| Contacts tab | No contacts yet | Contacts are created automatically when someone texts this agent's Twilio number. You can also add them during the onboard wizard. | (none) |
| Listings tab | No listings yet | Add this agent's active listings so the AI can answer showing requests and provide property details. | + Add Listing |
| Automations tab | No scheduled automations | The AI creates automations (follow-ups, reminders, briefings) as it handles conversations. They'll appear here. | (none) |

### Setup Checklist
| Item | Completion state |
|------|-----------------|
| Create your first customer | Checked when tenant_count >= 1 |
| Send a test SMS | Checked when any tenant has test_sms_sent_at |
| Review an AI conversation | Checked when operator views conversation detail |
| Connect Google Calendar | Checked when any tenant has Google OAuth |

### Coach Marks
| Target | Copy |
|--------|------|
| Autonomy selector | Agents typically graduate from Supervised to Autonomous after 1-2 weeks of trust-building. |
| Test SMS button | Send a test SMS to verify the Twilio channel before the handoff call. |
| Knowledge Base tab | Upload listing details, FAQs, and agent-specific info here. The AI retrieves this during conversations. |
| Automations nav | Check here for scheduled follow-ups, reminders, and briefings the AI has queued. |
| Billing nav | Track subscription revenue and AI costs per customer here. |

### Success States
| Context | Copy |
|---------|------|
| Test SMS success banner | Test SMS sent successfully. [Agent name]'s AI is live and ready to respond. |
| Checklist complete | All set! You're ready to scale. |

---

## 10. Accessibility

### Requirements

1. **All coach marks and toasts use `role="status"` and `aria-live="polite"`** so screen readers announce them without interrupting.

2. **Checklist items use semantic list markup** (`<ol>` or `<ul>`) with `aria-label` on the container.

3. **Empty states include descriptive text** — never rely on icon-only communication.

4. **Coach mark dismiss buttons have `aria-label="Dismiss tip"`** since the `x` character alone is not descriptive.

5. **Progress bar uses `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`:**

```html
<div class="setup-progress-bar"
     role="progressbar"
     aria-valuenow="{{ done_count }}"
     aria-valuemin="0"
     aria-valuemax="{{ total_count }}"
     aria-label="Setup progress: {{ done_count }} of {{ total_count }} steps complete">
    <div class="setup-progress-fill"
         style="width: {{ (done_count / total_count * 100)|int }}%"></div>
</div>
```

6. **Wizard toasts respect `prefers-reduced-motion`** — CSS transitions disabled, content still appears.

7. **Focus management on coach marks** — When a coach mark appears, focus moves to its dismiss button. When dismissed, focus returns to the element the coach mark was anchored to.

8. **Color is never the only indicator** — Checked items show a checkmark character alongside the green color. Error states include text labels.

---

## Implementation Priority

| Phase | Work | Effort |
|-------|------|--------|
| **P0 — Ship first** | Welcome screen, empty states for all pages, setup checklist on dashboard | 2-3 days |
| **P1 — First week** | Wizard first-run enhancements (intro banner, toasts), success banner on test SMS | 1-2 days |
| **P2 — Second week** | Coach marks system, feature hints, hint dismissal via cookies | 2-3 days |
| **P3 — Later** | What's New changelog section, advanced hint targeting (time-based) | 1 day |

Total estimated effort: **6-9 engineering days** for the full onboarding system.

---

*End of spec. Ready for @eng review.*
