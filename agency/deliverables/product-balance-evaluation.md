# Product Feature Balance Evaluation
## Date: 2026-03-11
## Authors: Oracle (Research) & Lyra (Product Design)

---

## Executive Summary

Calloway is **closer to v1 readiness than most products at this stage**, but it is not yet ready for unsupervised production use. The core AI message pipeline is genuinely strong — inbound SMS, voice, and email all flow through a well-structured normalize-classify-route-dispatch architecture. Contact management, scheduling, and automation form a coherent backbone. However, several critical gaps would block a solo agent from using this as their *primary* tool: the agent portal is read-only (no ability to take actions from the UI), Firebase push notifications are stubbed out, there is no onboarding flow for agents themselves, and the voice/Vapi integration is partially implemented. The product has more depth than breadth — the AI pipeline is sophisticated, but the human-facing surfaces that agents interact with daily are thin.

**Verdict: 70% ready for a controlled beta with 5-10 agents. Not ready for general availability.**

---

## Feature Inventory

### Communication Layer
| Feature | Status | Files |
|---------|--------|-------|
| Inbound SMS via Twilio | Built, production-ready | `app/api/webhooks.py`, `app/services/twilio_service.py` |
| Outbound SMS via Twilio | Built, with segment tracking | `app/services/twilio_service.py` |
| SMS delivery status tracking | Built (delivered, failed, read) | `app/api/webhooks.py` lines 182-248 |
| RCS with SMS fallback | Partially built (sends as SMS) | `app/services/twilio_service.py` |
| Inbound voice via Twilio | Built, forwards to agent then Vapi | `app/api/webhooks.py` lines 251-297 |
| Vapi post-call transcript processing | Built, processes through pipeline | `app/api/webhooks.py` lines 299-418 |
| Voice cost tracking (minutes + cost) | Built | `app/api/webhooks.py` lines 370-401 |
| Voice daily cap enforcement | Built with push notification | `app/api/webhooks.py` lines 384-401 |
| Inbound email via SendGrid | Built | `app/api/webhooks.py` lines 421-525 |
| Outbound email via SendGrid | Built | `app/services/email_service.py` |
| Email archiving to `emails` table | Built | `app/api/webhooks.py` lines 484-494 |
| Push notifications (Firebase) | **Stubbed** — logs only, no actual Firebase send | `app/services/firebase_service.py` lines 61-68 |

### Contact Management
| Feature | Status | Files |
|---------|--------|-------|
| Contact CRUD | Built | `app/tools/contacts.py` |
| Fuzzy name lookup | Built | `app/tools/contacts.py` lines 24-50 |
| Lifecycle stage tracking | Built (new_lead → active → under_contract → closed) | Schema `contacts.lifecycle_stage` |
| Lead preferences (areas, budget, beds, etc.) | Built with separate table | `lead_preferences` table, `app/tools/contacts.py` |
| TCPA consent tracking | Built with audit log | `contacts.consent_*` fields, `consent_log` table |
| Silent mode (agent handoff) | Built | `contacts.silent_mode`, `app/pipeline/commands/status.py` |
| Contact gap analysis | Built with lifecycle-specific thresholds | `app/tools/contacts.py` lines 213-269 |
| Lead source tracking | Built | `contacts.lead_source` |
| Language detection | Schema exists, implementation unclear | `contacts.language_detected` |
| Interaction counting | Built | `contacts.interaction_count` |

### Lead Management
| Feature | Status | Files |
|---------|--------|-------|
| Lead scoring (rule-based) | Built, batch-optimized | `app/tools/lead_scoring.py` |
| Score tiers (hot/warm/cool/cold) | Built | `app/tools/lead_scoring.py` lines 255-264 |
| Scoring factors: recency, engagement, stage, showings, consent, preferences | All built | `app/tools/lead_scoring.py` SCORING_RULES |
| Drip campaigns (3 default templates) | Built | `app/tools/drip_campaigns.py` |
| Drip enrollment + trigger scheduling | Built | `app/tools/drip_campaigns.py` lines 86-141 |
| Drip unenrollment | Built | `app/tools/drip_campaigns.py` lines 177-187 |
| Auto-create contact from email/voice | Built | `app/api/webhooks.py` |

