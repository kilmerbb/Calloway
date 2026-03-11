# Calloway: Competitive Landscape & Market Assessment
**Prepared by:** Oracle (Research)
**Date:** March 11, 2026
**Classification:** Internal Strategy Document

---

## 1. What Calloway Does Today

Based on a thorough codebase review, Calloway is a multi-tenant SaaS AI operational assistant for solo real estate agents. Here is what it does:

### Core Message Pipeline
- **Inbound SMS/RCS handling** via Twilio webhooks with full signature validation
- **Inbound voice call handling** via Twilio with Vapi fallback (rings agent 4x, then forwards to AI voice assistant)
- **Vapi post-call processing** with transcript summarization, contact creation, and RCS follow-up to callers
- **Email inbound** endpoint (stubbed, not yet implemented)
- **Full NLP pipeline:** Normalize -> Resolve Contact -> TCPA Check -> Rate Limit -> Consent Gate -> Classify Intent -> Route & Handle -> Dispatch

### Agent Command Channel (SMS-based control plane)
The agent texts their Twilio number to control the AI. Supported command types:
- `client_instruction` -- "Text Sarah and confirm Thursday"
- `listing_update` -- "New listing 123 Oak, 3/2, 475K" or price drops
- `broadcast` -- "Send 200 Front to matching buyers"
- `status_change` -- "I'm in showings until 3" / "I'm back"
- `query_contact` -- "What's going on with Mike?"
- `query_gap` -- "Who needs follow-up?"
- `query_schedule` -- "What's my day look like?"
- `query_listing` -- "How many showings on 123 Oak this week?"
- `trigger` -- "Remind me to follow up with Sarah Friday"
- `cascade` -- "Open house Saturday 1-3"
- `offer` -- "Sarah wants to offer on 123 Oak"
- `handoff_return` -- "Back from Sarah. We're seeing 123 Oak Saturday 11am."
- `note` -- "Note on Sarah: lease ends June 30"
- `connect` -- "Connect Sarah Chen +12675551234"

### AI Model Tiering
- **Template responses** -- Zero LLM cost for confirmations, acknowledgments, escalations
- **Haiku** -- Fast/cheap for listing Q&A, command parsing, intent classification
- **Sonnet** -- Full reasoning with tool use for complex client interactions (showing scheduling, multi-turn conversations)

### Listing Management
- Full CRUD for listings via SMS commands
- Missing field detection and follow-up prompts
- Listing Q&A for buyer inquiries (Haiku-powered)
- Listing broadcast to matching active buyers
- DOM (Days on Market) tracking with configurable alert thresholds (14, 30, 45, 60, 90 days)
- DOM-triggered strategic recommendations (pricing adjustments, staging, relist)

### Showing Scheduling
- Hold-based system with 30-minute expiry
- Google Calendar integration for confirmed showings
- Occupied property workflow with seller approval requirement
- Buffer time enforcement between showings
- Stale hold expiration via background worker

### Contact/CRM
- Full contact lifecycle tracking: new_lead -> active_buyer/seller -> active_client
- Preference tracking (areas, timeline, preapproved, property type, bedrooms, bathrooms, price range)
- Gap analysis -- identifies contacts needing attention based on last contact date
- Silent mode (agent handling contact directly)
- Interaction counting
- Language detection field
- Notes system

### Trigger System (Scheduled Automation)
- Background worker polling every 60 seconds
- Trigger types: follow_up, review_request, daily_briefing, gap_follow_up, dom_alert, proactive_follow_up, deadline, status_revert
- Action types: notify_agent (push), send_message (SMS), both, compile_report
- Recurrence: daily, weekly, monthly, annually
- Autonomy levels: auto (sends directly), ask_agent (notifies for approval)
- Cascade triggers for open houses and deal milestones

