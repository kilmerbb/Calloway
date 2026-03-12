# Calloway User Stories: Interactive Portal & Agent Analytics

**Author:** Mara, Product Manager
**Date:** 2026-03-12
**Status:** Draft — Awaiting Design & Research Input

---

## Feature A: Interactive Agent Portal (T-001)

### Assumptions

- Agents are primarily on mobile between showings; desktop is secondary
- The existing SMS command interface works well — the portal should complement it, not replace it
- Agents value speed over polish; a 3-tap action beats a beautiful 6-tap one every time
- We're adding write capabilities to existing views, not building from scratch

**Needs @research Oracle input:** What are the top 5 actions agents actually perform via SMS commands today?

---

### Story A-1: Quick-Reply to Conversations (P0)

**As a** solo agent reviewing my conversations on the portal,
**I want to** tap a conversation and send a reply directly from the portal,
**So that** I don't have to switch to my SMS app or memorize reply commands when I'm between showings.

**Acceptance Criteria:**
1. Text input field and "Send" button at bottom of conversation thread
2. Message delivered via same channel as original conversation (SMS/RCS)
3. Sent message appears immediately without full page reload (HTMX partial swap)
4. Input field clears after successful send, focus returns to it
5. Delivery failure shows inline error with retry option
6. Character count displays when message exceeds 160 characters (SMS segment boundary)
7. Works on mobile — input stays anchored to bottom, keyboard doesn't obscure it

**Edge Cases:**
- Client revoked TCPA consent → Send button disabled: "This contact has opted out of messages."
- Empty conversation → Agent can still initiate if contact exists and has consent
- Supervised autonomy mode → Manual portal replies send immediately (autonomy governs AI, not human)
- Network failure mid-send → Optimistic UI reverts; draft text preserved in input field

---

### Story A-2: Reschedule or Cancel a Showing (P0)

**As a** solo agent looking at my schedule,
**I want to** reschedule or cancel an upcoming showing with one or two taps,
**So that** I can react quickly when a client cancels or a conflict arises.

**Acceptance Criteria:**
1. Each upcoming showing has "Reschedule" and "Cancel" actions
2. Cancel: confirmation modal → showing removed → client notified
3. Reschedule: date/time picker → agent selects new time → confirmation → client notified
4. Past showings cannot be cancelled/rescheduled
5. Schedule view updates immediately without full page reload
6. Success toast confirms action: "Showing cancelled. Jane Doe has been notified."

**Edge Cases:**
- Showing in next 30 minutes → stronger warning: "This showing is in 28 minutes. Are you sure?"
- Client revoked consent → Showing cancelled but notification can't be sent; toast explains
- Agent reschedules to conflicting time → Warning but allow it (agents double-book intentionally)
- No upcoming showings → "No upcoming showings." with prompt to create one

---

### Story A-3: Create a New Contact (P1)

**As a** solo agent who just met a potential client,
**I want to** add a new contact from the portal with minimal required fields,
**So that** the lead is captured immediately while I still remember the context.

**Acceptance Criteria:**
1. Prominent "Add Contact" button on contacts page
2. Required fields: First name, phone number. That's it.
3. Optional: Last name, email, source (dropdown), notes (free text)
4. Phone validated for format; duplicate phone flagged with link to existing contact
5. Success message: "Contact added: [Name]"
6. After save, offer: "Send intro message" or "Done"
7. Completable in under 15 seconds on phone keyboard

**Edge Cases:**
- Duplicate phone → Surface existing contact, let agent update
- No country code → Default to +1 (US)
- Zero contacts (new agent) → Prominent "Add your first contact" CTA
- Phone only, no name → Allow it, save as "Unknown"

---

### Story A-4: Edit a Trigger (P1)

**As a** solo agent managing automated follow-ups,
**I want to** pause, resume, or edit a scheduled trigger from the portal,
**So that** I can adapt my automation without rebuilding from scratch via SMS.

**Acceptance Criteria:**
1. Triggers page shows active/paused triggers with next fire time, target, message preview
2. Three actions: Pause, Resume, Edit
3. Pause/resume are single-tap with inline confirmation (no modal)
4. Edit allows changing: scheduled time, message content, recurrence (NOT contact target)
5. Triggers due within 60 seconds cannot be edited
6. All changes logged for auditability

**Edge Cases:**
- Already-fired trigger → Show in "completed" section with "Clone" action
- Agent pauses all → Support "Pause All" bulk action
- Zero triggers → Empty state with explanation
- Trigger target revoked consent → Warning badge: "Contact has opted out — trigger will not fire"

---

### Story A-5: AI-Assisted Actions from Dashboard (P1) — FAST-FOLLOW

**As a** solo agent looking at my dashboard,
**I want to** tap a contextual action button that asks Calloway's AI to do something,
**So that** I get the AI's power without leaving the portal or remembering SMS commands.

**Actions:**
- "Draft a follow-up" → AI generates draft, agent edits and sends
- "Summarize this conversation" → AI generates 2-3 sentence summary inline
- "Draft intro message" → AI generates personalized intro from contact metadata
- "Suggest next steps" → AI recommends actions based on history and score

**Note:** Flagged as fast-follow by Solomon — bigger scope than bolt-on.

---

## Feature B: Agent Analytics Dashboard (T-005)

### Assumptions

- Agents are not data analysts — they want answers, not charts
- The morning ritual is real — this should be the first screen with coffee
- "Analytics" is wrong — UI should say "My Numbers" or "Business Pulse"

---

### Story B-1: Morning Briefing Dashboard (P0)

**As a** solo agent starting my day,
**I want to** see what happened overnight and what needs attention today,
**So that** I can prioritize my day in 30 seconds.

**Sections:**
1. **Today's Schedule:** Showings count, next showing time/address, triggers due today, conflicts
2. **Overnight Activity:** New inbound messages, AI-handled conversations, failed triggers/errors
3. **Pipeline Snapshot:** Active leads (30d), hot leads (score increase 7d), cold leads (no interaction 14d+)

**Edge Cases:**
- New agent, no data → Show structure with zeros + onboarding prompts
- Agent absent 7+ days → Expand overnight to cover gap
- All AI conversations handled fine → Positive signal, no click-through needed
- Agent on Manual mode → Hide AI sections

---

### Story B-2: Response Time & Engagement (P1)

- Average first-response time (this week vs last)
- Slowest response with conversation link
- Active conversations, conversations needing reply (2hr+)
- AI vs human response ratio

---

### Story B-3: Cost & ROI Transparency (P1)

- AI cost + messaging cost for billing period
- Daily cost trend
- "Calloway handled 340 messages, saving ~11 hours"
- Per-conversation cost drilldown

---

### Story B-4: Lead Pipeline Health (P2)

- New leads this month vs last
- Lead source breakdown
- Score distribution (Hot/Warm/Cool/Cold)
- Leads needing attention (high score, no contact in 7d+)

---

## Open Questions

1. Mobile-first or responsive? (Lyra to define breakpoints)
2. Push notification actions scope — T-001 or separate?
3. Offline support feasibility? (Atlas to assess)
4. Daily scanner timing vs morning check-in (Atlas to confirm)
5. Analytics data retention window (Atlas to recommend)
