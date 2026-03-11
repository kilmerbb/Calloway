# UI/UX Review: Calloway Operator Console

**Reviewer:** Lyra (Product Designer)
**Date:** 2026-03-11
**Scope:** All 17 console templates, 1 partial, route handler, and stylesheet

---

## Executive Summary

The Calloway operator console is a well-structured internal admin dashboard with strong fundamentals: clean dark-theme design system, consistent component vocabulary, solid mobile responsiveness, and thoughtful accessibility features (skip-nav, ARIA labels, title attributes throughout). The onboarding wizard is a standout -- it demonstrates genuinely excellent UX craft with its stepped flow, inline validation, option cards, and review summary.

The issues identified below are primarily in three categories: (1) template bugs that will cause runtime errors, (2) information architecture gaps that create dead-end workflows, and (3) accessibility and data-density refinements that would raise the console from good to excellent.

---

## Screen-by-Screen Review

### 1. Login (`login.html`)

**Strengths:**
- Clean, centered layout. Autofocus on the password field is correct.
- CSRF token present. Error state handled.
- Standalone HTML (does not extend base.html), which is correct since there is no nav context.

**Issues:**
- **No username field.** This is a single-password auth scheme (shared credential from `CONSOLE_PASSWORD`). Acceptable for a solo-operator tool, but worth noting -- there is no audit trail of who logged in.
- **No "show password" toggle.** Minor, but useful when entering a long shared password.
- **No rate limiting feedback.** If the backend rate-limits login attempts, the user gets no indication. The template only shows "Invalid password." Consider adding a lockout message.

**Severity:** Low

---

### 2. Base Layout (`base.html`)

**Strengths:**
- Skip-nav link for keyboard users.
- Sidebar with clear nav hierarchy and `title` attributes on every link.
- Sticky topbar with auto-refreshing health status dot (HTMX, 30s interval).
- Mobile hamburger menu with overlay -- well-implemented.
- `role="navigation"` and `aria-label` on the sidebar nav.
- `role="main"` on the content area.

**Issues:**

- **BUG: Template directory path resolution.** The `Jinja2Templates` directory is set to the `console/` subdirectory in `console.py` (line 18-19). All child templates use `{% extends "base.html" %}`, which resolves relative to that directory. The `_render` function calls `templates.TemplateResponse(request, template, ctx)`. In newer FastAPI/Starlette versions the signature changed -- verify this works with the installed version. If it breaks, the positional argument order may need to be `TemplateResponse(name, context, request)`.

- **No breadcrumb or back-navigation affordance.** The sidebar is the only navigation mechanism. On detail pages (tenant detail, conversation detail), there is no "Back to list" link in the content area itself -- users must use the sidebar or browser back. This is a minor friction point on deep pages.

- **Sidebar nav ordering could be improved.** "Onboard Agent" is the second item, above "Tenants." Since onboarding is an infrequent action, it could be lower in the list. The current order mixes frequency-of-use with logical grouping. A recommended order:
  1. Dashboard
  2. Tenants
  3. Conversations
  4. Triggers
  5. Errors
  6. Billing
  7. Costs
  8. Health
  9. Onboard Agent (less frequent)
  10. Harness (dev tool)
  11. Manual (reference)
  12. Logout

- **No active page indicator for the Harness.** The harness link points to `/harness/` (a separate app), so `active_nav` will never match it within the console templates. This is cosmetic but worth noting.

- **Logout link uses inline style** (`style="margin-top: auto; ..."`) instead of a CSS class. This works but breaks the separation of concerns pattern used everywhere else.

**Severity:** Medium (nav ordering), Low (rest)

---

### 3. Dashboard (`dashboard.html`)

**Strengths:**
- Pulse cards give an immediate system overview. Color-coded error count (red when > 0) is a good attention signal.
- Activity feed auto-refreshes via HTMX every 15s -- good for a monitoring dashboard.
- "Needs Attention" panel with error agents and inactive agents is operationally useful.
- Empty state ("All clear.") is handled.