### Daily Scanner (Morning Evaluation)
- Runs once per morning for all agents
- Contact gap analysis -> creates follow-up triggers
- DOM alerts for aging listings
- Proactive follow-ups for leads going cold (2-5 days inactive)
- Morning briefing compilation and push notification delivery

### Seller Operations
- Listing inquiry routing (occupied vs. vacant properties)
- Occupied home showing coordination with seller approval
- Listing activity tracking (showings, inquiries, feedback)
- Weekly seller activity reports
- Open house scheduling with trigger cascades and buyer matching

### TCPA Compliance
- Consent status tracking (pending, granted, revoked)
- STOP/HELP/START keyword processing
- Consent log with full audit trail
- Revoked consent blocks all automated messages
- Rate limiting on outbound messages

### Admin Console (/console)
- Dashboard with system pulse (active tenants, messages today, errors, LLM cost)
- Live activity feed (auto-refresh via HTMX)
- Tenant management (CRUD, onboarding wizard, test SMS, deactivation)
- Conversation browser with full chat thread view and inline tool execution traces
- Trigger queue management (retry, fire now, cancel)
- Error tracking (tool execution errors + application errors)
- Cost dashboard (30-day LLM spend, per-agent breakdown, model tier distribution, $/msg)
- Health monitoring (service connectivity, pipeline latency p50/p95)
- User manual built into the console

### Testing & Quality
- 24 test files covering: handlers, classifier, normalizer, resolver, contacts, listings, showings, triggers, seller tools, webhooks, voice, daily scanner, console, harness, health, hardening, e2e client messaging, e2e command channel, e2e triggers
- Test harness for conversation simulation (/harness)
- Harness trace storage for debugging

### Database Schema
- 15 tables with full RLS (Row Level Security) for tenant isolation
- pgvector extension for embeddings (1536 dimensions with IVFFlat index)
- Usage metrics tracking (messages, LLM calls, tokens, cost, voice minutes, showings, triggers)

### Key Technical Architecture
- Python 3.12 / FastAPI / Uvicorn
- PostgreSQL 16 + pgvector on Supabase
- Redis for caching
- Twilio (SMS/RCS/Voice), Vapi (AI Voice), Google (Calendar, Business Profile), Firebase (push notifications)
- Jinja2 + HTMX (server-rendered, no SPA)
- Docker + Railway deployment

---

## 2. Competitive Landscape

### Tier 1: Direct Competitors (AI-first operational assistants for real estate agents)

#### Structurely
- **What:** AI assistant for lead conversion via text, email, and web chat
- **Strengths:** Instant lead response (<60s), 12-month automated follow-up, Call AI for inbound calls, CRM integrations (Follow Up Boss, Sierra, kvCORE)
- **Pricing:** ~$200/month for individual agents
- **Differentiation from Calloway:** Structurely is lead-conversion focused -- it qualifies and hands off. Calloway is an operational assistant that manages the full agent workflow (listings, showings, seller ops, daily briefings). Structurely does not manage listings, showings, or seller operations.
- **Confidence:** HIGH

#### Ylopo (RAIYA AI)
- **What:** AI-first lead generation and nurturing platform with AI Voice and AI Text
- **Strengths:** Facebook/Google ad-driven lead gen, AI Voice calls leads 14x over 90 days (45% answer rate), AI Text (25M+ conversations, 48% response rate), 25% old lead re-engagement rate, dynamic seller lead gen ($25/lead)
- **Pricing:** Not publicly listed; estimated $500-1500+/month (lead gen + platform)
- **Differentiation from Calloway:** Ylopo is a marketing + lead gen platform that happens to have AI follow-up. Calloway is an operational layer that assumes leads exist and manages the entire agent workflow. Different value propositions. Ylopo does not do showing scheduling, seller ops, or daily briefings.
- **Confidence:** HIGH