### Scheduling
| Feature | Status | Files |
|---------|--------|-------|
| Showing hold (30-min expiry) | Built | `app/tools/showings.py` |
| Showing confirmation + Google Calendar event | Built | `app/tools/showings.py` lines 45-126 |
| Showing cancellation | Built | `app/tools/showings.py` lines 129-137 |
| Stale hold expiry (background worker) | Built | `app/tools/showings.py` lines 140-155 |
| Calendar availability check | Built | `app/tools/calendar_tools.py` |
| Calendar event creation | Built | `app/tools/calendar_tools.py` |
| Agent status management (in_showing, vacation, etc.) | Built with auto-revert | `app/pipeline/commands/status.py` |
| Occupied home showing coordination | Built | `app/tools/seller_tools.py` lines 74-109 |

### Listing Management
| Feature | Status | Files |
|---------|--------|-------|
| Natural language listing ingestion (AI parse) | Built | `app/tools/listings.py` lines 31-82 |
| Listing update (price change, etc.) | Built | `app/tools/listings.py` lines 85-123 |
| Listing search (filters) | Built | `app/tools/listings.py` lines 159-209 |
| Freshness warning (>7 days stale) | Built | `app/tools/listings.py` lines 151-154 |
| Listing broadcast to matching buyers | Built | `app/pipeline/commands/listing.py` lines 76-117 |
| DOM (Days on Market) tracking and alerts | Built with 5 thresholds | `app/tools/seller_tools.py` lines 178-218 |
| Listing activity tracking (showings, inquiries, feedback) | Built | `app/tools/seller_tools.py` lines 116-171 |
| Open house scheduling + trigger cascade | Built | `app/tools/seller_tools.py` lines 224-282 |
| Open house attendee tracking | Built | `app/tools/seller_tools.py` lines 285-305 |

### Transaction Management
| Feature | Status | Files |
|---------|--------|-------|
| Transaction CRUD (offer-to-close) | Built | `app/tools/transactions.py` |
| Transaction statuses (pending_offer → closed/fell_through) | Built, 6 statuses | `app/tools/transactions.py` VALID_STATUSES |
| Auto-sync contact lifecycle on status change | Built | `app/tools/transactions.py` lines 131-152 |
| Transaction deadline tracking (inspection, appraisal, financing, closing) | Schema built, cascade triggers built | Schema + `app/tools/triggers.py` lines 100-137 |
| Commission tracking | Schema built (`commission_pct`) | Schema `transactions` table |
| Offer preparation workflow | Built (requests docs from client) | `app/pipeline/commands/offer.py` |

### Automation (Triggers & Drips)
| Feature | Status | Files |
|---------|--------|-------|
| Trigger creation with deduplication | Built | `app/tools/triggers.py` lines 12-53 |
| Trigger worker (60s poll loop) | Built | `app/worker/trigger_worker.py` |
| Trigger firing: notify_agent, send_message, both, compile_report | Built | `app/worker/trigger_worker.py` lines 61-88 |
| Recurring triggers (daily, weekly, monthly, annually) | Built | `app/worker/trigger_worker.py` lines 181-210 |
| Trigger cascades: transaction_deadlines, open_house, post_close | Built | `app/tools/triggers.py` lines 90-218 |
| Daily scanner: gap analysis, DOM alerts, proactive follow-ups | Built | `app/worker/daily_scanner.py` |
| Morning briefing compilation and push | Built (push is stubbed) | `app/worker/daily_scanner.py` lines 60-204 |
| Seller weekly activity report | Built | `app/worker/daily_scanner.py` lines 206-292 |
| Usage metrics tracking (triggers_fired counter) | Built | `app/worker/trigger_worker.py` lines 213-226 |

