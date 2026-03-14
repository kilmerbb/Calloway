# Customer Detail Page — Tabbed Command Center Design Specification

**Author:** Lyra, Product Designer
**Date:** 2026-03-14
**Status:** Ready for Engineering

---

## 1. Overview

The Customer detail page (`/console/tenants/:id`) is being redesigned from a two-column layout into a tabbed command center. The current page shows profile, messages, contacts, listings, and automations in a cramped split view. The new design promotes each section to a full-width tab, giving every data type room to breathe.

### Tab Structure

| # | Tab | Content | Source |
|---|-----|---------|--------|
| 1 | Profile | Agent info, config, stats | Existing (refactored) |
| 2 | Messages | Conversations by contact | **New design** |
| 3 | Knowledge Base | RAG document inventory | **New design** |
| 4 | Contacts | Contact list | Existing (promoted to full-width) |
| 5 | Listings | Property listings | Existing (promoted to full-width) |
| 6 | Automations | Scheduled triggers | Existing (promoted to full-width) |

---

## 2. Page-Level Layout

### ASCII Wireframe — Page Shell

```
┌──────────────────────────────────────────────────────────────────────┐
│  TOPBAR:  [< Customers]  Customer Name   [status badge]             │
│           ──────────────────────────────────────────────────────     │
│           [Edit Settings] [Test SMS] [Deactivate]                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────┬──────────┬───────────────┬──────────┬──────────┬──────┐ │
│  │ Profile │ Messages │ Knowledge Base│ Contacts │ Listings │ Auto │ │
│  ├─────────┴──────────┴───────────────┴──────────┴──────────┴──────┤ │
│  │                                                                  │ │
│  │               (Active tab content area)                          │ │
│  │               Full width, no sidebar split                       │ │
│  │               Min-height: 400px                                  │ │
│  │                                                                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Tab Bar

Reuses the `.tab-bar` and `.tab-btn` CSS already defined in `style.css` (from the sidebar redesign spec). No new tab CSS required.

```html
<div class="tab-bar" role="tablist" aria-label="Customer sections">
    <button class="tab-btn active" role="tab" aria-selected="true"
            aria-controls="panel-profile" id="tab-profile"
            data-tab="profile">Profile</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            aria-controls="panel-messages" id="tab-messages"
            data-tab="messages">Messages</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            aria-controls="panel-kb" id="tab-kb"
            data-tab="kb">Knowledge Base</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            aria-controls="panel-contacts" id="tab-contacts"
            data-tab="contacts">Contacts</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            aria-controls="panel-listings" id="tab-listings"
            data-tab="listings">Listings</button>
    <button class="tab-btn" role="tab" aria-selected="false"
            aria-controls="panel-automations" id="tab-automations"
            data-tab="automations">Automations</button>
</div>
```

### Tab Switching

Use the same client-side JS pattern from the System Health page. Each panel has `role="tabpanel"`, `aria-labelledby`, and toggles via `.active` class. Support URL hash (`#messages`, `#kb`) so tabs are deep-linkable.

```js
// Tab switching (reuse existing pattern from health page)
document.querySelectorAll('[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        // Remove active from all tabs and panels
        document.querySelectorAll('.tab-btn').forEach(b => {
            b.classList.remove('active');
            b.setAttribute('aria-selected', 'false');
        });
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        // Activate clicked tab and its panel
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
        const panel = document.getElementById(btn.getAttribute('aria-controls'));
        panel.classList.add('active');
        // Update URL hash
        history.replaceState(null, '', '#' + btn.dataset.tab);
    });
});
// On load, activate tab from hash
const hash = location.hash.replace('#', '');
if (hash) document.querySelector(`[data-tab="${hash}"]`)?.click();
```

---

## 3. Profile Tab (Refactored Existing)

The Profile tab absorbs the current page content into a full-width layout. Stats move from the sidebar to a top card row.

### ASCII Wireframe

```
┌──────────────────────────────────────────────────────────────────────┐
│  STATS ROW                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ COST          │  │ MESSAGES     │  │ ERRORS 24H   │               │
│  │ $12.45        │  │ 342          │  │ 0            │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  PROFILE                          │  CONFIGURATION                   │
│  ┌────────────────────────────┐   │  ┌────────────────────────────┐  │
│  │ Name:      Jane Smith      │   │  │ > Style Profile            │  │
│  │ Email:     jane@email.com  │   │  │ > Autonomy Rules           │  │
│  │ Phone:     +1 555 0100    │   │  │ > Scheduling Prefs         │  │
│  │ Brokerage: Keller Williams │   │  │ > Raw Agent Record (JSON)  │  │
│  │ Market:    Austin, TX      │   │  └────────────────────────────┘  │
│  │ Timezone:  US/Central      │   │                                  │
│  │ Twilio #:  +1 555 0200    │   │                                  │
│  └────────────────────────────┘   │                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Layout

- Stats row: `.card-grid` with `grid-template-columns: repeat(3, 1fr)` and `max-width: 600px`
- Below stats: two-column grid `grid-template-columns: 1fr 1fr` with `gap: 24px`
- Profile table: existing `<table>` markup
- Configuration: existing `<details>` accordions

---

## 4. Messages Tab — Detailed Design

### 4.1 User Flow

```
User Flow: View Conversations