#### Cloze CRM
- **What:** AI-powered CRM for real estate with automatic data capture, AI follow-ups, and virtual assistant (Maia)
- **Strengths:** Automatic data capture from calls/texts/emails, AI-powered follow-up prompts, MLS integration, transaction management, mobile-first, selected by eXp Realty (81,000 agents), Maia AI assistant for natural language queries
- **Pricing:** Starting at $17/month
- **Differentiation from Calloway:** Cloze is a traditional CRM with AI layered on top. Calloway operates via SMS (no app required for the agent) and handles the actual communication with clients autonomously. Cloze requires agents to log in and take action; Calloway acts on behalf of the agent.
- **Confidence:** HIGH

#### Lindy AI (Real Estate Agents)
- **What:** Ready-to-use AI agents that generate leads, qualify, book appointments, handle calls, and update CRM
- **Strengths:** Multi-agent architecture (capture, qualify, update), shared context across workflows, smooth handoffs
- **Differentiation from Calloway:** Lindy is a horizontal AI agent platform with real estate templates. Calloway is purpose-built for real estate with deep domain logic (DOM alerts, showing holds, seller ops, TCPA compliance). Lindy is more generic.
- **Confidence:** MEDIUM

#### Crescendo.ai
- **What:** AI-powered conversational platform for real estate (live chat, voice, email, SMS)
- **Strengths:** Multi-channel (chat, phone, email, SMS), 24/7 lead capture, context-aware responses on listings/mortgages/HOA
- **Differentiation from Calloway:** Crescendo focuses on inbound lead capture from websites. Calloway manages the ongoing agent-client relationship after the lead is captured.
- **Confidence:** MEDIUM

### Tier 2: Adjacent Competitors (CRM/lead management with AI features)

| Competitor | Focus | AI Capability | Threat Level |
|-----------|-------|--------------|-------------|
| **Follow Up Boss** | Lead management CRM | AI-assisted follow-up sequences, 250+ lead source integrations | MEDIUM -- dominant in CRM, but AI is bolted on |
| **Sierra Interactive (Lead Engage)** | Website + CRM platform | AI-powered two-way text conversations for lead qualification | MEDIUM -- primarily a lead gen platform |
| **Lofty (formerly Chime)** | Full-stack CRM + DXP | 3 types of AI assistants, IDX websites, Zapier integration | MEDIUM -- broad but not deep on AI ops |
| **NovaCRM** | AI-powered CRM | AVON AI chatbot, lead gen, IDX websites, marketing automation | LOW-MEDIUM -- newer player |
| **CINC** | Lead gen + CRM | CINC AI add-on for lead readiness scoring | LOW -- primarily a lead gen platform |
| **Rechat (Lucy)** | All-in-one agent platform | AI creates marketing materials, websites, personalized comms | LOW -- marketing-focused, not operational |
| **alfred_** | Email triage + relationship layer | Client email triage, follow-up tracking, meeting prep, Daily Brief | LOW-MEDIUM -- email-only channel |

### Tier 3: Tangential / Future Competitors

| Competitor | Why to Watch |
|-----------|-------------|
| **OpenAI / ChatGPT (custom GPTs)** | Agents building DIY assistants; commoditization risk |
| **Wise Agent** | Budget CRM ($32/mo) adding AI features; competes on price |
| **Lone Wolf** | Enterprise CRM with AI email marketing; could move downmarket |
| **Salesforce (Real Estate Cloud)** | Enterprise entry into RE; unlikely to target solos but sets expectations |

---

## 3. Market Size & Opportunity

### Total Addressable Market (TAM)

**Global PropTech Market:** $47.08B in 2025, projected to reach $185.31B by 2034 (16.4% CAGR)

**AI in PropTech:** $20.5B in 2023, projected to reach $159.9B by 2033 (22.8% CAGR)

**U.S. PropTech Market:** $24.73B in 2026, projected to reach $76.84B by 2034 (18.5% CAGR)

**Real Estate AI Chatbot Market (estimated):** $2.6-2.7B in 2025 (real estate = 28% of global chatbot market)