### Intelligence (AI/RAG/Scoring)
| Feature | Status | Files |
|---------|--------|-------|
| Intent classification (Haiku) | Built | `app/pipeline/classifier.py` (referenced) |
| AI message composition (Sonnet) | Built | `app/pipeline/commands/contact.py` |
| Model tiering (Haiku/Sonnet) | Built | `app/services/anthropic_service.py` |
| RAG embedding (Voyage AI, 512 dims) | Built | `app/services/embedding_service.py` |
| RAG indexing (conversations, contacts, listings) | Built | `app/services/rag_service.py`, `app/worker/rag_indexer.py` |
| RAG search (cosine similarity via pgvector HNSW) | Built | `app/services/rag_service.py` lines 257-332 |
| RAG context injection into LLM prompts | Built | `app/services/rag_service.py` lines 334-386 |
| Token/cost tracking per agent per day | Built | `usage_metrics` table |

### Agent Experience (Portal)
| Feature | Status | Files |
|---------|--------|-------|
| Phone-based login with SMS code | Built | `app/api/agent_portal.py` lines 121-194 |
| Dashboard (stats, approvals, upcoming, conversations, listings) | Built | `app/api/agent_portal.py` lines 206-295 |
| Contact list with search + role/source filters | Built (read-only) | `app/api/agent_portal.py` lines 300-348 |
| Conversation list + detail view | Built (read-only) | `app/api/agent_portal.py` lines 353-426 |
| Schedule view (today + upcoming showings) | Built (read-only) | `app/api/agent_portal.py` lines 431-471 |
| Trigger/reminder list | Built (read-only) | `app/api/agent_portal.py` lines 476-508 |
| Transaction list | Built (read-only) | `app/api/agent_portal.py` lines 513-546 |
| Lead scores view | Built (read-only) | `app/api/agent_portal.py` lines 551-567 |
| Drip campaigns view | Built (read-only) | `app/api/agent_portal.py` lines 572-590 |
| **Agent cannot take any action from the portal** | **Gap** | No POST routes for approve/send/edit |

### Operator Console
| Feature | Status | Files |
|---------|--------|-------|
| Password-based auth with CSRF | Built | `app/api/console.py`, `app/api/console_auth.py` |
| System dashboard (pulse, activity, attention) | Built | `app/api/console.py` lines 80-95 |
| Tenant CRUD (list, detail, edit, deactivate) | Built | `app/api/console.py` lines 156-307 |
| Onboarding wizard | Built | `app/api/console.py` lines 115-149 |
| Conversation browser (with agent/channel filters) | Built | `app/api/console.py` lines 313-350 |
| Trigger management (queue, retry, cancel, fire-now) | Built | `app/api/console.py` lines 358-424 |
| Error log viewer | Built | `app/api/console.py` lines 431-445 |
| Cost dashboard (30-day summary, per-agent, model tiers) | Built | `app/api/console.py` lines 452-465 |
| Health overview + manual scan | Built | `app/api/console.py` lines 472-510 |
| Billing management (plan changes, cancellation) | Built | `app/api/console.py` lines 517-575 |
| User manual | Built | `app/api/console.py` lines 582-590 |
| Test SMS from console | Built | `app/api/console.py` lines 290-306 |
| HTMX partials (activity feed, health dot) | Built | `app/api/console.py` |

### Billing & Monetization
| Feature | Status | Files |
|---------|--------|-------|
| Stripe customer + subscription creation | Built | `app/services/billing_service.py` |
| 3 plan tiers (Starter $49, Pro $99, Enterprise $199) | Built | `app/services/billing_service.py` PLAN_TIERS |
| 14-day trial | Built | `app/services/billing_service.py` |
| Plan changes with proration | Built | `app/services/billing_service.py` lines 167-213 |
| Subscription cancellation (at period end or immediate) | Built | `app/services/billing_service.py` lines 216-252 |
| Webhook handlers (subscription.updated, invoice.paid, payment_failed) | Built | `app/services/billing_service.py` lines 257-347 |
| Message quota enforcement | Built | `app/services/billing_service.py` lines 361-395 |
| Invoice tracking | Built | `app/services/billing_service.py` lines 288-322 |
| Usage-based cost tracking (LLM, SMS, voice) | Built | `usage_metrics` table |

