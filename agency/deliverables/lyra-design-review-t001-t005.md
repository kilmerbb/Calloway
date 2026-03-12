# Design Review: Interactive Portal (T-001) & Analytics Dashboard (T-005)

**Reviewer:** Lyra, Product Designer
**Date:** 2026-03-12
**Status:** Final — 5 refinement items identified

---

## Implementation Status

All 5 interactive features and the analytics dashboard are fully implemented in HTML + CSS.

### Feature A — Interactive Elements (All Implemented)

1. **Trigger approve/reject** — Inline HTMX forms swap button pairs for status badges
2. **Conversation reply** — Sticky bottom reply bar with HTMX append to chat thread
3. **Contact edit** — Expand-in-place `<details>` panels for edit form and quick note
4. **Showing confirm/cancel** — Inline HTMX buttons that swap status badges
5. **Quick note** — Integrated into contacts expand panel

### Feature B — Analytics Dashboard (Fully Implemented)

- KPI cards with trend indicators
- CSS-only stacked bar chart (30-day conversation volume)
- Horizontal pipeline funnel bars
- Activity summary tables
- AI cost grid
- Responsive: 2-column → single column on mobile

---

## Required Refinements

### 1. CRITICAL: Cancel Showing Confirmation (Must Fix)

Current: Single tap cancels and notifies client immediately.
Required: Two-step inline confirmation.
- First tap: "Cancel this showing? [Yes, cancel] [Keep it]"
- Second tap: Executes cancellation
- Implementation: HTMX partial via `hx-get` before real `hx-post`

### 2. Analytics Empty States (Must Fix)

- Wrap chart in `{% if volume %}...{% else %}<div class="empty-state">{% endif %}`
- Show "--" instead of "0" for response time KPIs with no data
- New agent onboarding message in each section

### 3. HTMX Loading Indicators (Should Fix)

- Add `hx-indicator` attributes to trigger and showing action buttons
- CSS infrastructure already exists (`.htmx-indicator`, `.skeleton`)

### 4. Pipeline Bar Accessibility (Should Fix)

- Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax`

### 5. Analytics Mobile Nav (Should Fix)

- Add analytics link to mobile "More" menu (base.html lines 62-75)
- Currently only in desktop nav