**Issues:**

- **No link from pulse cards to their detail pages.** "Errors 24h" should link to `/console/errors`. "LLM Cost Today" should link to `/console/costs`. "Messages Today" could link to `/console/conversations`. These are missed navigational shortcuts.

- **"Active Tenants" label is misleading.** The backend provides `pulse.total_agents`, which is the total count, not filtered to "active" status. The card label says "Active Tenants" but likely shows all tenants including deactivated ones. Verify the backend query or rename.

- **No time range context on the dashboard.** The pulse cards show "today" and "24h" metrics, but there is no indication of what timezone "today" refers to (server time). A small note like "All times UTC" or the server's timezone would reduce ambiguity.

- **Activity feed loading state is plain text.** `Loading...` as a string is functional but could benefit from a skeleton loader or spinner for polish.

**Severity:** Medium (missing links), Low (rest)

---

### 4. Conversations List (`conversations.html`)

**Strengths:**
- Filter bar with agent, channel, and search is comprehensive.
- Table shows all essential fields. Last message preview truncated at 80 chars.
- Empty state handled.

**Issues:**

- **No pagination.** The backend limits to 100 results (`limit=100` in `console.py` line 330). With many tenants and high message volume, 100 conversations may not be enough, and there is no way to see older ones. Add pagination or "Load more."

- **No indication of unread or needs-attention conversations.** In a supervised autonomy mode, an operator might need to see which conversations have pending drafts awaiting approval. There is no visual distinction.

- **Channel filter labels are raw lowercase strings.** `sms`, `rcs`, `vapi`, `email` -- the `vapi` label is an internal name that means nothing to an operator unfamiliar with the system. Consider displaying "Voice" instead of "vapi" and capitalizing all channel names.

- **Table not sortable.** Clicking column headers should toggle sort order. Currently the table is rendered in whatever order the backend returns.

- **Phone column lacks formatting.** Raw E.164 numbers like `+15551234567` are hard to scan. Consider formatting as `(555) 123-4567`.

**Severity:** High (no pagination), Medium (rest)

---

### 5. Conversation Detail (`conversation_detail.html`)

**Strengths:**
- Chat thread layout with color-coded messages (client/AI/system) is clear.
- Metadata line (model, tokens, intent, feedback, timestamp) is rich.
- Inline tool execution details are expandable -- good progressive disclosure.
- Sidebar with contact info and active triggers provides context.

**Issues:**

- **BUG: Tool execution inline rendering logic is fragile.** Lines 23-35 attempt to interleave tool executions between messages using timestamp comparison. The logic `{% if loop.first or te.created_at <= (detail.messages[loop.index].created_at if loop.index < detail.messages|length else te.created_at) %}` is problematic:
  - `loop.index` inside the inner `{% for te ... %}` loop refers to the tool execution loop index, not the message loop index. This means tool executions will not be correctly placed between messages.
  - The outer loop's `loop` variable is shadowed by the inner loop. This is a Jinja2 scoping issue.
  - **Recommended fix:** Pre-merge messages and tool executions into a single chronological list in the backend, or use Jinja2's `namespace` to track the outer loop index.

- **No "back to conversations" link** in the content area. User must use sidebar or browser back.

- **Chat messages are not auto-scrolled to the bottom.** For long conversations, the user lands at the top and must scroll down manually. Consider scrolling to the most recent message on page load.

- **No indication of message delivery status.** For AI-generated messages, there is no indication of whether the message was actually sent (delivered via Twilio) or is still a draft awaiting approval. This is critical for supervised mode.

- **`feedback_score is not none`** (line 17) -- this uses Jinja2's `is not none` test. Confirm the installed Jinja2 version is 2.11+ which supports this syntax. Older versions need `{% if m.feedback_score != None %}`.

**Severity:** High (tool execution bug), Medium (rest)

---

### 6. Tenants List (`tenants.html`)