### Infrastructure & Reliability
| Feature | Status | Files |
|---------|--------|-------|
| PostgreSQL with RLS (15 tables, all with agent isolation) | Built | `app/db/schema.sql` |
| Redis caching + session/login code storage | Built with in-memory fallback | `app/services/redis_pool.py`, `app/api/agent_portal.py` |
| Twilio signature validation | Built | `app/api/webhooks.py` lines 13-19 |
| Vapi webhook secret validation | Built | `app/api/webhooks.py` lines 302-309 |
| CSRF protection on all POST routes | Built | Console and agent portal |
| Error logging table | Built | `error_log` table |
| Harness traces for testing | Built | `harness_traces` table |
| Rate limiting (referenced) | Built | `app/pipeline/rate_limiter.py` (referenced in webhooks) |
| Retry logic for embedding API | Built | `app/services/embedding_service.py` |

---

## System Balance Scorecard

| Category | Completeness | Quality | Integration | Score |
|----------|-------------|---------|-------------|-------|
| Communication (SMS/Voice/Email) | All 3 channels built, delivery tracking | Clean pipeline architecture | All feed through unified normalize-classify-route | **8/10** |
| Contact Management | Full CRUD, lifecycle, consent, preferences | Gap analysis is production-quality | Feeds into scoring, triggers, drips, RAG | **9/10** |
| Lead Management | Scoring + drips + auto-creation | Batch-optimized scoring, good templates | Scoring considers showings, consent, prefs | **7/10** |
| Scheduling | Hold/confirm/cancel, calendar, occupied homes | Clean hold-with-expiry pattern | Ties to listings, contacts, calendar, metrics | **8/10** |
| Transaction Management | Full lifecycle, deadline cascades | Auto-syncs contact stage | Links contacts, listings, triggers | **7/10** |
| Automation (Triggers/Drips) | Worker + daily scanner + cascades + recurrence | Deduplication, metric tracking | Deeply wired into contacts, listings, transactions | **9/10** |
| Intelligence (AI/RAG/Scoring) | Classification, composition, RAG, scoring | Voyage AI + pgvector HNSW is solid | RAG indexes conversations, contacts, listings | **7/10** |
| Agent Experience (Portal) | 9 screens, all read-only | Clean mobile-first templates | Shows data but cannot act on it | **4/10** |
| Operator Experience (Console) | 17 templates, full CRUD + actions | HTMX partials, filters, search | Deep integration with all backend services | **8/10** |
| Billing & Monetization | Stripe lifecycle fully built | Quota enforcement, proration, webhooks | Tracks usage against plan limits | **8/10** |
| Infrastructure & Reliability | RLS, CSRF, signature validation, Redis | Error logging, retry logic | Background workers + webhook processing | **8/10** |

**Overall Score: 7.5/10** — Strong backend, weak agent-facing surface.

---

## Feature Interconnection Map

The features connect in a genuinely coherent data model. This is one of Calloway's strengths.

### Strong Interconnections (verified in code)

1. **Contact lifecycle ↔ Transaction status**: When a transaction moves to `under_contract`, the contact is auto-updated (`_sync_contact_lifecycle` in `app/tools/transactions.py`). When it `closes`, the contact becomes `past_client`. When it falls through, they revert to `active_buyer`.

2. **Drip campaigns → Triggers → Trigger worker → Outbound messages**: Enrolling a contact in a drip creates scheduled triggers for each step (`app/tools/drip_campaigns.py` lines 119-137). The trigger worker fires them on schedule (`app/worker/trigger_worker.py`). This is a clean chain.