## Entry Points
- Click "Messages" tab on Customer detail page
- Deep link: /console/tenants/:id#messages

## Flow Steps
1. Messages tab loads → Contact list appears (sorted by most recent message)
2. User clicks a contact → Conversation thread expands/reveals on right
3. User reads thread → Scrolls through messages (newest at bottom)
4. User clicks "Refresh" → Thread reloads with latest messages
5. User clicks a different contact → Previous thread hides, new one loads

## Decision Points
* If no conversations exist → Show empty state
* If contact has tool calls in messages → Show expandable <details> blocks

## Error Paths
* API failure loading contacts → Error banner with retry button
* API failure loading thread → Error message in thread area with retry

## Exit Points
- Click another tab
- Click breadcrumb to Customers list
```

### 4.2 ASCII Wireframe — Messages Tab (Desktop)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Messages (47 conversations)                    [Refresh ↻]          │
├──────────────────────┬───────────────────────────────────────────────┤
│                      │                                               │
│  CONTACT LIST        │  CONVERSATION THREAD                          │
│  (scrollable)        │                                               │
│                      │  ┌─ Contact: Sarah Chen ─────────────────┐    │
│  ┌────────────────┐  │  │  +1 (555) 012-3456  SMS               │    │
│  │ ● Sarah Chen   │  │  └──────────────────────────────────────┘    │
│  │   SMS  12 msgs │  │                                               │
│  │   "Thanks for  │  │  ┌─────────────────────────────────────────┐  │
│  │   the info..." │  │  │ [Client] Sarah Chen         Mar 12 9:01 │  │
│  │     2h ago     │  │  │ Hi, I'm interested in the property on   │  │
│  ├────────────────┤  │  │ Oak Street. Is it still available?       │  │
│  │   John Rivera  │  │  └─────────────────────────────────────────┘  │
│  │   SMS  8 msgs  │  │                                               │
│  │   "I'll be th" │  │  ┌─────────────────────────────────────────┐  │
│  │     1d ago     │  │  │ [Cal]                       Mar 12 9:02 │  │
│  ├────────────────┤  │  │ Hi Sarah! Yes, 742 Oak Street is still  │  │
│  │   Lisa Park    │  │  │ available. Would you like to schedule a  │  │
│  │   RCS  3 msgs  │  │  │ showing?                                │  │
│  │   "When can we"│  │  │                                         │  │
│  │     3d ago     │  │  │ ┌─ Tool Call ──────────────────────┐    │  │
│  ├────────────────┤  │  │ │ > lookup_listing("742 Oak St")   │    │  │
│  │                │  │  │ └──────────────────────────────────┘    │  │
│  │  (more...)     │  │  └─────────────────────────────────────────┘  │
│  │                │  │                                               │
│  └────────────────┘  │  ┌─────────────────────────────────────────┐  │
│                      │  │ [System]                    Mar 12 9:02 │  │
│                      │  │ Showing scheduled for Mar 14 at 2:00 PM │  │
│                      │  └─────────────────────────────────────────┘  │
│                      │                                               │
└──────────────────────┴───────────────────────────────────────────────┘
```

### 4.3 ASCII Wireframe — Messages Tab (Empty State)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Messages                                       [Refresh ↻]          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                                                                      │
│                         ◬                                            │
│                   No messages yet                                    │
│                                                                      │
│           This customer hasn't received any                          │
│           messages. Conversations will appear                        │
│           here once contacts start texting.                          │
│                                                                      │
│                   [Send Test SMS]                                     │
│                                                                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.4 Component Inventory — Messages Tab

#### Contact List Item

| Property | Value |
|----------|-------|
| Container | `display: flex; flex-direction: column; gap: 4px; padding: 12px 16px; border-bottom: 1px solid var(--border); cursor: pointer;` |
| Hover | `background: var(--bg-hover);` |
| Selected | `background: rgba(30, 215, 96, 0.1); border-left: 2px solid var(--accent);` |
| Name | `font-size: 14px; font-weight: 600; color: var(--text);` |
| Meta row | `display: flex; align-items: center; gap: 8px;` |
| Channel badge | `.badge` (existing) — SMS=`badge-blue`, RCS=`badge-green`, Voice=`badge-yellow`, Email=`badge-gray` |
| Message count | `font-size: 12px; color: var(--text-muted);` e.g. "12 msgs" |
| Preview text | `font-size: 13px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px;` |
| Timestamp | `font-size: 12px; color: var(--text-subdued); margin-left: auto;` Relative format (e.g. "2h ago", "1d ago", "Mar 5") |