**Strengths:**
- Search filter. "New Tenant" CTA prominently placed.
- Status logic with badges (active/inactive/deactivated) is clear.
- Error count highlighted in red.
- Empty state handled.

**Issues:**

- **Status logic relies on `a.last_active.isoformat is defined`** (line 41) as a proxy for "is this a datetime object." This is a fragile type check. If `last_active` is a string (from JSON serialization), it will fail silently. Use a more explicit check or have the backend provide a boolean `is_active` field.

- **No pagination.** Same concern as conversations -- if there are many tenants, all are loaded at once.

- **No sort functionality.** The backend accepts a `sort` query parameter (line 166 of console.py: `sort_by = request.query_params.get("sort", "name")`) but it is never used -- agents are not sorted by `sort_by`. The template has no clickable sort headers either. This is dead code.

- **"Contacts" column provides no context.** A raw number like "47" does not tell the operator whether that is high or low. Consider showing it relative to plan limits if applicable.

**Severity:** Medium (status logic fragility), Low (rest)

---

### 7. Tenant Detail (`tenant_detail.html`)

**Strengths:**
- Action buttons (Edit, Test SMS, Deactivate) with confirmation dialog on destructive action.
- Profile section is comprehensive.
- Expandable configuration sections (style, autonomy, scheduling, raw JSON) use progressive disclosure well.
- Sidebar with cost, messages, errors, contacts, listings, and triggers -- rich context.
- TCPA consent revocation badge on contacts.

**Issues:**

- **No "reactivate" button.** Once deactivated, there is no UI to reactivate a tenant. The deactivate button is hidden when `current_status == 'deactivated'`, but no reactivate button replaces it. The operator would need to go to the edit page or use the database directly.

- **Raw JSON dump** in the "Raw Agent Record" details block uses `{{ agent }}`, which will render the Python dict's `repr()` -- not valid JSON. Use `{{ agent | tojson(indent=2) }}` for proper JSON formatting.

- **Contacts list truncated at 15 with no "show all" link.** If a tenant has 50 contacts, only 15 are shown with no indication that more exist. The section title shows the total count, but the user cannot see the rest.

- **Listings truncated at 10** with the same issue.

- **Test SMS success/failure feedback is lost.** The `tenant_test_sms` route (console.py line 290-306) catches exceptions and logs them, then redirects. The user gets no feedback on whether the test SMS succeeded or failed. The redirect to the detail page has no flash message mechanism.

- **No link from contacts to their conversation.** Clicking a contact name in the sidebar should navigate to the conversation detail, but contacts are not linked.

**Severity:** High (no reactivate), Medium (raw JSON, no feedback), Low (rest)

---

### 8. Tenant Edit (`tenant_edit.html`)

**Strengths:**
- Clean form layout constrained to 600px.
- CSRF protection. Error state handled.
- Cancel button links back to detail.
- Timezone options are user-friendly (showing city names).

**Issues:**

- **Missing timezone options.** Only 4 US timezones. No Hawaii, Alaska, or international options. If Calloway expands, this will need updating.

- **`style_profile.get('tone')` in template** (line 30) -- if `agent.style_profile` is a JSON string rather than a dict, `.get()` will fail. Ensure the backend deserializes this before passing to the template.

- **No field validation feedback beyond the error banner.** If validation fails, the error message is shown at the top, but the specific invalid field is not highlighted. The form is also not repopulated with submitted values -- it re-renders from the database, losing any changes the user made since last save.

- **Emoji setting from `tenant_new.html` is missing.** The new tenant form has an "Emoji Usage" field, but the edit form does not. This means the operator cannot change emoji settings after creation without a system prompt override.

- **No confirmation on save.** The form submits and redirects silently. A success flash message would confirm the save worked.

**Severity:** Medium (missing emoji field, validation UX), Low (rest)

---

### 9. Tenant New (`tenant_new.html`)

**Strengths:**
- Required fields marked with `*`. HTML5 `required` attribute enforced.
- E.164 format placeholder on phone fields.
- Style & Autonomy section is clear.

**Issues:**