3. **Daily scanner → Gap analysis → Triggers**: The morning scan runs `analyze_contact_gaps()` and auto-creates follow-up triggers (`app/worker/daily_scanner.py` lines 35-38).

4. **Daily scanner → DOM alerts → Triggers**: Listings are checked against DOM thresholds; alerts become triggers (`app/worker/daily_scanner.py` lines 41-43).

5. **Listing broadcast → Contact search**: Broadcasting a listing queries `active_buyer` contacts and queues messages (`app/pipeline/commands/listing.py` lines 76-117).

6. **Lead scoring → Showing data + Contact data + Preference data**: Score calculation pulls from showings, contacts, and lead_preferences tables with batch queries (`app/tools/lead_scoring.py`).

7. **Showing confirmation → Usage metrics + Google Calendar**: Confirming a showing creates a calendar event AND increments `showings_booked` in `usage_metrics` (`app/tools/showings.py` lines 109-118).

8. **RAG indexer → Conversations + Contacts + Listings**: All three entity types are embedded and searchable via cosine similarity (`app/services/rag_service.py`, `app/worker/rag_indexer.py`).

9. **Transaction deadlines → Trigger cascade**: Creating a transaction can generate a cascade of 4 triggers per deadline (3-day, 1-day, day-of, day-after) via `create_trigger_cascade` (`app/tools/triggers.py` lines 100-137).

10. **Open house → Trigger cascade → Buyer notification + Seller report**: Scheduling an open house creates 5 cascaded triggers and identifies matching buyers (`app/tools/seller_tools.py` lines 224-282).

### Weak or Missing Interconnections

1. **Lead scoring does NOT feed into drip enrollment**: Scoring contacts as "hot" or "cold" does not auto-enroll them in appropriate campaigns. This is a manual gap.

2. **RAG context is NOT confirmed to be injected into every LLM call**: The `get_context_for_message` method exists but its integration into the main pipeline handler would need verification in `handlers.py`.

3. **Billing quota does NOT gate voice calls**: `check_message_quota` only counts messages, not voice minutes against plan limits. The voice daily cap is separate and agent-specific, not plan-based.

4. **Agent portal has NO write path to any backend feature**: The portal is entirely GET routes. Agents cannot approve triggers, send messages, enroll in campaigns, or update contacts from the UI.

---

## Critical Gaps

### 1. Agent Portal is Read-Only (Severity: BLOCKING)
The agent portal (`app/api/agent_portal.py`) has 10 GET routes and zero POST routes (except login). A solo agent cannot:
- Approve or reject pending triggers
- Send a message to a contact
- Create or edit a contact
- Enroll a contact in a drip campaign
- Update a showing status
- Create a transaction
- Respond to a conversation

The ONLY way to interact with Calloway is via SMS commands to the AI pipeline. This is fine for some use cases but insufficient as a primary business tool. Agents need a "quick action" capability in the portal.

### 2. Firebase Push Notifications Are Stubbed (Severity: HIGH)
`app/services/firebase_service.py` line 57-68 explicitly says `# TODO: Implement actual Firebase sending`. The entire notification tier system (urgent, action_needed, informational, briefing) exists in code but messages are only logged, never delivered. This means:
- Morning briefings never reach agents
- Trigger approvals are invisible
- Delivery failures go unnoticed
- Voice call summaries are lost

### 3. No Agent Self-Onboarding (Severity: HIGH)
The console has an onboarding wizard (`/console/onboard`), but this is operator-initiated. There is no self-service signup flow for agents. For v1 launch with paying customers, agents need to be able to:
- Sign up with their phone/email
- Connect their Twilio number
- Set their preferences/style
- Start a trial

### 4. No Contact Detail View in Agent Portal (Severity: MEDIUM)
The agent portal shows a contact list but has no detail view. An agent cannot see a contact's preferences, lead score, notes, linked listing, or conversation history from the contact list. This forces them to context-switch to SMS commands.