**States:**

| State | Behavior |
|-------|----------|
| Default | Muted text, no left border |
| Hover | `background: var(--bg-hover)` |
| Selected/Active | `background: rgba(30, 215, 96, 0.1); border-left: 2px solid var(--accent);` name color `var(--accent)` |
| Loading | Skeleton: 3 placeholder rows with shimmer animation |

#### Conversation Thread

| Property | Value |
|----------|-------|
| Container | `flex: 1; padding: 16px; overflow-y: auto; max-height: calc(100vh - 250px);` |
| Thread header | Contact name (16px, weight 600), phone number (13px, muted), channel badge |
| Header border | `border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 16px;` |

#### Message Bubble

| Property | Value |
|----------|-------|
| Container | `padding: 10px 14px; border-radius: 8px; margin-bottom: 8px; max-width: 85%;` |
| Client message | `background: var(--bg-hover); color: var(--text);` (left-aligned) |
| Cal (AI) message | `background: rgba(30, 215, 96, 0.1); color: var(--text);` (left-aligned, distinct tint) |
| System message | `background: rgba(255, 164, 43, 0.1); color: var(--text); font-style: italic; font-size: 13px;` |
| Sender badge | `.badge` inline before timestamp. Client=`badge-green`, Cal=`badge-blue`, System=`badge-gray` |
| Timestamp | `font-size: 11px; color: var(--text-muted); margin-top: 4px; display: block;` |
| Tool call block | `<details>` inside message bubble |

#### Tool Call Block (inside AI messages)

```html
<details class="tool-call">
    <summary>lookup_listing("742 Oak St")</summary>
    <pre class="tool-call-output">{ "address": "742 Oak St", "price": 450000, ... }</pre>
</details>
```

| Property | Value |
|----------|-------|
| Container | `margin-top: 8px; padding: 8px; background: var(--bg); border-radius: 6px; border: 1px solid var(--border);` |
| Summary | `font-size: 12px; font-family: monospace; color: var(--text-muted); cursor: pointer;` |
| Summary hover | `color: var(--accent);` |
| Output pre | `font-size: 11px; padding: 8px; margin-top: 8px; max-height: 200px; overflow: auto; background: var(--bg); border-radius: 4px;` |

#### Refresh Button

| Property | Value |
|----------|-------|
| Style | `.btn .btn-outline .btn-sm` (existing classes) |
| Label | "Refresh" with `↻` prefix |
| Position | Top-right of Messages tab header, `float: right` or flex-end |
| Loading state | Button text changes to "Loading...", disabled, `opacity: 0.6` |

### 4.5 CSS for Messages Tab

```css
/* Messages Layout */
.messages-layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    min-height: 500px;
    max-height: calc(100vh - 250px);
}

.messages-contact-list {
    background: var(--bg-card);
    border-right: 1px solid var(--border);
    overflow-y: auto;
}

.messages-thread {
    background: var(--bg);
    padding: 16px;
    overflow-y: auto;
}

/* Contact List Items */
.contact-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.15s;
    border-left: 2px solid transparent;
}

.contact-item:hover {
    background: var(--bg-hover);
}

.contact-item.active {
    background: rgba(30, 215, 96, 0.1);
    border-left-color: var(--accent);
}

.contact-item-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
}

.contact-item.active .contact-item-name {
    color: var(--accent);
}

.contact-item-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-muted);
}

.contact-item-preview {
    font-size: 13px;
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.contact-item-time {
    font-size: 12px;
    color: var(--text-subdued);
    margin-left: auto;
    flex-shrink: 0;
}

/* Thread Header */
.thread-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-bottom: 12px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border);
}

.thread-header-name {
    font-size: 16px;
    font-weight: 600;
}

.thread-header-phone {
    font-size: 13px;
    color: var(--text-muted);
}

/* Message Bubbles */
.msg {
    padding: 10px 14px;
    border-radius: 8px;
    margin-bottom: 8px;
    max-width: 85%;
}

.msg-client {
    background: var(--bg-hover);
}

.msg-ai {
    background: rgba(30, 215, 96, 0.1);
}

.msg-system {
    background: rgba(255, 164, 43, 0.1);
    font-style: italic;
    font-size: 13px;
}

.msg-sender {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}

.msg-timestamp {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 4px;
}

/* Tool Call Blocks */
.tool-call {
    margin-top: 8px;
    padding: 8px;
    background: var(--bg);
    border-radius: 6px;
    border: 1px solid var(--border);
}

.tool-call summary {
    font-size: 12px;
    font-family: 'SF Mono', 'Fira Code', monospace;
    color: var(--text-muted);
    cursor: pointer;
}

.tool-call summary:hover {
    color: var(--accent);
}

.tool-call-output {
    font-size: 11px;
    padding: 8px;
    margin-top: 8px;
    max-height: 200px;
    overflow: auto;
    background: var(--bg);
    border-radius: 4px;
    white-space: pre-wrap;
    word-break: break-word;
}

/* Thread Empty State (no contact selected) */
.thread-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    gap: 8px;
}

.thread-empty-icon {
    font-size: 32px;
    opacity: 0.5;
}

/* Messages Empty State (no conversations at all) */
.messages-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 24px;
    text-align: center;
    color: var(--text-muted);
    gap: 12px;
}

.messages-empty-icon {
    font-size: 40px;
    opacity: 0.4;
}

.messages-empty-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
}

.messages-empty-desc {
    font-size: 14px;
    max-width: 320px;
    line-height: 1.5;
}
```

