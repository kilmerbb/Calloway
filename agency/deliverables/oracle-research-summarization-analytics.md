# Oracle Research Report: Summarization Strategy & Agent Analytics

**Author:** Oracle, Researcher
**Date:** 2026-03-12
**Status:** Final

---

## Research Question 1: Conversation Summarization Strategy (T-002)

### Key Findings

1. **Rolling incremental summarization is the best fit** (High Confidence) — hybrid summary + recent buffer outperforms sliding window, pure RAG, hierarchical, and topic-based approaches for relationship-heavy conversations.

2. **Contextual drift is the primary risk** (High Confidence) — over 5-10 incremental cycles, small errors compound. A $500K budget could drift to $450K.

3. **Mitigation: periodic full re-summarization** every 5th cycle, structured key-value fields, and drift detection.

4. **Add time-based trigger** (Medium Confidence) — summarize at 25+ messages if conversation spans 30+ days for slow-burn buyers.

5. **Critical fields to preserve:** Budget range, property requirements, timeline, financing status, relationship origin, key dates, deal status, **explicit dislikes/dealbreakers**.

6. **Summary injection placement:** Beginning of context block (before recent messages) due to "lost in the middle" effect.

### Recommendations for Engineering
- Add `incremental_count` column to conversation_summaries
- Full re-summarization every 5th cycle
- Time-based trigger (25+ messages, 30+ days)
- Key-value format for critical fields
- Add dealbreakers field to prompt
- Bump summary token budget from 300 to 400-500

---

## Research Question 2: Agent Analytics That Actually Matter (T-005)

### Key Findings

1. **Response time is THE metric** (High Confidence) — 1-minute response converts at 26% vs 3% at 24 hours (8.7x). 78% of buyers work with first responder.

2. **The "aha moment" metric:** "Calloway handled X conversations while you were [sleeping/showing]" — quantifies autonomous value.

3. **Morning briefing > dashboard** (Medium-High Confidence) — agents want "what do I do today?" not charts.

4. **Competitor insight:** CRMs for teams over-index on accountability. Solo agents need decision-support, not accountability dashboards.

### Recommended Tier Structure
- **Tier 1 (Daily/Morning Briefing):** Overnight activity, action required, today's calendar, follow-ups due
- **Tier 2 (Weekly KPIs):** Response time, pipeline health, conversion funnel, autonomy score, showings
- **Tier 3 (Monthly Review):** Commission pipeline, lead source ROI, AI cost vs value

### Metrics to NOT Build
- Total messages sent/received (vanity)
- Contact database size (vanity)
- Average conversation length (not actionable)
- Detailed AI token breakdowns (internal only)

---

## Sources

### Summarization
- LLM Chat History Summarization Guide (mem0.ai)
- Recursively Summarizing Enables Long-Term Dialogue Memory (arxiv)
- Context Engineering Best Practices (Redis)
- Context Window Management Strategies (getmaxim.ai)
- How Context Drift Impacts Conversational Coherence (getmaxim.ai)
- Agent Drift: Quantifying Behavioral Degradation (arxiv)
- MemGPT: Engineering Semantic Memory (informationmatters.org)

### Real Estate Analytics
- Real Estate Agent Performance Metrics 2025 (maverickre.com)
- Real Estate Lead Response Time (rubixone.com, foneswift.com, agentzap.ai)
- Real Estate Lead Conversion Rate (Follow Up Boss)
- Follow Up Boss vs kvCORE/LionDesk Comparisons (justarealtor.com)
- Real Estate Dashboard Examples (GoodData)