- **Buffer Minutes is a text input, not a select or number input.** The onboarding wizard uses a `<select>` for this field (with predefined options), but the new tenant form uses a free-text `<input type="text">`. This inconsistency could lead to invalid values. Use `<input type="number" min="0" max="120">` or a select.

- **No duplicate detection.** There is no client-side or server-side warning if a Twilio number is already assigned to another tenant.

- **Form does not repopulate on validation error.** If creation fails (ValueError), the form re-renders but all fields are empty -- the user loses their input. The route (console.py line 210) passes only `error=str(e)` but not the submitted form data.

**Severity:** Medium (form data loss on error), Low (rest)

---

### 10. Onboarding Wizard (`onboard_wizard.html`)

**Strengths:**
- This is the best-designed screen in the entire console. Seven well-organized steps with:
  - Progress bar and step counter
  - Clear headings with contextual operator guidance ("Get this from the discovery call...")
  - Option cards with example text for tone selection -- brilliant for communicating the difference
  - Client-side validation before advancing
  - Dynamic listing and client entry management (add/remove)
  - Review summary on the final step
  - Dot navigation for jumping back to earlier steps
  - Smooth fade-in animation between steps
- Escalation preferences with checkboxes are well thought out
- After-hours mode options with clear descriptions

**Issues:**

- **BUG: Form data loss on server-side validation error.** If the POST to `/console/onboard` fails with a `ValueError`, the route re-renders `onboard_wizard.html` (console.py line 147). But all the JavaScript state (current step, dynamically added listings/clients) is lost. The user is dumped back to Step 1 with an error banner and must re-enter everything. This is a severe UX failure for a 7-step form.
  - **Recommended fix:** Either (a) submit via HTMX/fetch and show errors inline without a full page reload, or (b) pass all submitted form values back and pre-populate the fields.

- **`renumberEntries` function has a fragile selector** (line 653): the template literal `${type}` in a CSS selector works, but the union selector `.${type}-entry, .listing-entry, .client-entry` selects ALL entry types regardless of context. This could cause numbering bugs if both containers are present on the page (which they are).

- **No "Save as Draft" capability.** A 7-step wizard with no way to save partial progress is risky. If the browser tab closes, all data is lost.

- **Wizard dots only allow backward navigation** (line 526-534: `if (step < currentStep)`). Forward jumps are blocked, which is correct for validation, but a completed step should allow re-visiting via dots without re-validation.

- **Step 5 (Listings) and Step 6 (Clients) are optional but positioned before the required Step 7 (Channel Setup).** Consider making the required channel config earlier in the flow, or clearly marking Steps 5-6 as "Optional" in the step label.

- **XSS risk in review summary.** The `buildReviewSummary()` function (line 662) uses `.innerHTML` to render user input values directly. If a user enters HTML/script in a text field, it will be rendered. Use `textContent` for individual values or sanitize inputs.

**Severity:** High (data loss on error, XSS), Medium (no draft save), Low (rest)

---

### 11. Onboard Success (`onboard_success.html`)

**Strengths:**
- Clear success confirmation with checkmark.
- Build checklist with done/pending states.
- Next steps as an ordered list with specific, actionable instructions.
- Three navigation options (view tenant, onboard another, back to tenants).

**Issues:**

- **The checkmark uses a raw HTML entity** (`&#10003;`) inside a div with `font-size: 48px`. This renders inconsistently across browsers/platforms. A proper SVG icon or an icon font would be more reliable.

- **No link to the Harness** in next steps. Step 3 says "Send a test message" and points to the tenant detail page, but the Harness is the dedicated tool for conversation simulation.

**Severity:** Low

---

### 12. Triggers (`triggers.html`)

**Strengths:**
- Filters for status and agent.
- Color-coded status badges with ARIA labels.
- Inline action buttons (Retry, Fire Now, Cancel) with confirmation dialogs on destructive actions.
- CSRF tokens on all action forms.

**Issues:**