**Confidence:** HIGH (multiple corroborating research sources)

### Serviceable Addressable Market (SAM)

**Target:** Solo real estate agents in the United States who would pay for an AI operational assistant

- ~1.5M NAR members (Feb 2025), down 2.1% YoY
- ~3M total active real estate licenses
- Industry is highly fragmented: 106,000+ brokerages, avg 14.6 agents/office
- Majority of agents are solo or small team (NAR data indicates most agents work independently)
- Conservative estimate: 500,000-800,000 solo agents in the US
- At $150-300/month price point: **SAM = $900M - $2.88B annually**

**Confidence:** MEDIUM (solo agent count is estimated; price point is assumed)

### Serviceable Obtainable Market (SOM)

**Realistic 3-year target:**
- 1,000-5,000 paying agents
- At $200/month average: **SOM = $2.4M - $12M ARR**
- This represents 0.1-0.6% of the estimated solo agent population

**Confidence:** MEDIUM (depends on go-to-market execution, pricing, and product-market fit)

### Market Dynamics

- 72% of major RE firms already use AI; 25% more are exploring
- 50%+ of agents have adopted some form of AI
- Real estate firms earn ~$30.48 ROI for every $1 spent on CRM
- CRM automation raises engagement by 28%
- AI chatbots deliver 40% higher lead capture and 50% faster response
- Agent attrition is high (median income for <2yr agents = $10,100)
- NAR membership declining for first time since 2012

---

## 4. Positioning Analysis

### Calloway's Unique Position

Calloway occupies a distinctive niche that no competitor fully addresses: **the full-stack AI operational layer for solo agents, controlled entirely via SMS.**

| Dimension | Calloway | Structurely | Ylopo | Cloze | Follow Up Boss |
|-----------|----------|-------------|-------|-------|----------------|
| Primary interface | SMS (no app needed) | Web dashboard | Web dashboard | App + Web | Web dashboard |
| Lead qualification | Yes (AI) | Primary focus | Primary focus | Manual + AI prompts | AI-assisted |
| Client communication | Autonomous AI | AI (text/email) | AI (text/voice) | Manual with AI prompts | Manual with sequences |
| Listing management | Full CRUD via SMS | None | None | MLS integration | None |
| Showing scheduling | Full workflow (hold/confirm/calendar) | None | None | Basic | None |
| Seller operations | Full (inquiry routing, DOM alerts, reports) | None | None | Transaction mgmt | None |
| Daily briefings | Yes (push notification) | None | None | AI agenda | None |
| Trigger/automation | Deep (8+ types, recurrence, cascades) | 12-month follow-up | Ad retargeting | AI follow-up prompts | Drip sequences |
| TCPA compliance | Built-in (consent tracking, keyword handling) | Unknown | Unknown | Unknown | Basic |
| Autonomy levels | 3 (supervised/autonomous/manual) | N/A | N/A | N/A | N/A |
| Multi-tenant admin | Full operator console | N/A | N/A | Brokerage admin | Team admin |
| Voice handling | Vapi integration with fallback | Call AI | AI Voice | Call tracking | Call tracking |
| Price point | TBD | ~$200/mo | $500-1500+/mo | $17+/mo | $69+/mo |

### Strengths

1. **Zero-app operation** -- The agent controls everything via SMS. No app to download, no dashboard to learn. This is a genuine moat for busy solo agents who live on their phones.
2. **Full operational scope** -- Calloway manages listings, showings, contacts, triggers, seller ops, and briefings. Competitors typically handle only 1-2 of these.
3. **Autonomous operation with guardrails** -- The 3-level autonomy system (supervised/autonomous/manual) is unique. Competitors are either fully automated or fully manual.
4. **TCPA compliance built in** -- Most competitors treat compliance as an afterthought. Calloway has consent tracking, keyword handling, and audit logging at the database level.
5. **Seller operations** -- DOM alerting, occupied-home showing coordination, and weekly seller reports are features that no direct competitor offers in an AI-first format.
6. **Cost-optimized AI** -- The template/Haiku/Sonnet tiering is thoughtful. Most competitors use a single model for everything, burning through API costs.
7. **Multi-tenant architecture** -- RLS-based tenant isolation enables a clean operator/agent model. This supports a brokerage distribution channel.

