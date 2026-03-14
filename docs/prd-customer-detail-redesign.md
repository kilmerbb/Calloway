PRD: Customer Detail Page Redesign
Version: 1.0
Author: Mara, Product Manager
Status: Draft
Last Updated: 2026-03-14

---

## 1. Problem Statement

The Customer detail page (`/console/tenants/{agent_id}`) currently crams all operational data into a single scrolling view: agent profile, configuration, recent messages, contacts, listings, and pending automations. This creates three distinct problems:

**Visibility problem.** Operators can only see the 20 most recent messages in a flat, undifferentiated list. They cannot see full conversation threads, cannot tell which contact a message belongs to without cross-referencing, and cannot inspect what tools Cal invoked during a response. When an operator needs to audit AI behavior — the primary reason they visit this page — they are effectively blind.

**Knowledge base problem.** The RAG vector store (pgvector + Voyage AI embeddings) is deployed and actively used by the AI pipeline, but operators have zero visibility into what data is indexed, when it was indexed, whether it is stale, and no ability to manage it. There is no expiration/TTL mechanism, meaning the knowledge base accumulates stale data indefinitely — degrading retrieval quality over time.

**Information architecture problem.** The current single-page layout does not scale. As we add richer operational views (full conversation history, knowledge base management), the page becomes unusable. The existing data (contacts, listings, automations) is already cramped into a narrow sidebar with arbitrary truncation (15 contacts, 10 listings).

**Evidence:** This page is the primary workspace for operators managing customer accounts. Every support interaction, every AI audit, every configuration change routes through it. The current layout was adequate for an MVP but is now the bottleneck for operational efficiency.

---

## 2. Goals & Success Metrics

**Primary Goal:** Give operators complete visibility into and control over each customer's AI operations through a well-organized tabbed interface.

**Key Metrics:**

| Metric | Current Baseline | Target |
|--------|-----------------|--------|
| Messages visible per customer | 20 (flat list, no threading) | All messages, threaded by contact |
| Knowledge base items visible | 0 (no UI) | All indexed items with metadata |
| Page sections requiring scrolling past unrelated content | 6 (all on one page) | 1 (active tab only) |
| Time to audit a specific contact's conversation | ~3 min (must leave page, navigate to global conversations, filter) | <30 sec (click contact in Messages tab) |
| Stale RAG items identifiable by operator | 0% (no visibility) | 100% (expiration dates shown) |

**Non-Goals:**

- Real-time message streaming or WebSocket push updates (manual refresh only)
- Operator-to-contact messaging from the console (this is an audit/management tool, not a communication tool)
- Bulk operations across multiple customers
- Redesigning the global Conversations or Automations pages (those remain independent)
- Mobile-responsive layout (console is desktop-only for operators)

---

## 3. User Stories

### Tab Layout (Foundation)

#### US-001: Tab-based navigation
**Priority:** P0
**As an** operator, **I want** the Customer detail page organized into tabs, **so that** I can focus on one operational area at a time without scrolling through unrelated content.

**Acceptance Criteria:**
- Given I navigate to `/console/tenants/{agent_id}`, When the page loads, Then I see 6 tabs: Profile, Messages, Knowledge Base, Contacts, Listings, Automations
- Given I click a tab, When the tab activates, Then only that tab's content is visible and the previously active tab's content is hidden
- Given I am on a specific tab, When I refresh the page, Then the same tab is still active (tab state preserved via URL query parameter `?tab=messages`)
- Given I am on any tab, When I look at the page header, Then I still see the agent name, status badge, and action buttons (Edit Settings, Test SMS, Deactivate) — these are always visible above the tabs

**Edge Cases:**
- If the URL contains an invalid `?tab=` value, default to the Profile tab
- If the customer has been deactivated, all tabs still render (read-only visibility is still valuable)

---

### Profile Tab

#### US-002: Profile tab consolidates existing info
**Priority:** P0
**As an** operator, **I want** the Profile tab to contain all existing profile, configuration, and stats information, **so that** nothing is lost in the redesign.