- **No trigger detail view.** Clicking a trigger row does nothing. There is no expandable detail or link to see the full trigger payload, associated contact, or message preview. The operator must infer context from the type, agent, and scheduled time alone.

- **No pagination.** Same concern as other list views.

- **"Fire Now" sends a real message with only a `confirm()` dialog.** This is a high-risk action (it sends an actual SMS to a real person). Consider a two-step confirmation or at least showing who will receive the message in the confirmation dialog.

- **No bulk actions.** If there are many error triggers, the operator must retry them one by one. A "Retry All" or checkbox selection would improve efficiency.

- **No indication of which contact the trigger targets.** The table shows agent, type, and schedule, but not the recipient. Knowing who will receive the follow-up is critical for the "Fire Now" decision.

**Severity:** High (no contact info on triggers), Medium (no trigger detail), Low (rest)

---

### 13. Costs (`costs.html`)

**Strengths:**
- Summary cards with key metrics.
- Daily cost bar chart is a nice visual.
- Model tier breakdown table.
- Per-agent cost table with red highlighting for costs > $15.
- Voice minutes and cost-per-message are useful unit economics metrics.

**Issues:**

- **BUG: Bar chart cost tooltip is potentially inconsistent.** Line 37: `title="{{ d.date }}: ${{ (d.cost / 100)|round(2) }}"` divides `d.cost` by 100, implying costs are stored in cents. But the summary card (line 7) displays `summary.total_cost_dollars` directly as a dollar value. If `d.cost` is in cents and the summary is pre-converted to dollars, this is correct. But if `d.cost` is already in dollars, the tooltip will show 1/100th of the actual cost. Verify the units are consistent.

- **Bar chart has no y-axis labels or gridlines.** The bars are relative to max, but there is no scale reference. The user must hover each bar to see the value. Add a y-axis or at least display the max value.

- **No date range selector.** Everything is hardcoded to 30 days. The operator cannot view costs for a different period.

- **Per-agent table lacks sorting.** The operator might want to sort by cost to find the most expensive tenants.

- **No export/download capability.** Cost data is often needed for reporting or bookkeeping.

**Severity:** Medium (chart cost units), Low (rest)

---

### 14. Health (`health.html`)

**Strengths:**
- Service connectivity cards with color-coded dots.
- Pipeline performance metrics (avg, p50, p95).
- Manual scan action with agent selector and confirmation.
- Auto-refresh every 30s via HTMX.
- Accessibility: `role="status"` and `aria-label` on service cards.

**Issues:**

- **HTMX self-refresh is wasteful.** The wrapper div (line 3) fetches the full page via `hx-get="/console/health"` and extracts just `.content`. A dedicated HTMX partial endpoint (like the dashboard uses for the activity feed) would be more efficient and avoid re-rendering the entire base layout on each refresh.

- **Potential duplicate status text.** The CSS `status-dot::after` pseudo-element (line 433 of style.css) renders `content: attr(data-label)` after the dot, while the template also renders a separate `.status-label` span. This could show the status word twice.

- **No historical health data.** The page shows current status only. There is no uptime history, no incident log, and no latency trends over time.

- **Manual scan gives no feedback.** Like the Test SMS button, the `run_manual_scan` route redirects without any success/failure indication.

- **Pipeline latency values lack context.** Numbers like "1200ms" mean nothing without a benchmark. Consider color-coding: green if under 2s, yellow if 2-5s, red if over 5s.

**Severity:** Medium (duplicate status text, no feedback on scan), Low (rest)

---

### 15. Errors (`errors.html`)

**Strengths:**
- Separate sections for tool errors and application errors.
- Expandable error details with input/output JSON and stack traces.
- Severity badges (error/warning).
- Filter by agent.
- Empty state handled.

**Issues:**

- **No time range filter.** The backend returns the most recent 100 errors, but the operator cannot filter by time range (today, last 24h, last 7 days).

- **No error count summary.** Unlike the dashboard (which shows "Errors 24h"), the errors page itself has no summary count. Adding "Showing X tool errors and Y app errors" would provide context.

