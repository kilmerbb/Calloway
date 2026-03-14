# UX Benchmarks: Best-in-Class SaaS Admin Panels & Dashboards

**Research Date:** 2026-03-14
**Analyst:** Oracle (Research)
**Purpose:** Inform Calloway console hardening with consumer-grade UX patterns

---

## 1. Executive Summary

After analyzing the UX of six leading SaaS products (Vercel, Linear, Stripe, Notion, Intercom, HubSpot), dozens of real estate CRMs, and current design system literature, the following themes emerge:

1. **Speed is the killer feature.** The products users love most (Linear, Vercel) feel instantaneous. Every click produces immediate visual feedback. For HTMX, this means aggressive use of swap transitions, skeleton screens, and optimistic UI patterns.

2. **Information density must be earned.** Stripe packs enormous data into small spaces, but only because the hierarchy is flawless -- 6 distinct type sizes, semantic color, and progressive disclosure. Calloway should start sparse and let operators drill down.

3. **Command palettes (Cmd+K) are table stakes.** Linear, Notion, Vercel, Slack, and Figma all ship them. For an operator tool, a Cmd+K palette that searches tenants, conversations, triggers, and settings would be transformative.

4. **Empty states are onboarding moments.** Every blank table, zero-result search, or fresh tenant should show an illustration, explanation, and a single clear CTA. This is the single cheapest way to make the console feel "finished."

5. **Keyboard shortcuts separate good from great.** Linear proves that a keyboard-first interface can feel 10x faster. Even a handful of shortcuts (J/K navigation, R to reply, E to resolve) dramatically elevate the operator experience.

6. **Dark mode signals maturity.** Every benchmark product ships it. CSS custom properties make it straightforward to implement with HTMX/Jinja2 -- no framework required.

7. **Micro-interactions signal quality.** Button hover states, toast confirmations, smooth transitions on swap, and loading shimmer effects communicate "this product is well-made" at a subconscious level.

---

## 2. Per-Product Analysis: What to Steal

### 2.1 Vercel Dashboard

**Why it is excellent:** Developer-centric but consumer-grade polish. Performance IS the UX -- they reduced First Meaningful Paint by 1.2s during their redesign. Every state is designed.

**Patterns to adopt:**
- **Browser tab integration:** Reflect page status in the tab icon/title. Calloway could show unread conversation count or active trigger count in the browser tab.
- **State completeness:** Every view has designed states for empty, sparse, dense, loading, and error. This is the single most impactful practice for polish.
- **Tabular numbers:** Use `font-variant-numeric: tabular-nums` wherever numbers appear in tables (costs, conversation counts, trigger counts). Numbers that shift width on update look amateurish.
- **Locale-aware formatting:** Dates, times, and currencies formatted per user locale.
- **Resilient layouts:** Designed to handle user-generated content of any length without breaking.
- **Nested border radii:** Child radius should be less than or equal to parent radius with concentric curves. Small detail, big polish signal.
- **Layered shadows:** At least two shadow layers (ambient + direct) for depth.
- **Non-breaking spaces:** Keep units together (`10 MB`, keyboard shortcuts like `Cmd + K`) with `&nbsp;`.