**Acceptance Criteria:**
- Given I am on the Profile tab, When I view it, Then I see: agent profile table (name, email, phone, brokerage, market, timezone, Twilio number), configuration sections (style profile, autonomy rules, scheduling prefs, raw JSON — all collapsible), and the stats sidebar (cost this month, messages this month, errors 24h)
- Given I am on the Profile tab, When I compare it to the current page, Then all existing data is present — nothing is removed

**Edge Cases:**
- None beyond existing behavior — this is a layout migration, not a feature change

---

### Messages Tab

#### US-003: View all conversations grouped by contact
**Priority:** P0
**As an** operator, **I want** to see all conversations for this customer organized by contact, **so that** I can quickly find and audit any communication thread.

**Acceptance Criteria:**
- Given I am on the Messages tab, When it loads, Then I see a list of contacts who have conversations, each showing: contact name, phone number, channel (SMS/voice/email), total message count, last message preview (truncated to 100 chars), and timestamp of last message
- Given the contact list, When I view it, Then contacts are sorted by most recent message first (most active conversations on top)
- Given there are 50+ contacts with conversations, When the page loads, Then the first 25 are shown with a "Load more" button (server-side pagination to avoid slow page loads)

**Edge Cases:**
- Contact with no name (phone only) — display phone number as the identifier
- Conversation with a deleted contact (contact_id is NULL in conversations table) — display as "Unknown Contact" with the conversation still visible
- Contact with conversations across multiple channels — show one entry per contact (not per channel), with channel badges indicating which channels were used

#### US-004: Expand contact to view full conversation thread
**Priority:** P0
**As an** operator, **I want** to click a contact to expand and see the full conversation thread, **so that** I can audit exactly what Cal said and when.