### 4.6 Interaction Specs — Messages Tab

#### Select Contact

```
Trigger: Click on contact-item in the list
Sequence:
1. Remove .active from previously selected contact-item
2. Add .active to clicked contact-item
3. Load conversation thread via HTMX: hx-get="/console/tenants/:id/messages/:contact_id"
4. Thread area shows skeleton loading (3 shimmer rows) for up to 300ms
5. Thread content replaces skeleton
Animation: fadeIn 0.2s ease on thread content
```

#### Refresh Conversations

```
Trigger: Click "Refresh" button
Sequence:
1. Button text changes to "Loading...", button becomes disabled (opacity: 0.6)
2. HTMX request: hx-get="/console/tenants/:id/messages" hx-target="#panel-messages"
3. Contact list and thread reload
4. Previously selected contact re-selects if still in list
5. Button reverts to "Refresh"
Duration: Spinner visible for minimum 300ms to avoid flash
```

#### Expand Tool Call

```
Trigger: Click <details> summary in a message bubble
Sequence:
1. Native <details> toggle — no custom JS needed
2. Pre block renders with monospace font, scrollable
Animation: None (native browser behavior)
```

---

## 5. Knowledge Base Tab — Detailed Design

### 5.1 User Flow

```
User Flow: Manage Knowledge Base

## Entry Points
- Click "Knowledge Base" tab on Customer detail page
- Deep link: /console/tenants/:id#kb

## Flow Steps
1. KB tab loads → Global settings row visible at top
2. Grouped sections render by source type
3. User clicks "Remove" on an item → Confirm dialog → Item removed
4. User clicks "Re-index" on an item → Item status changes to "Indexing..."
5. User clicks "Set Expiration" → Inline date picker appears → Confirm
6. User clicks "Add Document" → File upload modal or inline form

## Decision Points
* If no items exist → Show empty state with "Add Document" CTA
* If items expiring within 7 days → Show warning badge "Expiring Soon"
* If items past expiration → Show red "Expired" badge

## Error Paths
* Re-index fails → Toast notification: "Failed to re-index [title]. Try again."
* Upload fails → Error message in upload area

## Exit Points
- Click another tab
- Click breadcrumb to Customers list
```

### 5.2 ASCII Wireframe — Knowledge Base Tab

```
┌──────────────────────────────────────────────────────────────────────┐
│  Knowledge Base (24 items)                       [+ Add Document]    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  GLOBAL SETTINGS                                                     │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Default expiration: [90 days ▾]    Behavior: [Remind only ▾]│    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ── Conversations (12) ──────────────────────────────────────────    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ Sarah Chen — Showing inquiry    [CONVERSATION]  Active       │    │
│  │ Indexed: Mar 10  |  3 chunks  |  Expires: Jun 10             │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │ John Rivera — Price negotiation [CONVERSATION]  Expiring Soon│    │
│  │ Indexed: Dec 15  |  7 chunks  |  Expires: Mar 18   ⚠        │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ── Contacts (5) ───────────────────────────────────────────────    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ Sarah Chen — Contact profile    [CONTACT]       Active       │    │
│  │ Indexed: Mar 10  |  1 chunk   |  No expiration               │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ── Listings (4) ───────────────────────────────────────────────    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ 742 Oak Street — $450,000       [LISTING]       Active       │    │
│  │ Indexed: Mar 8   |  2 chunks  |  No expiration               │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ── Documents (3) ──────────────────────────────────────────────    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ Agent Bio.pdf                   [DOCUMENT]      Active       │    │
│  │ Indexed: Feb 20  |  4 chunks  |  Expires: May 20             │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  ├──────────────────────────────────────────────────────────────┤    │
│  │ Market Report Q1.pdf            [DOCUMENT]      Expired      │    │
│  │ Indexed: Jan 5   |  8 chunks  |  Expired: Mar 5   ✕         │    │
│  │                                [Remove] [Re-index] [Expire]  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.3 ASCII Wireframe — Knowledge Base (Empty State)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Knowledge Base                                  [+ Add Document]    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                                                                      │
│                         ◉                                            │
│                  Nothing indexed yet                                 │
│                                                                      │
│           The knowledge base is empty. As this                       │
│           customer communicates with contacts,                       │
│           conversations and contact profiles will                    │
│           be automatically indexed here.                             │
│                                                                      │
│           You can also upload documents manually.                    │
│                                                                      │
│                   [+ Add Document]                                    │
│                                                                      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 5.4 Component Inventory — Knowledge Base Tab

#### Global Settings Row

| Property | Value |
|----------|-------|
| Container | `display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: var(--bg-card); border-radius: 8px; margin-bottom: 24px; flex-wrap: wrap;` |
| Labels | `font-size: 13px; color: var(--text-muted);` |
| Dropdowns | Existing `<select>` styles. Width: `auto` (content-sized) |
| Expiration options | 30 days, 60 days, 90 days, 180 days, 1 year, No expiration |
| Behavior options | Auto-remove, Remind only |

#### Source Group Header

| Property | Value |
|----------|-------|
| Container | `display: flex; align-items: center; gap: 8px; padding: 8px 0; margin-top: 24px; margin-bottom: 8px;` |
| Line | `flex: 1; height: 1px; background: var(--border);` |
| Label | `font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap;` |
| Count | `font-size: 12px; color: var(--text-subdued);` in parentheses |

```html
<!-- Source group header pattern -->
<div class="kb-group-header">
    <span class="kb-group-label">Conversations (12)</span>
    <span class="kb-group-line"></span>