### 5. No Reporting / Analytics for Agents (Severity: MEDIUM)
The operator console has costs, health, and billing dashboards. The agent portal has none. A solo agent using Calloway cannot see:
- How many leads they converted this month
- Their showing-to-offer ratio
- Message response times
- Commission pipeline totals
- Monthly costs/usage

### 6. No Document/File Handling (Severity: MEDIUM)
Real estate transactions involve contracts, disclosures, pre-approval letters, inspection reports, etc. Calloway has no document upload, storage, or reference capability. The offer command in `app/pipeline/commands/offer.py` requests documents from clients but has nowhere to store them.

### 7. No MLS/IDX Integration (Severity: MEDIUM for v2, acceptable for v1)
Listings are manually created via natural language parsing. There is no integration with MLS data feeds, which means agents must manually enter every listing and keep them updated.

---

## Strength Areas

### 1. AI Pipeline Architecture
The normalize → classify → route → handle → dispatch pipeline is genuinely well-designed. It handles three channels (SMS, voice, email) through a single unified flow. The command decomposition into `app/pipeline/commands/` is clean and maintainable. TCPA compliance, rate limiting, and consent gating are properly positioned in the pipeline before message processing.

### 2. Trigger & Automation System
The trigger system is the product's deepest feature. It supports:
- Single triggers with deduplication
- Cascades (transaction deadlines, open house, post-close)
- Recurring triggers (daily/weekly/monthly/annually)
- Multiple action types (notify, send, both, compile_report)
- Autonomy levels (auto vs. ask_agent)
- Background execution via the trigger worker
- Integration with the daily scanner for proactive gap detection

This is a genuine competitive advantage. Most CRM tools for real estate agents don't offer this level of automated intelligence.

### 3. Seller Operations
The seller tools module (`app/tools/seller_tools.py`) is unusually complete: listing inquiry routing with occupied/vacant logic, DOM alerting with actionable recommendations at 5 thresholds, listing activity tracking, open house scheduling with cascade triggers, and attendee tracking. This suggests real domain expertise informed the design.

### 4. Data Model Coherence
The schema is well-normalized with appropriate indexes and RLS policies on every table. The `usage_metrics` table provides a single source of truth for cost tracking across SMS, voice, and LLM usage. Foreign key relationships between contacts, listings, showings, transactions, and triggers form a coherent graph.

### 5. Operator Console
The console is production-grade: 17 templates, HTMX partials for live updates, full CRUD on tenants, trigger queue management (retry/cancel/fire-now), cost dashboards, health monitoring, billing management, and a user manual. This is ready for an operator to manage 50+ agents.

---

## Coherence Assessment

**The backend is one product. The frontend is two disconnected experiences.**

The backend tools, services, and pipeline form a remarkably coherent system. Data flows naturally from inbound messages through contact resolution, intent classification, tool execution, trigger scheduling, and outbound delivery. The daily scanner and trigger worker provide proactive intelligence. The RAG system adds contextual memory. The billing system gates usage.

However, the two UIs tell different stories:
- The **operator console** is a complete management tool — it can see everything, act on triggers, manage billing, and monitor health.
- The **agent portal** is a dashboard that shows data but offers no agency. It feels like a monitoring screen, not a work tool.

This creates a fundamental UX problem: **the product's most powerful features are only accessible via SMS commands or the operator console**. A solo agent — the target user — needs to either memorize SMS command syntax or ask the operator to do things for them.

The features themselves are coherent. The surface area is not.

---

## v1 Launch Readiness Checklist