**Acceptance Criteria:**
- Given I see a contact in the Messages tab, When I click on it, Then the contact row expands to show the full conversation thread below it (accordion-style, inline expansion)
- Given the thread is expanded, When I view messages, Then each message shows: sender badge (client=green, ai=blue with model name, system=gray), timestamp (full date + time in customer's timezone), and message body (full text, not truncated)
- Given the thread is expanded, When I view an AI-generated message, Then I see the model used (e.g., "haiku" or "sonnet") in the sender badge
- Given the thread has 100+ messages, When I expand it, Then the most recent 50 messages load first with a "Load earlier messages" link at the top (reverse-chronological pagination within thread)
- Given a contact has multiple conversations (e.g., SMS and voice), When I expand, Then all conversations are shown in a unified chronological timeline with a channel indicator per message

**Edge Cases:**
- Very long message body (1000+ chars) — display full text but apply `max-height: 300px; overflow-y: auto` to individual message containers
- Messages with delivery failures — show a red badge with the failure_reason on hover
- Messages with `sender_type` values other than 'client', 'ai', 'system' (e.g., 'agent' for manual operator messages) — display with a distinct badge color (yellow)

#### US-005: View tool execution details per message
**Priority:** P1
**As an** operator, **I want** to see what tools Cal used when generating a response, **so that** I can audit AI behavior and debug issues.

**Acceptance Criteria:**
- Given I am viewing an AI-generated message in the expanded thread, When the message has associated tool executions, Then I see a "Tools used" indicator (e.g., wrench icon + count) below the message
- Given I see a "Tools used" indicator, When I click it, Then a collapsible details section expands showing: tool name, input parameters (formatted JSON), output result (formatted JSON), status (success/error), error message if failed, and latency in milliseconds
- Given a single AI response triggered multiple tool calls, When I expand tools, Then all tool executions are listed in execution order

**Edge Cases:**
- Tool execution with very large input/output JSON (10KB+) — truncate to first 500 chars with a "Show full" toggle
- Tool execution with `status = 'error'` — highlight the entry in red with the error_message prominently displayed
- No tool executions for an AI message — do not show the "Tools used" indicator at all

#### US-006: Manual refresh for Messages tab
**Priority:** P1
**As an** operator, **I want** a refresh button on the Messages tab, **so that** I can pull the latest messages without reloading the entire page.

**Acceptance Criteria:**
- Given I am on the Messages tab, When I click the "Refresh" button, Then the contact list reloads via HTMX partial swap (no full page reload)
- Given I have a contact expanded when I click Refresh, When the refresh completes, Then expanded contacts collapse (acceptable trade-off for simplicity)
- Given the refresh is in progress, When I look at the button, Then it shows a loading spinner and is disabled to prevent double-clicks

**Edge Cases:**
- Refresh fails (server error) — show a toast/banner "Failed to refresh messages" and leave existing content intact

---

### Knowledge Base Tab

#### US-007: View all indexed RAG items
**Priority:** P0
**As an** operator, **I want** to see all documents and data indexed in this customer's RAG knowledge base, **so that** I understand what context the AI has available when responding.

**Acceptance Criteria:**
- Given I am on the Knowledge Base tab, When it loads, Then I see items grouped by source type with section headers: Conversations, Contacts, Listings, Documents (uploaded)
- Given I see a knowledge base item, When I view it, Then I see: title/description (auto-generated from content — e.g., contact name, listing address, conversation summary preview), source type badge, date indexed (created_at), date last updated (updated_at), chunk count (number of embedding chunks), and expiration date (if set)
- Given the knowledge base has items across source types, When I view the tab header area, Then I see summary counts: total items, items per source type, and total chunks

**Edge Cases:**
- Customer with zero indexed items — show an empty state: "No knowledge base items yet. Items are indexed automatically from conversations, contacts, and listings. You can also upload documents manually."
- Source item that has been deleted from the primary table (e.g., contact was deleted but embeddings remain) — show with a "Source deleted" warning badge; these are candidates for cleanup
- Items with `source_type` values not in the expected set — display under an "Other" section rather than hiding them

#### US-008: Configure expiration per item
**Priority:** P1
**As an** operator, **I want** to set expiration dates on knowledge base items, **so that** stale information is automatically managed.

**Acceptance Criteria:**
- Given I see a knowledge base item, When I click an "Edit expiration" control, Then I can set: a specific expiration date (date picker), or a relative TTL (30/60/90/180/365 days from now), or "No expiration"
- Given an item has an expiration date, When I view it, Then the expiration date is displayed; items expiring within 7 days show a yellow warning badge; expired items show a red "Expired" badge
- Given an item has expired, When the daily scanner runs, Then the system takes the configured expiration action (see US-009)

**Edge Cases:**
- Operator sets expiration date in the past — reject with validation error "Expiration date must be in the future"
- Bulk expiration: when a source type has 50+ items, setting expiration one by one is tedious — provide a "Set default TTL for [source type]" option at the section level (P2, see US-015)

#### US-009: Configure expiration behavior
**Priority:** P1
**As an** operator, **I want** to choose what happens when a knowledge base item expires — auto-remove or remind-only, **so that** I can match the customer's operational needs.

**Acceptance Criteria:**
- Given I am on the Knowledge Base tab, When I look at the tab header area, Then I see an "Expiration Policy" setting with two options: "Auto-remove expired items" and "Remind only (flag but keep)"
- Given the policy is "Auto-remove", When an item's expiration date passes, Then the daily scanner deletes the embeddings for that item from the database
- Given the policy is "Remind only", When an item's expiration date passes, Then the item is flagged as expired (visible in the UI with a red badge) but embeddings are retained
- Given the policy is changed, When I save it, Then the change applies going forward only (does not retroactively process already-expired items)

**Edge Cases:**
- Policy change from "Remind only" to "Auto-remove" when expired items already exist — show a confirmation: "X expired items exist. Auto-remove will delete them on the next daily scan. Continue?"
- Customer has no knowledge base items — expiration policy setting is still visible but inert

#### US-010: Manually add a document to the knowledge base
**Priority:** P1
**As an** operator, **I want** to upload a document or paste text to add to the knowledge base, **so that** I can supplement the AI's context with custom information.

**Acceptance Criteria:**
- Given I am on the Knowledge Base tab, When I click "Add Document", Then a modal/form appears with: title (required, text input), content (required, textarea for pasting text — file upload is P2), source type (auto-set to "document"), and optional expiration date
- Given I submit the form with valid content, When the system processes it, Then the text is chunked and embedded using the existing embedding pipeline, a new entry appears in the knowledge base list with source_type="document", and a success message is shown with the chunk count
- Given the content is very short (<50 chars), When I submit, Then it is accepted (small documents are valid — e.g., "Agent is on vacation until March 20")

**Edge Cases:**
- Content exceeding 50,000 characters — reject with error "Document too large. Maximum 50,000 characters. Split into multiple documents."
- Empty content field — reject with validation error
- Duplicate title — allow (titles are display-only, not unique keys)

#### US-011: Remove a knowledge base item
**Priority:** P1
**As an** operator, **I want** to remove a stale or incorrect item from the knowledge base, **so that** the AI does not use outdated context.

**Acceptance Criteria:**
- Given I see a knowledge base item, When I click "Remove", Then a confirmation dialog appears: "Remove [item title]? This will delete all [N] embedding chunks. The AI will no longer use this information."
- Given I confirm removal, When the system processes it, Then all embeddings rows for that source_id are deleted from the database, and the item disappears from the list

**Edge Cases:**
- Removing a conversation embedding while the conversation is still active — allow the removal, but note: "This conversation is still active. New messages may cause it to be re-indexed automatically." (Depends on whether auto-indexing is active; if not, just remove silently.)
- Removing the last item in a source type section — the section header hides

#### US-012: Re-index a knowledge base item
**Priority:** P2
**As an** operator, **I want** to force a re-index of a knowledge base item, **so that** updated source data is reflected in the embeddings.

**Acceptance Criteria:**
- Given I see a knowledge base item with source_type in (conversation, contact, listing), When I click "Re-index", Then the system re-reads the source record, re-chunks, re-embeds, and upserts the embeddings
- Given re-indexing completes, When I view the item, Then the "Last updated" timestamp reflects now, and the chunk count may have changed
- Given I click "Re-index" on a "document" type item, When I look at the button, Then it is disabled/hidden (documents have no upstream source to re-read; the operator must remove and re-add)

**Edge Cases:**
- Source record has been deleted (e.g., contact was removed) — show error "Source record no longer exists. Consider removing this knowledge base entry."
- Re-indexing while Voyage API is down — show error "Embedding service unavailable. Try again later." and leave existing embeddings intact
- Re-index on an item that hasn't changed — the upsert is idempotent; no harm, just updates `updated_at`

---

### Contacts Tab

#### US-013: Contacts as a full tab
**Priority:** P0
**As an** operator, **I want** the contacts list to be a full-width tab, **so that** I can see all contact details without sidebar truncation.

**Acceptance Criteria:**
- Given I am on the Contacts tab, When it loads, Then I see a table with columns: Name, Phone, Email, Role, Stage, Consent Status, Last Contact, Silent Mode, Interaction Count
- Given there are 50+ contacts, When the page loads, Then all contacts are shown (the existing query already fetches all; table is scrollable)
- Given I view a contact row, When I look at consent status, Then "revoked" shows in red, "granted" in green, "pending" in yellow

**Edge Cases:**
- Customer with zero contacts — show empty state: "No contacts yet."

---

### Listings Tab

#### US-014: Listings as a full tab
**Priority:** P0
**As an** operator, **I want** the listings to be a full-width tab, **so that** I can see all listing details.

**Acceptance Criteria:**
- Given I am on the Listings tab, When it loads, Then I see a table with columns: Address, Price (formatted with commas), Status, Beds, Baths, Sqft, List Date
- Given there are listings, When I view them, Then active listings appear first, followed by other statuses
- Given I view a listing's status, When status is "active", Then the badge is green; otherwise gray

**Edge Cases:**
- Customer with zero listings — show empty state: "No listings yet."

---

### Automations Tab

#### US-015: Automations (Pending Triggers) as a full tab
**Priority:** P0
**As an** operator, **I want** the pending triggers displayed as a full tab called "Automations", **so that** I have a clear view of all scheduled actions.

**Acceptance Criteria:**
- Given I am on the Automations tab, When it loads, Then I see a table with columns: Trigger Type, Scheduled At (in customer timezone), Action Type, Entity Type, Status, Created At
- Given a trigger is pending, When I view it, Then the status badge is blue
- Given I view the tab, When there are also completed/cancelled triggers, Then I see a filter toggle: "Pending only" (default) / "All"

**Edge Cases:**
- Customer with zero triggers — show empty state: "No scheduled automations."
- Trigger scheduled in the past but still pending (stale) — show with a yellow "Overdue" warning badge

---

### Future / P2

#### US-016: Default TTL per source type
**Priority:** P2
**As an** operator, **I want** to set a default TTL for all items of a given source type, **so that** I do not have to set expiration on each item individually.

**Acceptance Criteria:**
- Given I am on the Knowledge Base tab, When I click "Set default TTL" on a source type section header, Then I can set a default TTL (30/60/90/180/365 days or "No default")
- Given a default TTL is set, When a new item of that source type is indexed, Then the expiration date is automatically set to `indexed_date + TTL`

#### US-017: File upload for knowledge base documents
**Priority:** P2
**As an** operator, **I want** to upload a PDF or text file to the knowledge base, **so that** I can index documents without copy-pasting.

**Acceptance Criteria:**
- Given I click "Add Document", When I see the form, Then there is a file upload option (accepts .txt, .pdf, .md; max 5MB)
- Given I upload a file, When the system processes it, Then text is extracted, chunked, and embedded

---

## 4. Technical Requirements

### 4.1 Data Model Changes

#### New columns on `embeddings` table:

```sql
ALTER TABLE embeddings ADD COLUMN title TEXT;
ALTER TABLE embeddings ADD COLUMN expires_at TIMESTAMPTZ;
```

- `title`: Human-readable label for UI display. Auto-generated during indexing (e.g., contact name, listing address, first 80 chars of document). NULL for legacy rows (UI falls back to source_type + source_id).
- `expires_at`: When this embedding set should expire. NULL means no expiration. Applies at the source_id level — all chunks for a source_id share the same expiration.

#### New column on `agents` table:

```sql
ALTER TABLE agents ADD COLUMN kb_expiration_policy TEXT DEFAULT 'remind_only';
ALTER TABLE agents ADD COLUMN kb_default_ttl_days JSONB DEFAULT '{}';
```

- `kb_expiration_policy`: Either `'auto_remove'` or `'remind_only'`. Controls what happens when embeddings expire.
- `kb_default_ttl_days`: JSON object mapping source_type to default TTL in days. E.g., `{"conversation": 90, "contact": null, "listing": 180}`. NULL values mean no default.

#### New source_type value:

- `'document'` — for operator-uploaded text documents. These have no `source_id` pointing to another table; the `source_id` is a newly generated UUID unique to the document.

### 4.2 New API Endpoints

All endpoints require console auth. All are scoped to a specific agent_id.

| Method | Path | Description | Request | Response |
|--------|------|-------------|---------|----------|
| GET | `/console/tenants/{agent_id}/messages` | HTMX partial: contact list with conversation summaries | Query: `?page=1&per_page=25` | HTML partial |
| GET | `/console/tenants/{agent_id}/messages/{contact_id}` | HTMX partial: expanded conversation thread for a contact | Query: `?before={message_id}` for pagination | HTML partial |
| GET | `/console/tenants/{agent_id}/knowledge-base` | HTMX partial: knowledge base items grouped by source type | — | HTML partial |
| POST | `/console/tenants/{agent_id}/knowledge-base/add` | Add a document to the knowledge base | Form: title, content, expires_at (optional) | Redirect or HTMX swap |
| POST | `/console/tenants/{agent_id}/knowledge-base/{source_id}/remove` | Remove all embeddings for a source_id | CSRF token | Redirect or HTMX swap |
| POST | `/console/tenants/{agent_id}/knowledge-base/{source_id}/reindex` | Force re-index of a source item | CSRF token | Redirect or HTMX swap |
| POST | `/console/tenants/{agent_id}/knowledge-base/{source_id}/expire` | Set expiration date for a source item | Form: expires_at | Redirect or HTMX swap |
| POST | `/console/tenants/{agent_id}/knowledge-base/policy` | Update expiration policy | Form: policy (auto_remove/remind_only) | Redirect or HTMX swap |

### 4.3 New Database Queries

#### Messages Tab Queries

**Contact list with conversation stats:**
```sql
SELECT c.id, c.name, c.phone,
       cv.channel,
       COUNT(m.id) as message_count,
       MAX(m.created_at) as last_message_at,
       (SELECT body FROM messages WHERE conversation_id = cv.id ORDER BY created_at DESC LIMIT 1) as last_message_preview
FROM contacts c
JOIN conversations cv ON cv.contact_id = c.id AND cv.agent_id = %s
JOIN messages m ON m.conversation_id = cv.id
WHERE c.agent_id = %s
GROUP BY c.id, c.name, c.phone, cv.channel, cv.id
ORDER BY last_message_at DESC
LIMIT %s OFFSET %s;
```

Note: This query will need optimization. Consider a materialized/denormalized approach if it becomes slow — the `conversations.last_message_at` column already exists and can serve as the sort key.

**Full thread for a contact (with tool executions):**
```sql
-- Messages
SELECT m.id, m.sender_type, m.body, m.created_at, m.model_used,
       m.delivery_status, m.failure_reason, m.intent, m.tokens_used,
       cv.channel
FROM messages m
JOIN conversations cv ON m.conversation_id = cv.id
WHERE cv.agent_id = %s AND cv.contact_id = %s
ORDER BY m.created_at DESC
LIMIT 50 OFFSET %s;

-- Tool executions (joined after, keyed by conversation_id + time proximity)
SELECT te.* FROM tool_executions te
JOIN conversations cv ON te.conversation_id = cv.id
WHERE cv.agent_id = %s AND cv.contact_id = %s
ORDER BY te.created_at;
```

#### Knowledge Base Queries

**All indexed items grouped by source type:**
```sql
SELECT source_type, source_id, title,
       MIN(created_at) as indexed_at,
       MAX(updated_at) as last_updated,
       COUNT(*) as chunk_count,
       MAX(expires_at) as expires_at
FROM embeddings
WHERE agent_id = %s
GROUP BY source_type, source_id, title
ORDER BY source_type, last_updated DESC;
```

**Delete all embeddings for a source:**
```sql
DELETE FROM embeddings WHERE agent_id = %s AND source_id = %s;
```

**Set expiration for a source:**
```sql
UPDATE embeddings SET expires_at = %s WHERE agent_id = %s AND source_id = %s;
```

**Expired items (for daily scanner):**
```sql
SELECT DISTINCT source_id, source_type, agent_id, title
FROM embeddings
WHERE expires_at IS NOT NULL AND expires_at < now();
```

### 4.4 Daily Scanner Addition

The existing `daily_scanner.py` must be extended with a knowledge base expiration check:

1. Query all expired embeddings across all agents
2. For each agent, check `kb_expiration_policy`:
   - If `'auto_remove'`: DELETE the expired embeddings
   - If `'remind_only'`: Log a warning (future: generate an alert/notification)
3. Log all actions for audit trail

### 4.5 Embedding Pipeline Extension

The existing `RAGService._upsert_chunks()` must be updated to:
- Accept and store a `title` parameter
- Accept and store an `expires_at` parameter (optional)
- Check `kb_default_ttl_days` on the agent record when no explicit `expires_at` is provided

A new method is needed:
- `RAGService.index_document(agent_id, title, content, expires_at=None) -> int` — for operator-uploaded documents

### 4.6 Performance Requirements

| Operation | Target | Notes |
|-----------|--------|-------|
| Messages tab initial load (contact list) | <1s | Paginated, 25 contacts per page |
| Conversation thread expansion | <800ms | 50 messages per page, HTMX partial |
| Knowledge base tab load | <1s | Aggregate query on embeddings table, indexed on agent_id+source_type |
| Document indexing (add) | <5s | Voyage API call is the bottleneck; show spinner |
| Re-index single item | <5s | Same as above |
| Item removal | <200ms | Simple DELETE query |

### 4.7 Security Requirements

- All new endpoints require existing console session auth (same as current pattern)
- All POST endpoints require CSRF token validation (same as current pattern)
- All queries are scoped to `agent_id` — no cross-tenant data leakage
- Document upload content is sanitized (strip HTML/script tags before indexing)
- File upload (P2) must validate file type and enforce size limit server-side

---

## 5. Scope & Constraints

### In Scope

- Tab-based layout for Customer detail page (6 tabs)
- Messages tab: contact-grouped conversations with expandable threads, tool call inspection, pagination, manual refresh
- Knowledge Base tab: view indexed items, set expiration, configure expiration policy, add documents (text paste), remove items, re-index items
- Contacts tab: existing data moved to full-width tab with table layout
- Listings tab: existing data moved to full-width tab with table layout
- Automations tab: existing pending triggers moved to full-width tab with filter
- Profile tab: existing profile + config + stats consolidated
- Schema migration: new columns on embeddings and agents tables
- Daily scanner extension for expiration processing
- RAGService extension for document indexing and title/expiration support

### Out of Scope

- Real-time updates / WebSocket / SSE push (manual refresh only)
- Operator sending messages to contacts from the console
- File upload for documents (P2 — text paste only in v1)
- Bulk operations (bulk remove, bulk set expiration)
- Global search across all customers' knowledge bases
- RAG quality metrics (relevance scoring, retrieval analytics)
- Editing the content of an existing knowledge base document (remove + re-add)
- Changes to the global Conversations, Triggers, or other console pages
- Mobile/responsive layout

### Technical Constraints

- **HTMX-first**: All tab switching and partial updates use HTMX, consistent with the existing console architecture. No client-side JavaScript framework.
- **Jinja2 templates**: All rendering is server-side via Jinja2.
- **Existing embedding model**: Voyage AI `voyage-3-lite` (512 dims). No model changes.
- **Existing chunking strategy**: `chunk_text()` with configurable chunk_size and overlap. No changes to chunking logic.
- **PostgreSQL + pgvector**: All queries must work with the existing database. No new tables — only ALTER TABLE for new columns.

### Business Constraints

- No new third-party service dependencies
- Voyage API costs for re-indexing and new document indexing are charged to the customer's usage metrics (track in `usage_metrics.llm_cost_cents`)

---

## 6. User Flows

### Flow 1: Operator audits a conversation

1. Operator navigates to `/console/tenants/{agent_id}?tab=messages`
2. Sees list of contacts sorted by most recent message
3. Spots the contact they are investigating
4. Clicks the contact row — it expands showing the conversation thread
5. Scrolls through messages, sees an AI response they want to inspect
6. Clicks "Tools used (3)" under the AI message
7. Tool execution details expand: sees Cal used `search_listings`, `check_availability`, `send_sms`
8. Reviews input/output of each tool call
9. Clicks "Load earlier messages" to see the conversation beginning
10. Closes the expansion by clicking the contact row again

### Flow 2: Operator manages knowledge base

1. Operator navigates to `/console/tenants/{agent_id}?tab=knowledge-base`
2. Sees 4 sections: Conversations (12 items), Contacts (8), Listings (5), Documents (0)
3. Notices a conversation item from 6 months ago — clicks "Edit expiration"
4. Sets expiration to "30 days from now"
5. Scrolls to the top, changes Expiration Policy from "Remind only" to "Auto-remove"
6. Confirms the change
7. Clicks "Add Document"
8. Enters title: "Agent vacation schedule Q2 2026"
9. Pastes text content with the vacation dates
10. Sets expiration: June 30, 2026
11. Submits — sees the new document appear under the Documents section with chunk count

### Flow 3: Operator reviews customer profile

1. Operator navigates to `/console/tenants/{agent_id}` (defaults to Profile tab)
2. Reviews agent info, expands Style Profile to check tone settings
3. Clicks the Messages tab to spot-check recent activity
4. Clicks the Automations tab to verify a scheduled follow-up is pending
5. Returns to Profile tab, clicks "Edit Settings" to adjust autonomy rules

---

## 7. Open Questions

| # | Question | Owner | Deadline |
|---|----------|-------|----------|
| 1 | Should tool executions be correlated to specific messages by timestamp proximity, or do we need a `message_id` FK on `tool_executions`? The current schema has `conversation_id` but not `message_id`. Timestamp correlation may be imprecise for rapid multi-turn exchanges. | @eng | Before implementation of US-005 |
| 2 | Should the daily scanner's expiration processing generate a notification to the operator (email, console alert), or is the UI badge sufficient for "remind only" mode? | @pm (self) | Before implementation of US-009 |
| 3 | When re-indexing a conversation, should we include only new messages since last index, or re-index the full conversation? The current `index_conversation()` re-indexes everything (idempotent upsert). For long conversations, this could be expensive. | @eng | Before implementation of US-012 |
| 4 | Are there existing conversations with NULL contact_id in production? If so, how many? This affects the Messages tab query design. | @eng | Before implementation of US-003 |
| 5 | Should the Automations tab include completed/cancelled triggers or only pending? The current sidebar shows only pending. Including history adds value but requires a new query with potentially large result sets. | @pm (self) | Before implementation of US-015 |

---

## 8. Release Criteria

### Must be true before this ships:

1. **All P0 user stories pass acceptance criteria** — verified by manual QA walkthrough
2. **Tab navigation works** — all 6 tabs render, URL state is preserved, no broken links
3. **No data regression** — every piece of information visible on the current tenant_detail page is still visible on the redesigned page (Profile tab contains all existing data)
4. **Messages tab loads within performance targets** — <1s for contact list, <800ms for thread expansion, tested with a customer having 100+ contacts and 10,000+ messages
5. **Knowledge base tab accurately reflects database state** — chunk counts match actual embeddings table, source types are correct, expiration dates display in customer timezone
6. **Document addition works end-to-end** — text is chunked, embedded, stored, and appears in knowledge base tab
7. **Item removal deletes all chunks** — verified by checking embeddings table post-removal
8. **Expiration policy is persisted and respected** — daily scanner processes expired items correctly for both auto_remove and remind_only modes
9. **CSRF protection on all POST endpoints** — no regression from existing security
10. **All existing tests pass** — no regressions in the 26 test files
11. **New tests written** for: tab routing, messages pagination, knowledge base CRUD operations, expiration processing, document indexing
12. **Schema migration is reversible** — new columns use ADD COLUMN with defaults; no destructive changes

### Rollback plan:
- New columns are additive (not breaking). If the feature is rolled back, the old template can be restored and new columns are inert. No data migration reversal needed.

---

## Backlog Summary

| ID | Story | Priority | Effort | Dependencies | Status |
|----|-------|----------|--------|--------------|--------|
| US-001 | Tab-based navigation | P0 | M | None | Ready |
| US-002 | Profile tab (existing data) | P0 | S | US-001 | Ready |
| US-003 | Messages: contact list | P0 | L | US-001 | Ready |
| US-004 | Messages: expanded thread | P0 | L | US-003 | Blocked |
| US-005 | Messages: tool execution details | P1 | M | US-004 | Blocked |
| US-006 | Messages: manual refresh | P1 | S | US-003 | Blocked |
| US-007 | KB: view indexed items | P0 | L | US-001, schema migration | Ready |
| US-008 | KB: configure expiration per item | P1 | M | US-007 | Blocked |
| US-009 | KB: configure expiration behavior | P1 | M | US-007, scanner extension | Blocked |
| US-010 | KB: add document | P1 | M | US-007, RAGService extension | Blocked |
| US-011 | KB: remove item | P1 | S | US-007 | Blocked |
| US-012 | KB: re-index item | P2 | M | US-007 | Blocked |
| US-013 | Contacts as full tab | P0 | S | US-001 | Ready |
| US-014 | Listings as full tab | P0 | S | US-001 | Ready |
| US-015 | Automations as full tab | P0 | S | US-001 | Ready |
| US-016 | KB: default TTL per source type | P2 | M | US-008 | Blocked |
| US-017 | KB: file upload | P2 | L | US-010 | Blocked |

**Estimated total effort:** ~6-8 engineering days for P0+P1, ~3-4 additional days for P2.