</div>
```

```css
.kb-group-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 24px;
    margin-bottom: 8px;
}

.kb-group-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
}

.kb-group-line {
    flex: 1;
    height: 1px;
    background: var(--border);
}
```

#### Knowledge Base Item Card

| Property | Value |
|----------|-------|
| Container | `padding: 12px 16px; background: var(--bg-card); border-bottom: 1px solid var(--border); transition: background 0.15s;` |
| First item | `border-radius: 8px 8px 0 0;` |
| Last item | `border-radius: 0 0 8px 8px; border-bottom: none;` |
| Only item | `border-radius: 8px; border-bottom: none;` |
| Hover | `background: var(--bg-hover);` |
| Row 1 (header) | `display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;` |
| Title | `font-size: 14px; font-weight: 500; color: var(--text);` |
| Source type badge | `.badge` with source-specific color (see below) |
| Status badge | See status badge spec below |
| Row 2 (meta) | `font-size: 12px; color: var(--text-muted);` pipe-separated |
| Row 3 (actions) | `display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px;` |

**Source Type Badges:**

| Source | Class | Colors |
|--------|-------|--------|
| Conversation | `badge-blue` | `rgba(30,215,96,0.15)` bg, `var(--accent)` text |
| Contact | `badge-gray` | `rgba(148,163,184,0.15)` bg, `var(--text-muted)` text |
| Listing | `badge-yellow` | `rgba(234,179,8,0.15)` bg, `var(--yellow)` text |
| Document | `badge-blue` | `rgba(30,215,96,0.15)` bg, `var(--accent)` text |

**Status Badges:**

| Status | Condition | Badge | Colors |
|--------|-----------|-------|--------|
| Active | Expiration > 7 days away or no expiration | `badge-green` | Green bg/text |
| Expiring Soon | Expiration within 7 days | `badge-yellow` + `⚠` suffix | Yellow bg/text |
| Expired | Past expiration date | `badge-red` + `✕` suffix | Red bg/text |

**Action Buttons:**

| Button | Style | Behavior |
|--------|-------|----------|
| Remove | `.btn .btn-outline .btn-sm` | Confirm dialog: "Remove [title] from knowledge base? This cannot be undone." → POST delete |
| Re-index | `.btn .btn-outline .btn-sm` | Button text → "Indexing..." (disabled) → POST re-index → revert on success |
| Set Expiration | `.btn .btn-outline .btn-sm` | Label shows "Expire" normally. Click reveals inline date input (type="date") with Save/Cancel |

**States:**

| State | Behavior |
|-------|----------|
| Default | Card with meta info and action buttons |
| Hover | `background: var(--bg-hover)` |
| Re-indexing | "Re-index" button disabled, text "Indexing...", opacity 0.6 |
| Loading | Skeleton: 3 placeholder cards with shimmer |
| Empty | Full empty state (see wireframe 5.3) |

#### Add Document Button

| Property | Value |
|----------|-------|
| Style | `.btn .btn-primary .btn-sm` |
| Label | `+ Add Document` |
| Position | Top-right of KB tab header, aligned with tab title |
| Click behavior | Opens inline upload form or modal (see interaction spec below) |

### 5.5 CSS for Knowledge Base Tab

```css
/* Knowledge Base Layout */
.kb-settings {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: var(--bg-card);
    border-radius: 8px;
    margin-bottom: 24px;
    flex-wrap: wrap;
}