### Ready for Launch
- [x] Inbound/outbound SMS with delivery tracking
- [x] Voice call handling with Vapi transcript processing
- [x] Email channel with SendGrid
- [x] Contact management with lifecycle tracking
- [x] TCPA consent compliance
- [x] Lead scoring (rule-based)
- [x] Drip campaign templates and enrollment
- [x] Showing scheduling with hold/confirm/cancel
- [x] Google Calendar integration
- [x] Transaction lifecycle tracking
- [x] Trigger system with cascades and recurrence
- [x] Daily scanner (gaps, DOM alerts, proactive follow-ups)
- [x] Morning briefing compilation
- [x] Listing ingestion via natural language
- [x] DOM alerting with recommendations
- [x] Open house scheduling with cascades
- [x] Seller activity reports
- [x] RAG system (Voyage AI + pgvector)
- [x] Stripe billing with 3 tiers
- [x] Message quota enforcement
- [x] Operator console (full management)
- [x] Agent portal login (phone + SMS code)
- [x] RLS tenant isolation
- [x] CSRF protection
- [x] Twilio signature validation

### Needs Work Before Launch
- [ ] **Agent portal write actions** — at minimum: approve/reject triggers, send quick message, add/edit contacts
- [ ] **Firebase push notifications** — implement actual FCM sending (currently stubbed)
- [ ] **Agent self-onboarding** — sign up flow, Twilio number provisioning, preference setup
- [ ] **Contact detail view** in agent portal with linked conversations, scores, transactions
- [ ] **Error handling UX** — what happens when the AI pipeline fails? Agent sees nothing
- [ ] **Billing enforcement at pipeline level** — expired/canceled subscriptions should gate the pipeline

### Can Wait for v2
- [ ] Agent analytics dashboard (conversion rates, response times, pipeline value)
- [ ] Document/file handling for transactions
- [ ] MLS/IDX integration
- [ ] Multi-language support (schema has `language_detected` but no i18n)
- [ ] Team/brokerage features (currently strictly solo)
- [ ] Webhook for third-party integrations
- [ ] Automated A/B testing of message templates
- [ ] Client-facing portal (property search, showing booking)

---

## Feature Prioritization for Next Phase

Based on gap severity, user impact, and implementation effort:

| Priority | Feature | Effort | Impact | Rationale |
|----------|---------|--------|--------|-----------|
| P0 | Agent portal write actions (approve triggers, quick message, edit contacts) | Medium | Critical | Without this, agents cannot use the product without SMS commands |
| P0 | Firebase push notification implementation | Small | Critical | All notifications are currently black-holed |
| P1 | Contact detail view in agent portal | Small | High | Agents need to see full contact context without switching to SMS |
| P1 | Agent self-onboarding flow | Medium | High | Required for any scale beyond hand-held onboarding |
| P1 | Billing enforcement at pipeline level | Small | High | Canceled agents can still use the system |
| P2 | Agent analytics/reporting dashboard | Medium | Medium | Solo agents care deeply about their numbers |
| P2 | Conversation reply from portal | Medium | Medium | Agent should be able to compose messages from the UI |
| P2 | Settings page in agent portal (preferences, style, autonomy rules) | Small | Medium | Agents need to customize behavior without operator help |
| P3 | Document handling for transactions | Large | Medium | Important but not blocking for v1 |
| P3 | MLS integration | Large | Medium | Big feature, can be manual entry for v1 |

---

## UX Flow Continuity

### A Day in the Life: Solo Agent Using Calloway

**7:30 AM — Morning briefing**
The daily scanner compiles a briefing with today's showings, pending tasks, gap alerts, new leads, and DOM warnings. However, **the push notification is stubbed**, so the agent never receives it. If they open the agent portal, the dashboard shows some of this data (upcoming showings, pending approvals, active contacts) but not the briefing itself.

**Gap: No briefing delivery mechanism. No briefing view in the portal.**

**8:00 AM — New lead texts in**
"Hi, I saw your listing on Oak Street. Is it still available?" The SMS hits Twilio → webhook → pipeline. Contact is auto-created as `new_lead` with `lead_source` tracked. The AI classifies intent, assembles context (including RAG), composes a response, and sends it. The agent gets a push notification... **except they don't, because Firebase is stubbed.**