- **No "mark as resolved" or "acknowledge" action.** Errors persist with no way to dismiss or track resolution. Over time, the list will be dominated by stale errors that have already been investigated.

- **No link from an error to its conversation.** If a tool error occurred during a conversation, the operator should be able to click through to see the conversation context.

**Severity:** Medium (no time filter, no resolution tracking), Low (rest)

---

### 16. Billing (`billing.html`)

**Strengths:**
- Plan tier cards with feature lists and pricing.
- Subscription table with rich status information.
- Message usage progress bars with color thresholds (green/yellow/red).
- Plan change dropdown with cancel option.
- Revenue summary cards (MRR, active subscribers, trials, past due).
- Empty state with guidance.

**Issues:**

- **The "Change Plan" dropdown uses `<details>` for a popover** (lines 67-85). This works but has UX issues:
  - It does not close when clicking outside (native `<details>` behavior).
  - Multiple rows can have their dropdowns open simultaneously.
  - The dropdown can overflow the table on small screens.
  - Consider replacing with a modal or a proper dropdown component.

- **No indication of plan change impact.** When changing from one plan to another, there is no preview of what changes (price difference, feature differences, proration).

- **Cancel subscription has no "undo" or reactivation path.** The confirmation dialog says "Cancel at end of billing period" but there is no way to un-cancel from this UI.

- **Revenue summary uses complex Jinja2 expressions** (lines 107-126) that could break if the data shape changes. These calculations should ideally be done in the backend and passed as template variables.

**Severity:** Medium (details-as-popover UX), Low (rest)

---

### 17. Manual (`manual.html`)

**Strengths:**
- Comprehensive documentation of every screen, column, and button.
- Table of contents with anchor links.
- Styled consistently with the console design.
- Helpful tips section.

**Issues:**

- **Missing documentation for Billing and Onboard Wizard.** The manual covers Dashboard, Tenants, Conversations, Triggers, Errors, Costs, Health, and Harness. The Billing page and the Onboard Wizard are not documented. These are newer features that need manual entries.

- **Sidebar nav table in the manual does not list "Billing" or "Onboard Agent."** The sidebar description table (lines 50-63) lists 10 items but omits these two nav entries that exist in the actual sidebar.

- **No search functionality within the manual.** For a long reference document, Ctrl+F works, but an in-page search would be more accessible.

**Severity:** Medium (missing documentation for Billing and Onboard)

---

### 18. Activity Feed Partial (`partials/activity_feed.html`)

**Strengths:**
- Clean feed item rendering.
- Color-coded sender badges (green inbound, blue AI, gray system).
- Contact name appended when available.
- Empty state handled.

**Issues:**

- **No link to the conversation.** Feed items show a message preview but do not link to the full conversation. The operator sees activity but cannot click through to investigate.

- **`event.ai_generated` is used** instead of `event.sender_type == 'ai'`. This is inconsistent with `conversation_detail.html` which checks `m.sender_type`. If the backend uses different field names for the same concept, this could be a source of bugs.

**Severity:** Medium (no links to conversations)

---

## Cross-Cutting Issues

### A. No Flash Message / Toast System

Multiple actions (Test SMS, Deactivate, Run Scan, plan change, trigger retry/cancel/fire) redirect after a POST with no user feedback. The operator clicks a button, the page reloads, and nothing visually confirms what happened. This is the most impactful systemic UX gap.

**Recommendation:** Implement a simple flash message system. FastAPI/Starlette supports session-based flash messages, or use a query parameter approach (`?msg=test_sms_sent`) with conditional rendering in `base.html`.

**Severity:** High

### B. No Pagination Anywhere

Conversations (100 limit), triggers (no limit specified in template), errors (100 limit), and tenants (no limit) all load everything at once with no pagination. As the system scales, this will cause performance issues and make it impossible to find older records.

**Recommendation:** Add cursor-based or offset pagination to all list views. Show "Showing 1-100 of 342" with Next/Previous controls.