### Gaps & Weaknesses

1. **No lead generation** -- Calloway assumes leads exist. Ylopo and CINC generate leads. This is a significant gap for agents who need top-of-funnel help.
2. **No MLS integration** -- Cloze, Lofty, and Sierra all integrate with MLS data. Calloway requires manual listing entry via SMS, which is friction-heavy for agents with many listings.
3. **No web/mobile app** -- The SMS-only interface is both a strength and weakness. Agents cannot view conversation history, manage contacts visually, or review pending triggers without the operator console.
4. **Email channel not implemented** -- The email inbound endpoint is stubbed. Email is critical for contracts, disclosures, and agent-to-agent communication.
5. **No marketing/content generation** -- Rechat (Lucy), Ylopo, and Epique can generate listing descriptions, social media posts, and marketing materials. Calloway cannot.
6. **No IDX website** -- Ylopo, CINC, Lofty, and Sierra all offer branded search portals. Calloway has no consumer-facing web presence.
7. **Limited analytics** -- The operator console tracks costs and message volume, but lacks conversion analytics (lead-to-client conversion rate, showing-to-offer ratio).
8. **No transaction management** -- Cloze and Lone Wolf track deals from offer to close. Calloway has an offer command but no post-offer workflow.

---

## 5. Strategic Recommendations

### Recommendation 1: Build a Lightweight Agent Mobile App
**Priority:** CRITICAL
**Rationale:** While SMS-first is a great onboarding hook, agents need a visual interface for reviewing conversation history, managing contacts, and approving pending actions. The Supervised autonomy mode (approval required) is nearly unusable via SMS alone. A simple mobile app with push notification deep links would dramatically improve the Supervised workflow and create a second engagement surface.
**Confidence:** HIGH

### Recommendation 2: Add MLS Integration for Automated Listing Sync
**Priority:** HIGH
**Rationale:** Manually entering listings via SMS is the highest-friction part of the product. MLS integration (via RETS/RESO API or Spark API) would allow automatic listing population, price change detection, and status updates. This would also enable the pgvector embeddings table to be populated with listing data for semantic search (the table exists but appears underutilized).
**Confidence:** HIGH

### Recommendation 3: Target Brokerage Distribution Channel
**Priority:** HIGH
**Rationale:** The multi-tenant architecture with RLS and the operator console are already built for this. A brokerage signs up, gets the operator console, and rolls Calloway out to their agents. This mirrors Cloze's eXp Realty deal (81,000 agents). Brokerage distribution solves the CAC problem for solo agents (who are expensive to acquire individually). The existing admin console supports this with minimal modification.
**Confidence:** HIGH

### Recommendation 4: Implement Email Channel
**Priority:** MEDIUM-HIGH
**Rationale:** The email inbound endpoint exists but returns a stub response. Real estate transactions generate significant email volume (contracts, disclosures, lender communications). Even a BCC-capture model (where agents BCC Calloway) would enable the AI to maintain context about deal progress without requiring full email integration.
**Confidence:** MEDIUM (depends on build complexity and whether agents will change email habits)

### Recommendation 5: Build Conversion Analytics Dashboard
**Priority:** MEDIUM
**Rationale:** The usage_metrics table tracks operational metrics (messages, tokens, cost) but not business outcomes. Adding lead-to-client conversion rate, average response time, showing-to-offer ratio, and lead source attribution would allow agents to see ROI and provide Calloway with a retention hook. This data is already latent in the schema (contacts lifecycle_stage progression, showings, offers) -- it just needs to be surfaced.
**Confidence:** HIGH