**Reference:** [Vercel Web Interface Guidelines](https://vercel.com/design/guidelines) | [Dashboard Redesign Blog](https://vercel.com/blog/dashboard-redesign) | [Performance Blog](https://vercel.com/blog/how-we-made-the-vercel-dashboard-twice-as-fast)

---

### 2.2 Linear

**Why it is excellent:** The fastest-feeling web application in production. Keyboard-first, minimal chrome, every interaction is sub-100ms. Feels like a native app.

**Patterns to adopt:**
- **Command palette (Cmd+K):** Every action accessible via search. The gold standard. For Calloway: search tenants by name/phone, jump to conversations, navigate to settings.
- **Keyboard shortcuts with discovery:** `C` to create, `G then I` for "Go to Inbox." Show shortcuts in context menus and tooltips so users learn them naturally.
- **Searchable shortcut help (`?`):** A modal listing all shortcuts, filterable by search.
- **Safe triangle for submenus:** When hovering to a submenu, Linear draws an invisible triangle between cursor and submenu so it does not accidentally close. This kind of invisible detail makes an app feel "right."
- **Perceptually uniform color themes:** Linear uses LCH color space instead of HSL for generating themes. If Calloway ships dark mode, LCH produces more consistent results.
- **Minimal chrome:** No busy sidebars or unnecessary ornamentation. Content takes center stage.
- **Contextual right-click menus:** Right-click on any entity to see all available actions plus their keyboard shortcuts.

**Reference:** [Linear UI Redesign](https://linear.app/now/how-we-redesigned-the-linear-ui) | [Invisible Details](https://medium.com/linear-app/invisible-details-2ca718b41a44)

---

### 2.3 Stripe Dashboard

**Why it is excellent:** Masters information density without feeling overwhelming. 6 type sizes and weights create scannable hierarchy. Semantic color (red only for things that need fixing NOW).

**Patterns to adopt:**
- **Sparklines next to metrics:** Tiny inline trend indicators next to numbers (MRR, conversation volume, cost per day). Show direction without requiring a full chart.
- **Calm technology philosophy:** Powerful functionality that does not demand attention. The interface recedes; the data speaks.
- **Minimum viable information:** Every view asks "What is the absolute minimum information needed at this step?" and shows only that, with drill-down available.
- **Semantic color discipline:** Blue for primary actions, red ONLY for errors/urgent items, green for success. Never decorative color.
- **Global search spanning all entity types:** Search across tenants, conversations, triggers, contacts -- all from one input.
- **Contextual sidebar apps:** Detail panels that slide in from the right without losing the list context. Perfect for Calloway's conversation or contact detail views.

**Reference:** [Stripe Apps Design Patterns](https://docs.stripe.com/stripe-apps/patterns) | [Stripe Dashboard UI (SaaSFrame)](https://www.saasframe.io/examples/stripe-payments-dashboard)

---

### 2.4 Notion

**Why it is excellent:** Makes complex software feel friendly and approachable. Block-based flexibility with clean defaults. Setting a new standard for how software "should feel."

**Patterns to adopt:**
- **Slash commands (`/`):** Type `/` in any text input to get a contextual command menu. For Calloway, this could work in the conversation test harness or message composer.
- **Drag-and-drop with consistent affordances:** The six-dot grip icon universally signals "draggable." Consistent cursor changes on hover.
- **Progressive disclosure via hover:** Additional controls appear only on hover, keeping the default view clean. Always provide a non-hover alternative for touch.
- **Breadcrumb navigation:** Visual hierarchy of where you are within nested pages/views. Essential for a multi-section admin console.
- **Sidebar accordion navigation:** Collapsible sections in the left nav that let operators organize their workspace.
- **Preview on hover:** Hover over a link to see a preview card without navigating away. Useful for tenant names, contact references, or conversation links.

**Reference:** [Notion UI Breakdown (Medium)](https://medium.com/@yolu.x0918/a-breakdown-of-notion-how-ui-design-pattern-facilitates-autonomy-cleanness-and-organization-84f918e1fa48) | [Notion UX Review (Adam Fard)](https://adamfard.com/blog/notion-ux-review)

---

### 2.5 Intercom

**Why it is excellent:** The closest analog to Calloway's use case -- messaging, conversations, contact management. Their 2025 IA redesign solved the exact "maze of features" problem admin panels face.

**Patterns to adopt:**
- **Unified inbox with keyboard navigation:** J/K to navigate conversations, R to reply, E to resolve. Filter by unassigned, mine, tagged. This is directly applicable to Calloway's conversation views.
- **Consistent secondary navigation:** Every section (Inbox, Contacts, Knowledge, Automation) follows identical visual patterns -- minimalist folder structure, pinning/unpinning.
- **Merged related sections:** When users toggle between related areas (e.g., Knowledge Hub and Help Center), merge them into one destination. Calloway should avoid splitting related concepts.
- **Uniform iconography and spacing:** Consistent across all sections so users can predict where to find things.
- **AI-suggested responses with edit tracking:** When AI suggests a response and the operator edits it, track the change. Directly applicable to Calloway's supervised mode.
- **Real-time dashboards with filters:** First response time, resolution time, CSAT -- filterable by agent, team, time period.

**Reference:** [Intercom IA Redesign](https://www.intercom.com/blog/designing-for-clarity-restructuring-intercoms-information-architecture/) | [Intercom Interaction Design Fundamentals](https://www.intercom.com/blog/fundamentals-good-interaction-design/) | [Intercom Design System](https://intercom.design/)

---

### 2.6 HubSpot CRM

**Why it is excellent:** Contact and deal management at scale with role-based experience design. Customizable dashboards that adapt to the user's actual job.

**Patterns to adopt:**
- **Role-based default views:** Different users see different default dashboards. For Calloway, a super-admin might see system health + all tenants, while a tenant operator might see their own conversations + triggers.
- **Custom views and smart filters:** Save filter combinations as named views (e.g., "Hot Leads," "Overdue Follow-ups"). For Calloway: "Pending Approval," "Failed Triggers," "High-Cost Tenants."
- **Contact record layout with activity timeline:** A unified view of a contact showing all interactions chronologically. Directly applicable to Calloway's contact detail pages.
- **Drag-and-drop pipeline visualization:** Visual deal/lead stages. Could inspire a trigger lifecycle or conversation status visualization.
- **Inline task management:** Create and complete tasks directly within the contact or deal record without navigating away.

**Reference:** [HubSpot CRM UX (Abduzeedo)](https://abduzeedo.com/hubspot-crms-enhanced-uiux-design-saas/) | [HubSpot UI Extensions 2025](https://developers.hubspot.com/blog/app-cards-updates-spring-spotlight-2025)

---

## 3. Pattern Library

### 3.1 Navigation

| Pattern | Description | Achievable with HTMX? | Priority |
|---------|-------------|----------------------|----------|
| **Command palette (Cmd+K)** | Global search + action launcher overlay | Yes (Alpine.js + HTMX for search results) | P0 |
| **Sidebar accordion** | Collapsible nav sections with active indicators | Yes (pure CSS/HTMX) | P0 |
| **Breadcrumbs** | Show hierarchy path on detail pages | Yes (Jinja2 template) | P1 |
| **Keyboard shortcuts** | J/K nav, R reply, E resolve, ? help | Yes (vanilla JS event listeners) | P1 |
| **Tab title/favicon status** | Show counts or status in browser tab | Yes (vanilla JS) | P2 |

### 3.2 Tables & Lists

| Pattern | Description | Achievable with HTMX? | Priority |
|---------|-------------|----------------------|----------|
| **Fixed column headers** | Headers stay visible on scroll | Yes (CSS `position: sticky`) | P0 |
| **Sort indicators** | Chevron on sortable column headers | Yes (HTMX `hx-get` with sort param) | P0 |
| **Filter chips/tags** | Active filters shown as removable chips | Yes (HTMX partial swap) | P1 |
| **Saved/named views** | Save filter+sort combos as presets | Yes (server-side, HTMX trigger) | P2 |
| **Hover row actions** | Edit/delete buttons appear on row hover | Yes (CSS `:hover` + fallback menu) | P1 |
| **Pagination with page size selector** | 25/50/100 rows with page nav | Yes (HTMX `hx-get`) | P0 |
| **Empty table state** | Illustration + explanation + CTA when no rows | Yes (Jinja2 conditional) | P0 |
| **Bulk actions** | Select multiple rows, apply action | Yes (Alpine.js + HTMX) | P2 |
| **Tabular numbers** | `font-variant-numeric: tabular-nums` for numeric columns | Yes (CSS) | P0 |

### 3.3 Detail Pages

| Pattern | Description | Achievable with HTMX? | Priority |
|---------|-------------|----------------------|----------|
| **Split view (list + detail)** | Click a row to load detail in adjacent panel | Yes (HTMX `hx-target`) | P1 |
| **Activity timeline** | Chronological feed of all interactions | Yes (HTMX infinite scroll or pagination) | P0 |
| **Tabbed sections** | Tabs for different data groups within a detail page | Yes (HTMX tab swap) | P1 |
| **Inline editing** | Click a field to edit in-place | Yes (HTMX `hx-swap`) | P2 |
| **Slide-over panel** | Detail panel slides in from right, list remains visible | Yes (CSS transform + HTMX) | P1 |

### 3.4 Loading States

| Pattern | Description | Achievable with HTMX? | Priority |
|---------|-------------|----------------------|----------|
| **Skeleton screens** | Gray placeholder shapes matching content layout | Yes (CSS animation, show during `htmx-request`) | P0 |
| **Shimmer animation** | Gradient sweep across skeleton elements | Yes (CSS `@keyframes`) | P1 |
| **Request indicator** | Subtle progress bar or spinner during HTMX requests | Yes (`htmx-indicator` class) | P0 |
| **Optimistic UI** | Show the expected result immediately, roll back on error | Partial (requires careful HTMX + JS) | P2 |

**CSS for skeleton screens:**
```css
.skeleton {
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
/* Show skeleton only when container is empty (loading) */
.skeleton-container:empty::before {
  content: '';
  display: block;
  /* dimensions matching expected content */
}
/* Respect reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
```

### 3.5 Empty States

| Pattern | Description | Priority |
|---------|-------------|----------|
| **First-use empty state** | "No tenants yet. Add your first agent to get started." + CTA button | P0 |
| **No-results empty state** | "No conversations match your filters." + "Clear filters" link | P0 |
| **Success/cleared empty state** | "All caught up! No pending approvals." (celebratory tone) | P1 |
| **Error empty state** | "Something went wrong loading triggers." + "Retry" button | P0 |

**Structure for every empty state:**
1. Illustration or icon (optional but high-polish signal)
2. Headline explaining the state
3. Secondary text with guidance
4. Action button (when applicable)

### 3.6 Action Feedback

| Pattern | Description | Achievable with HTMX? | Priority |
|---------|-------------|----------------------|----------|
| **Toast notifications** | Brief confirmation of completed action (bottom-right) | Yes (HTMX OOB swap + CSS animation) | P0 |
| **Inline validation** | Real-time field validation as user types | Yes (HTMX `hx-trigger="keyup changed delay:500ms"`) | P1 |
| **Confirmation dialogs** | Modal for destructive actions (delete tenant, revoke consent) | Yes (Alpine.js modal or HTMX) | P0 |
| **Undo via toast** | "Trigger deleted. Undo" toast with time-limited action | Yes (HTMX + JS timer) | P2 |

**Toast implementation for HTMX:**
- Keep a `<div id="toast-container">` in the base template
- Use HTMX out-of-band swaps (`hx-swap-oob="beforeend:#toast-container"`) to inject toasts from any response
- Auto-dismiss after 4 seconds via CSS animation + JS `setTimeout`
- Pause countdown on hover (like Discord)
- Limit to 3 words max for the message; use inline feedback for anything requiring detail

### 3.7 Dark Mode

| Pattern | Description | Priority |
|---------|-------------|----------|
| **CSS custom properties theming** | Define all colors as `--color-*` variables on `:root` | P1 |
| **`data-theme` attribute toggle** | `<html data-theme="dark">` swaps variable values | P1 |
| **`prefers-color-scheme` detection** | Auto-match system preference on first visit | P1 |
| **Persist preference** | Save to `localStorage`, apply before paint to prevent FOUC | P1 |
| **`light-dark()` CSS function** | Modern CSS function for simpler theming (2025 browser support) | P2 |

**Minimal implementation approach:**
```css
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f5f5;
  --text-primary: #111111;
  --text-secondary: #666666;
  --border: #e0e0e0;
  --accent: #0070f3;
}
[data-theme="dark"] {
  --bg-primary: #0a0a0a;
  --bg-secondary: #1a1a1a;
  --text-primary: #ededed;
  --text-secondary: #a0a0a0;
  --border: #2a2a2a;
  --accent: #3291ff;
}
```

### 3.8 HTMX-Specific Patterns

| Pattern | Description | Priority |
|---------|-------------|----------|
| **Swap transitions** | CSS transitions on `htmx-settling` class for smooth content replacement | P0 |
| **View Transitions API** | Use `hx-swap="transition:true"` for page-level transitions (modern browsers) | P2 |
| **`hx-boost`** | Add to navigation links for AJAX page loads without full reload | P0 |
| **Request indicators** | Show spinner/skeleton during `htmx-request` class | P0 |
| **Active search** | `hx-trigger="keyup changed delay:300ms"` on search inputs | P1 |
| **Infinite scroll** | `hx-trigger="revealed"` on a sentinel element for timeline views | P2 |
| **Click-to-load** | "Load more" button that appends content via `hx-swap="beforeend"` | P1 |
| **Out-of-band swaps** | Update multiple page sections from a single response (toasts, counters, badges) | P0 |

**Smooth swap transition CSS:**
```css
.htmx-settling {
  opacity: 0;
}
.htmx-settled {
  transition: opacity 200ms ease-in;
  opacity: 1;
}
```

---

## 4. Specific Recommendations for Calloway's Console

### Tier 1: Quick Wins (1-2 days each, massive polish impact)

1. **Design all empty states.** Audit every table, list, and section. Add headline + explanation + CTA for each empty condition. This is the single fastest path from "developer tool" to "consumer-grade."

2. **Add skeleton loading screens.** Replace blank/spinner states with shimmer skeletons that match the layout of the content being loaded. Use the `htmx-request` class to toggle visibility.

3. **Implement toast notifications.** Use HTMX out-of-band swaps to inject toast confirmations for every mutation (create, update, delete, approve, reject). Keep messages to 3 words or fewer.

4. **Add `font-variant-numeric: tabular-nums` to all numeric displays.** Cost columns, conversation counts, trigger counts -- numbers should not shift width.

5. **Sticky table headers.** `position: sticky; top: 0;` on all `<thead>` elements. Trivial CSS change, huge usability improvement for long tables.

6. **Smooth HTMX swap transitions.** Add the settling/settled CSS transitions (shown above) globally. Every content swap will feel intentional rather than jarring.

7. **`hx-boost` on all navigation links.** Eliminates full page reloads for nav clicks. Instant SPA-like feel with zero JS framework.

### Tier 2: High Impact (3-5 days each)

8. **Command palette (Cmd+K).** Build a modal overlay with a search input. On keystroke, HTMX-fetch matching tenants, conversations, triggers, and settings. Use Alpine.js for the modal toggle and keyboard binding. This is the single feature most likely to impress investors.

9. **Keyboard shortcuts.** Start with: `?` for help, `G then T` for Go to Tenants, `G then C` for Conversations, `J/K` for row navigation. Show shortcuts in tooltips and context menus.

10. **Dark mode.** Refactor all colors to CSS custom properties. Add a `data-theme` toggle with `localStorage` persistence. Detect `prefers-color-scheme` for first-time default.

11. **Conversation detail redesign.** Adopt Intercom's inbox pattern: list on left, conversation thread on right. Keyboard navigable. Show contact context (name, phone, consent status, recent activity) in a collapsible right sidebar.

12. **Contact activity timeline.** Chronological feed showing all messages, triggers, status changes, and notes for a contact. This is what real estate CRMs (Follow Up Boss, HubSpot) do well.

### Tier 3: Differentiation (1-2 weeks each)

13. **Saved views / smart filters.** Let operators save filter combinations ("Pending Approvals," "High-Cost Tenants," "Failed Triggers") as named views in the sidebar.

14. **Inline editing on detail pages.** Click a tenant name or config value to edit in-place. HTMX makes this straightforward with targeted swaps.

15. **Split-view for tables.** Click a row to load its detail in a slide-over panel without losing the list context. Stripe and Intercom both use this pattern.

16. **Real-time updates via SSE.** Use Server-Sent Events with HTMX's SSE extension to push conversation updates, trigger status changes, and cost alerts without polling.

17. **Micro-interactions audit.** Add hover states to all buttons, focus rings to all inputs, transition on all color changes, and subtle scale on click for action buttons. Each takes minutes; collectively they transform the feel.

---

## 5. Real Estate CRM-Specific Patterns

### Follow Up Boss
- **Lead inbox redesign:** High-density interface redesigned for clarity -- directly relevant to Calloway's conversation management
- **Smart lists:** Dynamically updating lists based on client activity ("Call today," "New leads," "Hot prospects")
- **Drag-and-drop contact profiles:** Agents customize what fields appear and in what order
- **Integrated communication:** Email, text, and call history in one timeline per contact

**Reference:** [Follow Up Boss CRM Design (SaaS Designer)](https://saasdesigner.com/fub/)

### kvCORE
- **Mobile-first architecture:** Dedicated iOS/Android apps for agents in the field (100K+ downloads)
- **AI behavioral automation:** Identifies hottest prospects from behavior signals
- **Mobile dialer integration:** Make calls, access contacts, manage tasks on the go
- **Limitation:** Steep learning curve, app glitches -- shows that mobile polish matters as much as desktop

**Reference:** [kvCORE Reviews 2025](https://www.selecthub.com/p/crm-for-commercial-real-estate/kvcore/)

### Key Takeaway for Calloway
Real estate agents live on their phones. While Calloway's console is an operator tool (not agent-facing), if it ever becomes agent-visible:
- Touch-friendly tap targets (minimum 44px)
- Responsive tables that collapse gracefully on mobile
- Sticky action bars at the bottom of the screen on mobile
- One-tap actions for common tasks (approve, reject, call)

For the operator console today, ensure the admin panel is at minimum **usable on tablet** for demos and on-the-go checks.

---

## 6. Typography & Spacing Philosophy

Drawing from Vercel, Linear, and Stripe:

| Principle | Implementation |
|-----------|---------------|
| **Limited type scale** | Use 4-6 sizes max: 12px (caption), 14px (body/table), 16px (subhead), 20px (section title), 28px (page title) |
| **Weight for hierarchy** | Regular (400) for body, Medium (500) for labels/headers, Semibold (600) for page titles. Avoid bold (700) except for emphasis. |
| **Generous line height** | 1.5 for body text, 1.3 for headings |
| **Consistent spacing scale** | Use a 4px base: 4, 8, 12, 16, 24, 32, 48, 64. Never use arbitrary values. |
| **Tabular numbers** | Always for data tables and metrics |
| **System font stack** | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif` for fast rendering, or use Inter/Geist for branded feel |
| **Color for hierarchy, not decoration** | Primary text (#111), secondary text (#666), muted text (#999). Never use color just to "make it pop." |

---

## 7. References & Resources

### Product Design Systems
- [Vercel Web Interface Guidelines](https://vercel.com/design/guidelines)
- [Vercel Geist Design System](https://vercel.com/geist/typography)
- [Intercom Design System](https://intercom.design/)
- [Stripe Apps Design Patterns](https://docs.stripe.com/stripe-apps/patterns)
- [Carbon Design System -- Notifications](https://carbondesignsystem.com/patterns/notification-pattern/)

### UX Analysis & Case Studies
- [Vercel Dashboard Redesign](https://vercel.com/blog/dashboard-redesign)
- [Vercel Dashboard Performance](https://vercel.com/blog/how-we-made-the-vercel-dashboard-twice-as-fast)
- [Linear UI Redesign](https://linear.app/now/how-we-redesigned-the-linear-ui)
- [Linear Invisible Details](https://medium.com/linear-app/invisible-details-2ca718b41a44)
- [Intercom IA Redesign](https://www.intercom.com/blog/designing-for-clarity-restructuring-intercoms-information-architecture/)
- [Intercom Interaction Design Fundamentals](https://www.intercom.com/blog/fundamentals-good-interaction-design/)
- [Stripe Payment UX Gold Standard](https://www.illustration.app/blog/stripe-payment-ux-gold-standard)
- [Notion UI Breakdown](https://medium.com/@yolu.x0918/a-breakdown-of-notion-how-ui-design-pattern-facilitates-autonomy-cleanness-and-organization-84f918e1fa48)

### Pattern Libraries & Inspiration
- [SaaSFrame -- 166 Dashboard Examples](https://www.saasframe.io/categories/dashboard)
- [SaaSFrame -- 90 Empty State Examples](https://www.saasframe.io/categories/empty-state)
- [SaaS Interface -- Dashboard Gallery](https://saasinterface.com/pages/dashboard/)
- [Pencil & Paper -- Dashboard UX Patterns](https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-dashboards)
- [Pencil & Paper -- Data Table UX](https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-data-tables)
- [Pencil & Paper -- Empty States](https://www.pencilandpaper.io/articles/empty-states)

### Technical Implementation
- [HTMX Animation Examples](https://htmx.org/examples/animations/)
- [HTMX View Transitions](https://htmx.org/essays/view-transitions/)
- [HTMX UX Patterns](https://htmx.org/examples/)
- [Building Skeleton Screens with CSS (CSS-Tricks)](https://css-tricks.com/building-skeleton-screens-css-custom-properties/)
- [Dark Mode CSS Complete Guide](https://css-tricks.com/a-complete-guide-to-dark-mode-on-the-web/)
- [How to Build a Command Palette (Superhuman)](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/)
- [Awesome Command Palette (GitHub)](https://github.com/stefanjudis/awesome-command-palette)
- [Toast Notification Best Practices (LogRocket)](https://blog.logrocket.com/ux-design/toast-notifications/)

### Real Estate CRM References
- [Follow Up Boss CRM Design](https://saasdesigner.com/fub/)
- [Follow Up Boss Review 2025](https://inboundrem.com/follow-up-boss-pros-and-cons/)
- [kvCORE Reviews 2025](https://www.selecthub.com/p/crm-for-commercial-real-estate/kvcore/)
- [Sierra Interactive Review 2025](https://unifyrealestate.com/platform/sierra-interactive/)

### General UX Best Practices
- [SaaS UI Design Trends 2026](https://www.saasui.design/blog/7-saas-ui-design-trends-2026)
- [Admin Dashboard Best Practices 2025 (Medium)](https://medium.com/@CarlosSmith24/admin-dashboard-ui-ux-best-practices-for-2025-8bdc6090c57d)
- [Micro-Interactions in Web Design 2025 (Stan Vision)](https://www.stan.vision/journal/micro-interactions-2025-in-web-design)
- [Micro-Interactions Guide 2025 (Justinmind)](https://www.justinmind.com/web-design/micro-interactions)
- [Empty State UX (Eleken)](https://www.eleken.co/blog-posts/empty-state-ux)
- [Table Design UX (Eleken)](https://www.eleken.co/blog-posts/table-design-ux)
- [Command Palette UX Patterns (Medium)](https://medium.com/design-bootcamp/command-palette-ux-patterns-1-d6b6e68f30c1)
- [Accessible Feedback Patterns (DEV)](https://dev.to/miasalazar/replacing-toasts-with-accessible-user-feedback-patterns-1p8l)