**Severity:** High

### C. No Confirmation Feedback Pattern

Related to (A), there is no consistent pattern for post-action confirmation. Some actions use `confirm()` dialogs before execution (good), but none show confirmation after execution.

**Severity:** High

### D. Keyboard Navigation

- The sidebar nav items are `<a>` tags (focusable by default) -- good.
- Filter forms have standard inputs -- good.
- The onboarding wizard's step dots use `onclick` on `<span>` elements -- **not keyboard accessible**. These should be `<button>` elements.
- The mobile menu toggle is a `<button>` -- good.
- `<details>` elements are natively keyboard-accessible -- good.

**Severity:** Medium (wizard dots)

### E. Color Contrast

The dark theme uses `--text-muted: #94a3b8` on `--bg: #0f172a`. The contrast ratio is approximately 5.6:1, which passes WCAG AA for normal text. The primary text `--text: #e2e8f0` on `--bg` is approximately 12.4:1 -- excellent. Badge text colors on their semi-transparent backgrounds effectively pass AA as well.

Overall, color contrast is adequate. The system does well by not relying solely on color (text labels accompany colored dots on the health page).

**Severity:** Low (passes WCAG AA)

### F. Missing `<label for="">` Associations

Several filter forms have `<label>` elements without `for` attributes (conversations.html lines 5, 8; errors.html line 5). Triggers.html correctly uses `for` attributes. This inconsistency means some form controls are not programmatically associated with their labels for screen readers.

**Severity:** Medium

### G. Tables Not Responsive

On mobile (< 768px), the CSS reduces font size and padding for tables, but wide tables (conversations with 7 columns, triggers with 8 columns, tenants with 9 columns) will still overflow horizontally. Consider wrapping tables in `overflow-x: auto` containers.

**Severity:** Medium

### H. Pervasive Inline Styles

Both the tenant detail page and the billing page make heavy use of inline `style=""` attributes for layout, spacing, and sizing. This defeats the purpose of a CSS system, makes theming impossible, and creates maintenance debt. A sampling from `tenant_detail.html` alone: 15+ inline style attributes for layout that should be CSS classes.

**Severity:** Medium

---

## Template Bug Summary

| # | File | Bug | Severity |
|---|------|-----|----------|
| B1 | `conversation_detail.html` | Tool execution interleaving logic uses inner loop's `loop.index` instead of outer loop's, causing incorrect placement of tool executions between messages | High |
| B2 | `onboard_wizard.html` | Full form data lost on server-side validation error -- user dumped back to Step 1 with empty fields | High |
| B3 | `onboard_wizard.html` | `buildReviewSummary()` uses `.innerHTML` with unsanitized user input -- XSS risk | High |
| B4 | `tenant_detail.html` | `{{ agent }}` renders Python dict `repr()`, not JSON. Use `{{ agent \| tojson(indent=2) }}` | Medium |
| B5 | `tenants.html` | `a.last_active.isoformat is defined` is a fragile type check for datetime detection | Medium |
| B6 | `costs.html` | Bar chart tooltip divides `d.cost` by 100; verify cost units are consistent with summary cards | Medium |
| B7 | `tenant_new.html` | Form fields not repopulated on validation error -- user loses all input | Medium |
| B8 | `health.html` | Potential duplicate status text from CSS `::after` pseudo-element and `.status-label` span | Medium |
| B9 | `console.py` | `sort_by` query param is captured on line 166 but never used for sorting | Low |
| B10 | `manual.html` | Billing and Onboard Wizard sections missing from documentation | Medium |

---

## Prioritized Recommendations

### P0 -- Fix Before Next Deploy

1. **Fix the tool execution interleaving bug** in `conversation_detail.html`. Pre-merge messages and tool executions into a single chronological list in the backend and pass it as a flat list to the template. This eliminates the Jinja2 loop scoping issue entirely.