---

## 6. Confidence Assessment Summary

| Finding | Confidence | Basis |
|---------|-----------|-------|
| Calloway's current capabilities | HIGH | Direct codebase review |
| Competitor feature comparison | HIGH | Web research + product pages |
| Competitor pricing | MEDIUM | Publicly available for some; estimated for others |
| TAM ($47B PropTech, $2.6B RE chatbot) | HIGH | Multiple research firms corroborate |
| SAM ($900M-$2.88B) | MEDIUM | Solo agent count is estimated |
| SOM ($2.4M-$12M ARR) | MEDIUM | Depends on GTM execution |
| "SMS-first" as differentiation | HIGH | No competitor operates this way |
| Brokerage channel opportunity | HIGH | Architecture already supports it |
| MLS integration as critical gap | HIGH | Industry standard across competitors |
| Mobile app necessity | HIGH | Supervised mode workflow analysis |

---

## Sources

- [HousingWire: 16 AI Tools for Real Estate Agents](https://www.housingwire.com/articles/ai-tools-real-estate/)
- [The Close: 10 Best AI Tools for Real Estate 2026](https://theclose.com/best-real-estate-ai-tools/)
- [V7 Labs: Best AI Tools for Real Estate 2026](https://www.v7labs.com/blog/best-ai-tools-for-real-estate)
- [Ascendix: AI for Real Estate Agents (35+ Tools)](https://ascendix.com/blog/ai-real-estate-agents/)
- [Crescendo.ai: Conversational AI for Real Estate](https://www.crescendo.ai/blog/conversational-ai-for-real-estate)
- [Crescendo.ai: Best Real Estate Chatbots](https://www.crescendo.ai/blog/best-real-estate-chatbots-with-ai)
- [Ylopo: AI for Real Estate](https://www.ylopo.com/ai-for-real-estate)
- [The Close: Ylopo Review](https://theclose.com/ylopo-reviews/)
- [Cloze: AI-Powered Real Estate](https://ai.cloze.com/)
- [eXp Realty selects Cloze](https://finance.yahoo.com/news/exp-realty-selects-cloze-ai-160100286.html)
- [Lindy AI: Real Estate Lead Generation](https://www.lindy.ai/blog/how-to-use-ai-for-real-estate-lead-generation)
- [Sierra Interactive: Lead Engage](https://sierrainteractive.com/insights/blog/using-ai-for-lead-engagement-in-real-estate/)
- [Archiz: Best CRM for Single Agents](https://archizsolutions.com/best-real-estate-crm-for-single-agents/)
- [Precedence Research: PropTech Market Size](https://www.precedenceresearch.com/proptech-market)
- [Fortune Business Insights: PropTech Market](https://www.fortunebusinessinsights.com/proptech-market-108634)
- [PwC: How PropTech and AI are Transforming Real Estate](https://www.pwc.com/us/en/industries/financial-services/asset-wealth-management/real-estate/emerging-trends-in-real-estate-pwc-uli/trends/proptech-impact.html)
- [Leads Deposit: How Many Realtors in the US](https://leadsdeposit.com/how-many-realtors-in-the-us/)
- [RubyHome: Number of Realtors in the US](https://www.rubyhome.com/blog/number-of-realtors/)
- [NAR: Quick Real Estate Statistics](https://www.nar.realtor/research-and-statistics/quick-real-estate-statistics)
- [NAR: 2025 Member Trends](https://www.nar.realtor/magazine/real-estate-news/sales-marketing/income-steady-even-as-market-slows-2025-member-trends)
- [Master of Code: Chatbot Statistics 2026](https://masterofcode.com/blog/chatbot-statistics)
- [RTS Labs: AI Chatbot for Real Estate](https://rtslabs.com/ai-chatbot-for-real-estate/)
- [Market.us: PropTech Market](https://market.us/report/proptech-market/)