.kb-settings-label {
    font-size: 13px;
    color: var(--text-muted);
}

.kb-settings select {
    width: auto;
    min-width: 140px;
}

/* KB Item Cards */
.kb-item {
    padding: 12px 16px;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
}

.kb-item:hover {
    background: var(--bg-hover);
}

.kb-item:first-child {
    border-radius: 8px 8px 0 0;
}

.kb-item:last-child {
    border-radius: 0 0 8px 8px;
    border-bottom: none;
}

.kb-item:only-child {
    border-radius: 8px;
    border-bottom: none;
}

.kb-item-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}

.kb-item-title {
    font-size: 14px;
    font-weight: 500;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
}

.kb-item-status {
    display: flex;
    align-items: center;
    gap: 8px;
}

.kb-item-meta {
    font-size: 12px;
    color: var(--text-muted);
    display: flex;
    gap: 4px;
}

.kb-item-meta-sep::before {
    content: "|";
    margin: 0 4px;
    color: var(--border);
}

.kb-item-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 8px;
}

/* Add Document inline form (hidden by default) */
.kb-upload-form {
    display: none;
    padding: 16px;
    background: var(--bg-card);
    border: 1px dashed var(--border);
    border-radius: 8px;
    margin-bottom: 16px;
    text-align: center;
}

.kb-upload-form.active {
    display: block;
    animation: fadeIn 0.2s ease;
}

.kb-upload-dropzone {
    padding: 32px;
    border: 2px dashed var(--border);
    border-radius: 8px;
    color: var(--text-muted);
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
}

.kb-upload-dropzone:hover,
.kb-upload-dropzone.dragover {
    border-color: var(--accent);
    background: rgba(30, 215, 96, 0.05);
}

/* Empty State */
.kb-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px 24px;
    text-align: center;
    color: var(--text-muted);
    gap: 12px;
}

.kb-empty-icon {
    font-size: 40px;
    opacity: 0.4;
}

.kb-empty-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
}