2. **Fix form data loss** on validation errors in `onboard_wizard.html` and `tenant_new.html`. At minimum, pass submitted form data back to the template for re-population. For the wizard, consider submitting via `fetch()` and showing errors inline without a full page reload.

3. **Fix XSS in `buildReviewSummary()`**. Replace `.innerHTML` assignments with DOM construction using `.textContent` for user-provided values.

4. **Add a flash message system** to `base.html` for post-action feedback (Test SMS, Deactivate, Run Scan, trigger actions, plan changes). Every mutating action should confirm success or report failure to the operator.

5. **Add a reactivate button** to `tenant_detail.html` when `current_status == 'deactivated'`.

### P1 -- Next Sprint

6. **Add pagination** to conversations, triggers, errors, and tenants list views. Start with simple offset-based pagination.

7. **Add links from dashboard pulse cards** to their detail pages (errors to `/console/errors`, costs to `/console/costs`, messages to `/console/conversations`).

8. **Add links from activity feed items** to their conversation detail pages.

9. **Show contact/recipient info on triggers.** Add a "Contact" column to the triggers table so the operator knows who will receive the message before clicking "Fire Now."

10. **Fix `{{ agent }}` raw JSON rendering** in tenant detail. Use `{{ agent | tojson(indent=2) }}`.

11. **Add Billing and Onboard Wizard documentation** to `manual.html`.

12. **Add `for` attributes** to all `<label>` elements in filter forms (conversations, errors).

### P2 -- Improvement Backlog

13. **Make wizard step dots keyboard-accessible** by using `<button>` elements instead of `<span>` with `onclick`.

14. **Wrap tables in `overflow-x: auto` containers** for mobile responsiveness.

15. **Replace the `<details>` popover** in `billing.html` with a proper dropdown or modal for plan changes.

16. **Add channel label mapping** in conversations: display "Voice" instead of "vapi", capitalize all channel names.

17. **Reorder sidebar navigation** to put frequently-used items first and infrequent actions (Onboard, Harness, Manual) lower.

18. **Add an emoji toggle** to `tenant_edit.html` to match the field available in `tenant_new.html` and the onboarding wizard.

19. **Add sorting to tables** (tenants by name/status/errors, costs by cost/messages, conversations by time).

20. **Add a time range filter** to the errors page.

21. **Extract inline styles to CSS classes** across all templates. Create reusable layout classes (`.action-bar`, `.table-container`, `.sidebar-stats`, etc.).

22. **Resolve duplicate status text** on the health page -- remove either the `::after` pseudo-element or the `.status-label` span.

23. **Add auto-scroll to bottom** on conversation detail page load, so the operator sees the most recent messages first.

24. **Add message delivery status indicators** to conversation detail for AI-generated messages (sent, draft, failed).

25. **Add a "mark as resolved" action** on errors, or at minimum a way to filter out previously-investigated errors.

---

## Design System Assessment

The CSS design system is clean and compact (457 lines). Key strengths:

- **Consistent spacing and sizing.** Cards, sections, and form groups use predictable padding/margins.
- **Badge system is versatile.** Five color variants (green, yellow, red, blue, gray) cover all semantic needs.
- **Dark theme is well-executed.** The three-tier background hierarchy (`--bg`, `--bg-card`, `--bg-hover`) creates clear visual layers.
- **Typography is minimal but effective.** System font stack, 14px base, 1.5 line-height.
- **Mobile breakpoint at 768px** handles the most critical layout changes (sidebar, grid, form rows).
- **Onboarding wizard components** (option cards, progress bar, step dots) are well-crafted and could be reused elsewhere.

Potential additions to the design system:
- A `.table-container { overflow-x: auto; }` wrapper class.
- A `.toast` or `.flash-message` component for post-action feedback.
- A `.loading-skeleton` class for placeholder content during HTMX loads.
- A `.breadcrumb` component for detail page navigation.
- A `.action-bar` class for the top button rows used in tenant detail and other pages.
- Focus-visible styles for all interactive elements beyond form inputs.

---

*End of review. Questions or clarifications -- reach out to @design.*