If the agent checks the portal, they can see the new conversation in the conversation list. They can read the messages. But they cannot reply, add notes, or update the contact from the portal.

**Gap: No notification. No ability to act from portal.**

**9:00 AM — Showing request**
The new lead wants to see the Oak Street listing at 2 PM. The AI creates a showing hold with 30-minute expiry. If the listing is occupied, it routes to the seller approval flow. The agent should receive an approval notification... **which is stubbed.**

The agent can see the showing in the schedule view of the portal. But they cannot confirm or cancel it from the portal — they have to text "Confirm [showing]" to the AI.

**Gap: No approval/confirmation from portal.**

**10:00 AM — Agent texts "Who needs follow-up?"**
The AI runs `analyze_contact_gaps()` and returns a list of contacts overdue for contact, sorted by urgency. This is well-implemented. The agent can then text "Text Sarah and check in about the inspection" and the AI composes and sends a personalized message.

**This SMS command flow works well.** It's the product's strongest interaction pattern.

**12:00 PM — Agent texts "I've got Mike, handling him directly"**
Silent mode activates for Mike. The AI stops auto-messaging him. When the agent texts "Back from Mike — he wants to see 456 Elm on Thursday," the AI reactivates messaging, creates a showing, and logs notes.

**This handoff flow is excellent UX — genuinely thoughtful.**

**2:00 PM — Showing happens**
The agent meets the lead at Oak Street. After the showing, there's no mechanism to log showing feedback from the portal. The `showings.feedback` field exists in the schema but there's no portal UI to fill it in.

**Gap: No showing feedback entry.**

**4:00 PM — Offer preparation**
The agent texts "Prep an offer for Sarah on Oak Street." The AI sends Sarah a message requesting pre-approval and proof of funds, creates a transaction record, and notifies the agent... **via a stubbed push notification.**

**6:00 PM — End of day review**
The agent opens the portal to see their day. Dashboard shows message count, showing count, active contacts. But there's no analytics: no conversion metrics, no pipeline value, no comparison to last week.

**Gap: No end-of-day summary or analytics.**

### Verdict on End-to-End Usability
The SMS command interface provides a surprisingly complete interaction model. An agent who is comfortable texting commands to the AI can accomplish most daily tasks. But the portal — which should be the *primary* interface for review, analysis, and batch actions — is a passive display. A solo agent would need to **augment Calloway with their existing CRM** rather than replace it.

---

## Recommendations

### Top 5 Actions Before Launch

1. **Implement agent portal write actions.** Add POST routes for: approve/reject trigger, send message to contact, create/edit contact, confirm/cancel showing. These are the minimum for the portal to be a work tool rather than a display screen. Estimated effort: 1-2 weeks.

2. **Ship Firebase push notifications.** The notification tier system (urgent, action_needed, informational, briefing) is fully designed. Replace the TODO stub in `app/services/firebase_service.py` with actual `firebase_admin.messaging.send()` calls. Add FCM token storage to the `agents` table. Estimated effort: 2-3 days.

3. **Build a contact detail page in the agent portal.** Route: `/agent/contacts/{contact_id}`. Show: name, phone, email, lifecycle stage, lead score, preferences, conversation history, linked transactions, linked listings, notes, drip enrollment status. This is the single most-used screen in any CRM. Estimated effort: 3-5 days.

4. **Add agent self-onboarding.** A `/agent/signup` flow: enter name, email, phone, market. Auto-create agent record, provision Twilio number (or accept existing), seed default drip campaigns, create Stripe trial subscription, send welcome SMS. The console already has `create_agent_from_wizard` — expose a self-service version. Estimated effort: 1 week.

5. **Add billing enforcement to the message pipeline.** In `app/api/webhooks.py` `process_inbound_message`, after resolving the agent, call `check_message_quota()` and block processing if the subscription is canceled or the quota is exhausted. Currently an agent with a canceled subscription can still use the system indefinitely. Estimated effort: 1 day.