.kb-empty-desc {
    font-size: 14px;
    max-width: 360px;
    line-height: 1.5;
}
```

### 5.6 Interaction Specs — Knowledge Base Tab

#### Remove Item

```
Trigger: Click "Remove" button on KB item
Sequence:
1. Browser confirm dialog: "Remove [title] from knowledge base? This cannot be undone."
2. If confirmed → POST /console/tenants/:id/kb/:item_id/remove
3. Item fades out (opacity 0, height 0 over 200ms)
4. Item removed from DOM
5. Group header count decrements
6. If group now empty, group header hides
Feedback: Toast or flash message: "[title] removed from knowledge base"
```

#### Re-index Item

```
Trigger: Click "Re-index" button on KB item
Sequence:
1. Button text changes to "Indexing..." + disabled state (opacity 0.6, pointer-events: none)
2. POST /console/tenants/:id/kb/:item_id/reindex
3. On success: Button reverts to "Re-index", "Indexed" date updates to today
4. On failure: Button reverts, show error toast
Duration: Button stays in loading state until response (typically 1-3 seconds)
```

#### Set Expiration

```
Trigger: Click "Expire" button on KB item
Sequence:
1. Button transforms into inline form: [date input] [Save] [Cancel]
2. Date input defaults to current expiration or 90 days from today
3. User selects date → clicks Save
4. POST /console/tenants/:id/kb/:item_id/expire with new date
5. On success: Inline form reverts to "Expire" button, expiration date updates
6. Cancel: Inline form reverts without changes
Animation: Inline form appears with fadeIn 0.2s ease
```

#### Add Document

```
Trigger: Click "+ Add Document" button
Sequence:
1. Upload form area appears below settings row (slideDown + fadeIn, 200ms)
2. Dropzone: "Drag and drop a file, or click to browse" with dashed border
3. On file select: Show filename, file size, [Upload] [Cancel] buttons
4. Upload: POST /console/tenants/:id/kb/upload (multipart)
5. Progress: Button shows "Uploading..." with disabled state
6. On success: Form hides, new item appears in Documents group
7. On failure: Error message inline: "Upload failed. Maximum file size is 10MB."
Animation: Form slideDown 200ms ease. New item fadeIn 200ms ease.
```

#### Update Global Settings

```
Trigger: Change dropdown value in global settings row
Sequence:
1. POST /console/tenants/:id/kb/settings with new values
2. Dropdown shows brief "Saved" feedback (checkmark icon or green flash on border, 1s)
3. If behavior changed to "Auto-remove", show confirm: "Expired items will be automatically removed. Continue?"
```

---

## 6. Responsive Behavior

### Desktop (1200px+)

- Messages tab: 280px contact list sidebar + fluid thread area
- Knowledge Base: Full-width cards, settings row horizontal
- Tab bar: All 6 tabs visible inline

### Tablet (768px - 1199px)

- Messages tab: Contact list collapses to 220px, thread area fluid
- Knowledge Base: Unchanged, cards are already full-width
- Tab bar: All tabs visible, text may truncate. Reduce padding to `8px 14px`

### Mobile (< 768px)

- **Tab bar**: Horizontal scroll with `-webkit-overflow-scrolling: touch`. Add `overflow-x: auto; white-space: nowrap;` to `.tab-bar`. Only 3-4 tabs visible at once; user scrolls for the rest.
- **Messages tab**: Stacked layout. Contact list takes full width. Clicking a contact navigates to a thread view (replaces contact list). Back button at top of thread returns to list.
- **Knowledge Base**: Settings row wraps to stacked layout (`flex-direction: column`). Item cards full-width. Action buttons wrap to new row.
- **Profile tab**: Stats cards stack to single column. Profile/Config sections stack vertically.

```css
@media (max-width: 768px) {
    .tab-bar {
        overflow-x: auto;
        white-space: nowrap;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;  /* Firefox */
    }
    .tab-bar::-webkit-scrollbar {
        display: none;          /* Chrome/Safari */
    }

    .messages-layout {
        grid-template-columns: 1fr;
    }

    .messages-contact-list {
        border-right: none;
        border-bottom: 1px solid var(--border);
        max-height: none;
    }

    /* On mobile, show either contact list OR thread, not both */
    .messages-layout.thread-open .messages-contact-list {
        display: none;
    }

    .messages-layout:not(.thread-open) .messages-thread {
        display: none;
    }

    .kb-settings {
        flex-direction: column;
        align-items: flex-start;
        gap: 12px;
    }

    .kb-item-actions {
        flex-wrap: wrap;
    }
}
```

---

## 7. Accessibility Notes

### Tab Bar

| Requirement | Implementation |
|------------|----------------|
| ARIA roles | `role="tablist"` on container, `role="tab"` on buttons, `role="tabpanel"` on panels |
| ARIA attributes | `aria-selected="true/false"` on tabs, `aria-controls` linking tab to panel, `aria-labelledby` on panel linking to tab |
| Keyboard navigation | Arrow Left/Right moves between tabs. Home/End jump to first/last tab. Tab key moves focus into the panel. |
| Focus management | When tab activates, focus stays on the tab button (not the panel) |
| Screen reader | Tab changes announced via aria-selected state change |

### Messages Tab

| Requirement | Implementation |
|------------|----------------|
| Contact list | `role="listbox"` with `role="option"` on each contact. `aria-selected` on active contact. |
| Thread | `role="log"` on thread container. `aria-live="polite"` for new messages on refresh. |
| Message sender | Sender type included as visible badge text (not color-only). Screen reader reads "Client: Sarah Chen" or "AI: Cal" |
| Tool calls | `<details>` is natively accessible. Summary text is descriptive ("Tool call: lookup_listing") |
| Refresh button | `aria-label="Refresh conversations"` |
| Empty state | `role="status"` on empty state container |

### Knowledge Base Tab

| Requirement | Implementation |
|------------|----------------|
| Status indicators | Status uses text label + color (not color alone). "Active", "Expiring Soon", "Expired" are readable text. |
| Warning icon | `⚠` has `aria-label="Warning: expiring soon"` or is supplemented by `.sr-only` text |
| Action buttons | Each button has descriptive `aria-label`: "Remove [title] from knowledge base", "Re-index [title]", "Set expiration for [title]" |
| Confirm dialogs | Native `confirm()` is accessible. Future: use a proper modal with focus trap. |
| Upload dropzone | `role="button"`, `aria-label="Upload document"`. Keyboard activatable via Enter/Space. |

### Color Contrast (verified against existing palette)

| Combination | Ratio | WCAG Level |
|------------|-------|------------|
| `var(--text)` (#FFF) on `var(--bg)` (#121212) | 17.4:1 | AAA |
| `var(--text-muted)` (#B3B3B3) on `var(--bg-card)` (#181818) | 7.5:1 | AAA |
| `var(--accent)` (#1ED760) on `var(--bg-card)` (#181818) | 5.2:1 | AA |
| `var(--text-muted)` (#B3B3B3) on `var(--bg-hover)` (#282828) | 5.8:1 | AA |
| `var(--yellow)` (#FFA42B) on `var(--bg-card)` (#181818) | 6.4:1 | AA |
| `var(--red)` (#E91429) on `rgba(239,68,68,0.15)` tint | 4.8:1 | AA |

### Reduced Motion

All animations and transitions are already governed by the existing `@media (prefers-reduced-motion: reduce)` rule in `style.css`. New components that use `transition` or `animation` must also be included in that media query. The CSS above uses `transition: background 0.15s` and `animation: fadeIn 0.2s ease`, both of which are already covered by the existing rule targeting `.tab-panel` and using the `fadeIn` keyframe.

---

## 8. Loading States

### Skeleton Patterns

Use the shimmer skeleton pattern from the Spotify design reference:

```css
.skeleton {
    background: linear-gradient(
        90deg,
        var(--bg-card) 25%,
        var(--bg-hover) 50%,
        var(--bg-card) 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s linear infinite;
    border-radius: 4px;
}

@keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

.skeleton-text {
    height: 14px;
    margin-bottom: 8px;
}

.skeleton-text-short {
    width: 60%;
}

.skeleton-text-long {
    width: 90%;
}

.skeleton-badge {
    height: 20px;
    width: 60px;
    border-radius: 4px;
}
```

### Where Skeletons Appear

| Tab | Skeleton Content |
|-----|-----------------|
| Messages — Contact list loading | 5 rows: each with skeleton name (120px), skeleton badge (50px), skeleton preview (180px) |
| Messages — Thread loading | 4 message bubbles: alternating widths (60%, 75%, 50%, 80%) |
| Knowledge Base loading | 3 item cards: each with skeleton title (200px) + skeleton meta (150px) |
| Profile loading | Stat cards skeleton (3 cards) + table rows skeleton (7 rows) |

---

## 9. Implementation Notes for Atlas

### File Changes Required

1. **`app/templates/console/tenant_detail.html`** — Complete rewrite to tabbed layout
2. **`app/static/console/style.css`** — Add all new CSS from sections 4.5, 5.5, 6, and 8
3. **`app/api/console.py`** — New endpoints:
   - `GET /console/tenants/:id/messages/:contact_id` — returns conversation thread HTML partial
   - `GET /console/tenants/:id/kb` — returns KB items (or add to existing detail endpoint)
   - `POST /console/tenants/:id/kb/:item_id/remove` — delete KB item
   - `POST /console/tenants/:id/kb/:item_id/reindex` — re-index KB item
   - `POST /console/tenants/:id/kb/settings` — update global KB settings
   - `POST /console/tenants/:id/kb/upload` — upload document
4. **`app/services/console_queries.py`** — New queries for KB items grouped by source type, conversation threads grouped by contact

### Data Requirements

**Messages Tab** needs the backend to provide:
- List of contacts with: `contact_id`, `name`, `phone`, `channel`, `message_count`, `last_message_preview` (first 60 chars), `last_message_at`
- Per-contact thread: all messages ordered by `created_at` ASC, each with `sender_type`, `contact_name`, `body`, `created_at`, `model_used`, `tool_calls` (JSON)

**Knowledge Base Tab** needs:
- List of KB items with: `id`, `title`, `source_type` (conversation|contact|listing|document), `indexed_at`, `chunk_count`, `expires_at`, `status` (active|expiring_soon|expired)
- Global KB settings: `default_expiration_days`, `expiration_behavior` (auto_remove|remind_only)

### Implementation Sequence

1. Add new CSS to `style.css`
2. Restructure `tenant_detail.html` with tab bar and 6 panels
3. Profile tab: rearrange existing content (no new data needed)
4. Contacts/Listings/Automations tabs: move existing sidebar content to full-width panels (no new data needed)
5. Messages tab: requires new backend query + HTMX partials
6. Knowledge Base tab: requires new data model + backend endpoints

### HTMX Integration

- Tab switching: client-side JS (all panels rendered on page load for Profile, Contacts, Listings, Automations)
- Messages tab: HTMX lazy-load on tab activation (`hx-trigger="click"` on Messages tab button, `hx-get="/console/tenants/:id/messages"`)
- Messages thread: HTMX load on contact click (`hx-get="/console/tenants/:id/messages/:contact_id"`, `hx-target="#thread-area"`)
- Knowledge Base: HTMX lazy-load on tab activation, same pattern as Messages
- KB actions (remove, re-index, set expiration): HTMX POST with `hx-swap` to update the item in place

---

## 10. What NOT to Change

- **Existing tab bar CSS** — Already defined and working. Reuse `.tab-bar`, `.tab-btn`, `.tab-panel` as-is.
- **Badge styles** — All existing badge classes (`.badge-green`, `.badge-blue`, etc.) are reused, not redefined.
- **Button styles** — Existing `.btn`, `.btn-outline`, `.btn-primary`, `.btn-danger`, `.btn-sm` classes apply throughout.
- **URL routes** — The base route `/console/tenants/:id` stays the same. Tabs are client-side hash navigation.
- **Color palette** — All new components use existing CSS custom properties from `:root`.
- **Database column names** — "tenant" in the data model is fine. Only user-facing text says "Customer".
