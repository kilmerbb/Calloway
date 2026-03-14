# HTMX + Jinja2 + CSS + Accessibility — Best Practices Reference (2025–2026)

**Prepared by:** Oracle (Research)
**Date:** 2026-03-14
**Confidence Level:** High — based on official documentation, community patterns, and production case studies

---

## Table of Contents

1. [HTMX Anti-Patterns and How to Avoid Them](#1-htmx-anti-patterns-and-how-to-avoid-them)
2. [HTMX + Jinja2 Server-Side Rendering Architecture](#2-htmx--jinja2-server-side-rendering-architecture)
3. [CSS Organization for Large Admin Panels](#3-css-organization-for-large-admin-panels)
4. [Accessibility Checklist for HTMX-Powered Apps](#4-accessibility-checklist-for-htmx-powered-apps)
5. [Performance Optimization for Server-Rendered HTMX Apps](#5-performance-optimization-for-server-rendered-htmx-apps)

---

## 1. HTMX Anti-Patterns and How to Avoid Them

### Anti-Pattern: Separating Frontend and Backend Origins

**Problem:** Serving HTML frontend from a different domain/URL than the backend, requiring absolute URLs and CORS headers.

**Fix:** Serve HTMX-driven HTML from the same server (or at least the same domain) as your backend. HTMX is designed around same-origin requests — this eliminates CORS issues and simplifies CSRF handling.

### Anti-Pattern: Thinking in JSON / SPA Mindset

**Problem:** Returning JSON from endpoints and trying to build/render HTML client-side.

**Fix:** Servers should return HTML fragments, not JSON. There is no client-side rendering layer, no component lifecycle management, and no state synchronization between client and server. The backend generates HTML; HTMX places it where you specify.

### Anti-Pattern: Calling Untrusted HTML APIs

**Problem:** Using HTMX to call third-party HTML endpoints you don't control.

**Fix:** Never use HTMX to fetch untrusted HTML — HTMX executes HTML, and HTML is code. If you need third-party data, use `fetch()` + `JSON.parse()` and render it server-side.

### Anti-Pattern: Using HTMX for Highly Interactive / Offline-First Apps

**Problem:** Forcing HTMX into use cases requiring rich client-side state management, complex animations, or offline capability.

**Fix:** HTMX is best for server-driven CRUD applications, admin dashboards, and data-heavy pages. For offline-first or complex interactive features (e.g., drag-and-drop editors, real-time collaboration canvases), use purpose-built JavaScript.

### Anti-Pattern: Over-swapping / Full-Page Replacements

**Problem:** Swapping large DOM regions when only a small part changed, or doing full-page swaps that lose client state.

**Fix:** Target the smallest possible DOM region with `hx-target`. Use morphing swaps (Idiomorph extension) to preserve focus, video state, and form inputs during updates. Use `hx-preserve` on elements that must not be replaced.

### Anti-Pattern: Request Storms from Rapid User Input

**Problem:** Sending an HTMX request on every keystroke without debouncing, overwhelming the server.

**Fix:** Use `hx-trigger="keyup changed delay:300ms"` for search inputs. Use `hx-sync="closest form:replace"` to cancel in-flight requests when new ones start. Use `hx-sync` with `queue` or `drop` strategies as appropriate.

### Anti-Pattern: Missing HTML Auto-Escaping

**Problem:** Returning dynamic content without escaping, creating XSS vulnerabilities.

**Fix:** Always use a template engine with auto-escaping enabled (Jinja2 has it on by default). Use `hx-disable` on elements containing user-generated content to prevent HTMX attribute processing. Whitelist allowed attributes/tags rather than blacklisting.

---

## 2. HTMX + Jinja2 Server-Side Rendering Architecture

### Template Organization

```
templates/
├── base.html                    # Root skeleton: <html>, <head>, <body>, nav, footer
├── layouts/
│   ├── console.html             # Admin layout (sidebar + main area), extends base
│   └── public.html              # Public-facing layout, extends base
├── partials/                    # HTMX fragment targets (NO <html>/<body> wrappers)
│   ├── _toast.html              # Notification toast (OOB swap target)
│   ├── _modal.html              # Modal shell
│   ├── _table_rows.html         # Table body fragment for infinite scroll
│   └── _form_errors.html        # Validation error list
├── components/                  # Reusable Jinja2 macros
│   ├── _macros.html             # Shared macros (buttons, cards, badges, inputs)
│   ├── _pagination.html         # Pagination macro
│   └── _data_table.html         # Data table macro with sort/filter
├── console/                     # Full pages for admin console
│   ├── dashboard.html           # extends layouts/console.html
│   ├── conversations.html
│   ├── triggers.html
│   └── settings.html
└── emails/                      # Email templates (separate inheritance chain)
    └── base_email.html
```

### Key Patterns

**1. Dual-Response Endpoints (Full Page vs. Fragment)**

Every endpoint should detect HTMX requests and return either a full page or a fragment:

```python
@router.get("/console/conversations")
async def conversations(request: Request):
    data = await get_conversations(...)
    template = "partials/_conversation_list.html" if request.headers.get("HX-Request") else "console/conversations.html"
    return templates.TemplateResponse(template, {"request": request, **data})
```

**2. Jinja2 Inheritance — 3-Level Maximum**

```
base.html → layouts/console.html → console/dashboard.html
```

Keep inheritance to 3 levels max. Deeper nesting makes debugging difficult and slows rendering.

**3. Macros for Reusable Components**

Store macros in dedicated files and import only what you need:

```jinja
{# components/_macros.html #}
{% macro button(text, variant="primary", hx_post=None, hx_target=None) %}
<button class="btn btn-{{ variant }}"
    {% if hx_post %}hx-post="{{ hx_post }}" hx-target="{{ hx_target }}"{% endif %}>
    {{ text }}
</button>
{% endmacro %}

{# Usage in a page #}
{% from "components/_macros.html" import button %}
{{ button("Save", variant="primary", hx_post="/api/save", hx_target="#result") }}
```

**4. Partials Convention**

- Prefix partial templates with `_` (e.g., `_toast.html`)
- Partials never extend a base template — they are bare HTML fragments
- Partials are the only templates targeted by HTMX swaps

**5. Out-of-Band (OOB) Swaps for Multi-Region Updates**

When a single action must update multiple DOM regions (e.g., save a record AND update a notification count):

```html
<!-- Primary response swapped into hx-target -->
<div id="record-detail">...updated content...</div>

<!-- OOB swap: updates notification badge regardless of hx-target -->
<span id="notification-count" hx-swap-oob="true">3</span>
```

**6. CSRF Protection (FastAPI + HTMX)**

Apply the CSRF token globally via `hx-headers` on `<body>`:

```html
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
```

This ensures every HTMX request includes the token without per-element configuration.

**7. hx-boost for Progressive Enhancement**

Add `hx-boost="true"` to the `<body>` tag or navigation container. This converts all `<a>` and `<form>` elements to AJAX requests automatically, preserving full-page navigation as a fallback when JS is disabled.

**8. hx-swap Strategy Guide**

| Strategy | Use Case |
|----------|----------|
| `innerHTML` (default) | Replace contents of target (most common) |
| `outerHTML` | Replace the target element itself (use for full component replacement) |
| `beforeend` | Append to target (infinite scroll, chat messages) |
| `afterbegin` | Prepend to target (newest-first lists) |
| `delete` | Remove the target element (after successful delete action) |
| `none` | Fire the request but don't swap (side-effect-only actions) |

Add modifiers: `hx-swap="innerHTML swap:200ms settle:100ms"` for transition timing.

**9. SSE for Real-Time Updates**

```html
<div hx-ext="sse" sse-connect="/events/stream">
    <div sse-swap="new-message" hx-swap="beforeend">
        <!-- New messages appended here -->
    </div>
    <div sse-swap="status-update">
        <!-- Status replaced here -->
    </div>
</div>
```

Use SSE (not WebSockets) for uni-directional server-to-client updates like notifications, status changes, and live feeds. Reserve WebSockets for true bi-directional needs.

**10. Lazy Loading**

```html
<!-- Load on page init -->
<div hx-get="/api/stats" hx-trigger="load" hx-swap="innerHTML">
    <div class="skeleton-loader">Loading...</div>
</div>

<!-- Load when scrolled into view -->
<div hx-get="/api/chart" hx-trigger="revealed" hx-swap="innerHTML">
    <div class="skeleton-loader">Loading...</div>
</div>

<!-- Fine-grained viewport control -->
<div hx-get="/api/data" hx-trigger="intersect threshold:0.5" hx-swap="innerHTML">
    Loading...
</div>
```

**Decision rule:** If content must exist before users can act, render it server-side. If it is below the fold, personalized, or takes >200ms to query, defer it with HTMX lazy loading.

---

## 3. CSS Organization for Large Admin Panels

### Architecture: Design Tokens + Layered CSS

```
static/css/
├── tokens/
│   ├── _primitives.css          # Raw values: --blue-500, --gray-100, --radius-md
│   ├── _semantic-light.css      # Semantic mappings for light: --surface-bg, --text-primary
│   └── _semantic-dark.css       # Semantic mappings for dark theme
├── base/
│   ├── _reset.css               # Modern CSS reset
│   ├── _typography.css          # Font stacks, scale, line heights
│   └── _utilities.css           # Utility classes (visually-hidden, flex-center, etc.)
├── layout/
│   ├── _shell.css               # App shell: sidebar, topbar, main content area
│   ├── _grid.css                # Dashboard grid system
│   └── _responsive.css          # Viewport-level breakpoints (page structure only)
├── components/
│   ├── _button.css
│   ├── _card.css
│   ├── _data-table.css
│   ├── _modal.css
│   ├── _form.css
│   ├── _toast.css
│   ├── _badge.css
│   └── _sidebar.css
└── main.css                     # Single entry point: @import all above in order
```

### Design Token System

```css
/* tokens/_primitives.css */
:root {
    /* Color Palette */
    --blue-50: #eff6ff;
    --blue-500: #3b82f6;
    --blue-700: #1d4ed8;
    --gray-50: #f9fafb;
    --gray-900: #111827;

    /* Spacing Scale */
    --space-1: 0.25rem;
    --space-2: 0.5rem;
    --space-4: 1rem;
    --space-6: 1.5rem;
    --space-8: 2rem;

    /* Typography Scale */
    --text-sm: 0.875rem;
    --text-base: 1rem;
    --text-lg: 1.125rem;

    /* Radius */
    --radius-sm: 0.25rem;
    --radius-md: 0.375rem;
    --radius-lg: 0.5rem;

    /* Shadows */
    --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
    --shadow-md: 0 4px 6px rgb(0 0 0 / 0.1);
}

/* tokens/_semantic-light.css */
:root, [data-theme="light"] {
    --surface-bg: var(--gray-50);
    --surface-card: #ffffff;
    --text-primary: var(--gray-900);
    --text-secondary: #6b7280;
    --border-default: #e5e7eb;
    --interactive: var(--blue-500);
    --interactive-hover: var(--blue-700);
    --focus-ring: 0 0 0 3px rgba(59, 130, 246, 0.5);
}

/* tokens/_semantic-dark.css */
[data-theme="dark"] {
    --surface-bg: #0f172a;
    --surface-card: #1e293b;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --border-default: #334155;
    --interactive: #60a5fa;
    --interactive-hover: #93bbfd;
    --focus-ring: 0 0 0 3px rgba(96, 165, 250, 0.5);
}
```

### Dark Mode Implementation

**Recommended approach:** `data-theme` attribute on `<html>` with CSS custom property overrides.

```html
<html data-theme="light">
```

```javascript
// Theme toggle — persist to localStorage, respect system preference as default
function initTheme() {
    const saved = localStorage.getItem('theme');
    const system = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', saved || system);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
}
```

**Prevent flash of wrong theme (FOWT):** Place a blocking `<script>` in `<head>` before any CSS loads:

```html
<script>
    document.documentElement.setAttribute('data-theme',
        localStorage.getItem('theme') ||
        (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light')
    );
</script>
```

### Container Queries for Admin Components

Use container queries for components that appear in multiple layout contexts (main content, sidebar, modal):

```css
/* The parent wrapper establishes the containment context */
.widget-container {
    container-type: inline-size;
    container-name: widget;
}

/* The component responds to its container, not the viewport */
@container widget (min-width: 400px) {
    .stat-card { flex-direction: row; }
}

@container widget (max-width: 399px) {
    .stat-card { flex-direction: column; }
}
```

**Rule of thumb:**
- **Viewport queries (`@media`):** Page-level layout (sidebar collapse, grid column count)
- **Container queries (`@container`):** Component-level adaptation (card layout, table density)

### Modern CSS Features to Adopt

| Feature | Use Case | Browser Support |
|---------|----------|----------------|
| Container queries (size) | Responsive components in varied contexts | 95%+ |
| `:has()` | Parent-aware styling without JS | 95%+ |
| CSS nesting | Cleaner component styles | 95%+ |
| `light-dark()` function | Simplified theme token declarations | Emerging |
| Cascade layers (`@layer`) | Control specificity across token/base/component layers | 95%+ |
| Subgrid | Align nested grid items to parent grid | 93%+ |

### Cascade Layers for Specificity Control

```css
/* main.css */
@layer tokens, reset, base, layout, components, utilities;

@import "tokens/_primitives.css" layer(tokens);
@import "tokens/_semantic-light.css" layer(tokens);
@import "tokens/_semantic-dark.css" layer(tokens);
@import "base/_reset.css" layer(reset);
@import "base/_typography.css" layer(base);
@import "layout/_shell.css" layer(layout);
@import "components/_button.css" layer(components);
@import "base/_utilities.css" layer(utilities);
```

This guarantees utilities always win over components, components over layout, etc. — without resorting to `!important`.

---

## 4. Accessibility Checklist for HTMX-Powered Apps

### Semantic HTML First

- [ ] Use native `<button>`, `<a>`, `<input>`, `<select>`, `<dialog>` before reaching for ARIA
- [ ] Use `<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>` landmarks
- [ ] Use heading hierarchy (`<h1>`–`<h6>`) correctly — one `<h1>` per page, no skipped levels
- [ ] Use `<table>` with `<thead>`, `<th scope>` for data tables, not for layout

### Dynamic Content Announcements (Critical for HTMX)

- [ ] Wrap HTMX swap targets that update asynchronously in `aria-live="polite"` regions
- [ ] Use `aria-live="assertive"` only for urgent alerts (errors, session timeout)
- [ ] Use `aria-busy="true"` on containers during loading, set to `false` after swap completes
- [ ] Ensure `aria-live` regions exist in the DOM on page load (don't add them dynamically)
- [ ] For toast notifications, use `role="status"` with `aria-live="polite"`
- [ ] For error alerts, use `role="alert"` (implicitly `aria-live="assertive"`)

### Focus Management After HTMX Swaps

- [ ] After content swap that changes layout, programmatically move focus to the new content's heading or first interactive element using `htmx:afterSwap`
- [ ] After form submission success, move focus to the success message
- [ ] After form validation failure, move focus to the first error
- [ ] After modal open, trap focus within the modal; on close, return focus to the trigger element
- [ ] After delete action, move focus to the next logical element in the list
- [ ] Use `tabindex="-1"` on non-interactive elements that need programmatic focus (headings, containers)
- [ ] Consider the Idiomorph extension for morphing swaps that preserve focus state

```javascript
// Example: Focus management after HTMX swap
document.addEventListener('htmx:afterSwap', function(event) {
    const target = event.detail.target;
    // Focus the first heading or first focusable element in swapped content
    const focusTarget = target.querySelector('h1, h2, h3, [autofocus], input, button');
    if (focusTarget) {
        focusTarget.setAttribute('tabindex', '-1');
        focusTarget.focus();
    }
});
```

### Keyboard Navigation

- [ ] All interactive elements are reachable via Tab / Shift+Tab
- [ ] Custom widgets implement expected key bindings (Arrow keys in menus, Escape to close)
- [ ] No keyboard traps — users can always Tab out (except inside open modals)
- [ ] Skip-to-main-content link as first focusable element
- [ ] Visible focus indicators on all interactive elements (minimum 3:1 contrast per WCAG 2.2 SC 2.4.11)
- [ ] Focus indicators must be at least 2px thick perimeter around the element

### WCAG 2.2 New Success Criteria (Relevant to Admin Dashboards)

| Criterion | Level | What It Means |
|-----------|-------|---------------|
| 2.4.11 Focus Appearance | AA | Focus indicator must have ≥3:1 contrast and ≥2px perimeter |
| 2.4.12 Focus Not Obscured (Minimum) | AA | Focused element must not be fully hidden by sticky headers/footers |
| 2.4.13 Focus Not Obscured (Enhanced) | AAA | Focused element must not be even partially hidden |
| 2.5.7 Dragging Movements | AA | Any draggable operation must have a non-dragging alternative |
| 2.5.8 Target Size (Minimum) | AA | Interactive targets must be at least 24x24 CSS pixels |
| 3.2.6 Consistent Help | A | Help mechanisms must be in the same relative position on each page |
| 3.3.7 Redundant Entry | A | Don't ask users to re-enter info already provided in the same session |
| 3.3.8 Accessible Authentication (Minimum) | AA | No cognitive function tests (e.g., puzzle CAPTCHAs) for auth |

### ARIA Patterns for Common HTMX Components

**Modals:**
```html
<dialog id="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <h2 id="modal-title">Edit Contact</h2>
    <!-- Trap focus here. Close on Escape. Return focus to trigger on close. -->
</dialog>
```

**Tabs:**
```html
<div role="tablist" aria-label="Conversation views">
    <button role="tab" aria-selected="true" aria-controls="panel-active" id="tab-active">Active</button>
    <button role="tab" aria-selected="false" aria-controls="panel-closed" id="tab-closed">Closed</button>
</div>
<div role="tabpanel" id="panel-active" aria-labelledby="tab-active"
     hx-get="/console/conversations?status=active" hx-trigger="load">
    <!-- Content loaded by HTMX -->
</div>
```

**Live Search Results:**
```html
<input type="search" aria-label="Search contacts"
       hx-get="/api/search" hx-trigger="keyup changed delay:300ms"
       hx-target="#results" aria-controls="results">
<div id="results" role="region" aria-live="polite" aria-label="Search results">
    <!-- HTMX swaps results here; screen reader announces updates -->
</div>
```

### Testing Approach

- Automated tools (axe, Lighthouse) catch ~40% of WCAG 2.2 issues
- Manual testing required: focus visibility, consistent help placement, redundant entry, authentication flows
- Test with keyboard-only navigation (unplug the mouse)
- Test with a screen reader (NVDA on Windows, VoiceOver on macOS)
- Test with browser zoom at 200% and 400%

---

## 5. Performance Optimization for Server-Rendered HTMX Apps

### HTTP Caching for HTMX Fragments

**ETag / Last-Modified:** HTMX respects standard HTTP caching. Return `Last-Modified` and `ETag` headers on fragment responses. The browser will send `If-Modified-Since` / `If-None-Match` on subsequent requests, and the server can return `304 Not Modified` (zero bytes transferred).

**Important:** If the same URL returns different content based on `HX-Request` (full page vs. fragment), generate a unique ETag per variant, or use the `Vary: HX-Request` header.

**Cache-Control for fragments:**
```
Cache-Control: private, max-age=60    # Cache for 60s (user-specific content)
Cache-Control: public, max-age=300    # Cache for 5min (shared content like listings)
Cache-Control: no-cache               # Always revalidate (conversations, triggers)
```

### Client-Side Caching

Use `hx-cache="true"` or `hx-cache="30s"` to cache HTMX GET responses in memory. Good for navigation tabs or reference data that doesn't change often.

### Preloading

Use the HTMX preload extension for predictable navigation:

```html
<a href="/console/dashboard" preload="mousedown">Dashboard</a>
<a href="/console/conversations" preload="mouseover">Conversations</a>
```

`mousedown` fires ~100ms before `click` — enough to start loading. `mouseover` is more aggressive but may waste bandwidth.

### Server-Side Optimization

| Technique | Impact | Implementation |
|-----------|--------|----------------|
| Redis template fragment caching | 85-90% cache hits on repeated renders | Cache rendered HTML fragments keyed by tenant + params |
| Jinja2 async template loader | Faster template resolution | Use async file loader with in-memory LRU cache |
| Connection pooling | Reduce DB latency | asyncpg pool with min=5, max=20 per worker |
| Partial queries | Reduce DB load | Only query columns/rows needed for the fragment |
| HTTP/2 multiplexing | Parallel fragment loading | Enable in reverse proxy (nginx/caddy) |

### Request Optimization

- **Debounce:** `hx-trigger="keyup changed delay:300ms"` for search/filter inputs
- **Sync:** `hx-sync="closest form:replace"` to cancel stale in-flight requests
- **Stagger lazy loads:** Use `hx-trigger="load delay:100ms"`, `delay:200ms`, `delay:300ms` on dashboard widgets to avoid request storms at page load
- **Minimal payloads:** Return only the HTML fragment needed — avoid sending nav, sidebar, or other chrome in fragment responses

### View Transitions

HTMX 2.0 supports the View Transitions API for smooth swap animations:

```html
<meta name="htmx-config" content='{"globalViewTransitions": true}'>
```

This gives you cross-fade transitions on swaps without custom CSS animation code.

### Benchmarks (2025)

- FastAPI + HTMX SSR: ~45ms Time to Interactive (vs. ~650ms for React SPA)
- Server-side fragment rendering with Redis cache: 90% cache hit rate in production
- Service worker + HTMX boost: DOMContentLoaded drops from 2.9s to <500ms, transmitted data from 2MB to 84KB

---

## So What — Actionable Implications for Calloway

1. **Template restructure:** Adopt the `templates/partials/` + `templates/components/` organization. Every HTMX endpoint should have a corresponding partial. Macros should be extracted for buttons, form fields, data tables, badges, and cards.

2. **CSS design tokens:** Implement a 3-layer token system (primitives → semantic → component). This enables dark mode, future theming, and consistent spacing/color without scattered magic values.

3. **Dark mode:** Use `data-theme` attribute on `<html>` with CSS custom property overrides. Add the FOWT-prevention script to `<head>`. Persist preference to localStorage with system-preference fallback.

4. **Container queries now:** The console dashboard has widgets that appear in different contexts (main area, modals, possibly a future mobile view). Container queries eliminate breakpoint gymnastics for these components. Browser support is 95%+.

5. **Accessibility is non-negotiable:** Add `aria-live="polite"` to all HTMX swap targets that update asynchronously. Implement `htmx:afterSwap` focus management. Ensure 24x24px minimum target sizes and 2px+ focus indicators. The WCAG 2.2 criteria around focus appearance (2.4.11, 2.4.12) are especially relevant for admin dashboards with sticky headers.

6. **Performance quick wins:** Add `Vary: HX-Request` and `ETag` headers to fragment endpoints. Use Redis fragment caching for expensive queries (conversation lists, dashboard stats). Stagger dashboard widget loads to avoid request storms.

7. **CSRF:** Apply `hx-headers` with CSRF token on `<body>` globally — one line, all requests covered.

8. **SSE for real-time:** Use SSE (not WebSockets) for the trigger worker status, conversation updates, and notification badges. SSE is simpler, works through proxies, and is sufficient for Calloway's uni-directional update needs.

---

## Sources

- [HTMX Official Documentation](https://htmx.org/docs/)
- [HTMX Web Security Basics](https://htmx.org/essays/web-security-basics-with-htmx/)
- [HTMX hx-swap Attribute Reference](https://htmx.org/attributes/hx-swap/)
- [HTMX Preload Extension](https://htmx.org/extensions/preload/)
- [HTMX SSE Extension](https://v1.htmx.org/extensions/server-sent-events/)
- [HTMX Complete Guide for 2026 (DevToolbox)](https://devtoolbox.dedyn.io/blog/htmx-complete-guide)
- [HTMX Best Practices (DEV Community)](https://dev.to/hexshift/htmx-best-practices-building-responsive-web-apps-without-javascript-frameworks-25dm)
- [HTMX + FastAPI Patterns 2025](https://johal.in/htmx-fastapi-patterns-hypermedia-driven-single-page-applications-2025/)
- [HTMX Performance Optimization (aspnet-htmx)](https://aspnet-htmx.com/chapter20/)
- [Smart Loading Patterns with HTMX](https://blog.openreplay.com/smart-loading-patterns-htmx/)
- [HTMX Accessibility Issue #1431](https://github.com/bigskysoftware/htmx/issues/1431)
- [HTMX Accessibility Considerations (StudyRaid)](https://app.studyraid.com/en/read/1955/32848/accessibility-considerations-in-htmx-applications)
- [HTMX Security Best Practices (DeepWiki)](https://deepwiki.com/bigskysoftware/htmx/9.1-security-best-practices)
- [HTMX CSRF with Django](https://django-htmx.readthedocs.io/en/latest/tips.html)
- [Jinja2 Template Designer Documentation](https://jinja.palletsprojects.com/en/stable/templates/)
- [Jinja2 Template Inheritance and Inclusion (DeepWiki)](https://deepwiki.com/pallets/jinja/3.2-template-inheritance-and-inclusion)
- [Primer on Jinja Templating (Real Python)](https://realpython.com/primer-on-jinja-templating/)
- [Flask Jinja2 Templates (OneUpTime)](https://oneuptime.com/blog/post/2026-02-02-flask-jinja2-templates/view)
- [FastAPI Templating with Jinja2 and HTMX 2025](https://www.johal.in/fastapi-templating-jinja2-server-rendered-ml-dashboards-with-htmx-2025/)
- [CSS Variables Guide: Design Tokens & Theming 2025](https://www.frontendtools.tech/blog/css-variables-guide-design-tokens-theming-2025)
- [Dark Mode Implementation Guide 2025](https://medium.com/design-bootcamp/the-ultimate-guide-to-implementing-dark-mode-in-2025-bbf2938d2526)
- [Dark Mode CSS Complete Guide (design.dev)](https://design.dev/guides/dark-mode-css/)
- [Developer's Guide to Design Tokens and CSS Variables (Penpot)](https://penpot.app/blog/the-developers-guide-to-design-tokens-and-css-variables/)
- [The State of CSS in 2026 (CoderCops)](https://www.codercops.com/blog/state-of-css-2026)
- [CSS Container Queries Complete Guide 2026 (DevToolbox)](https://devtoolbox.dedyn.io/blog/css-container-queries-guide)
- [Container Queries in 2026 (LogRocket)](https://blog.logrocket.com/container-queries-2026/)
- [Modern CSS Trends 2025 (Medium)](https://medium.com/@mernstackdevbykevin/modern-css-trends-2025-container-queries-subgrid-cascade-layers-real-use-cases-tips-733af70eb5fb)
- [2026 CSS Features You Must Know](https://blog.riadkilani.com/2026-css-features-you-must-know/)
- [WCAG 2.2 Complete Compliance Guide 2025](https://www.allaccessible.org/blog/wcag-22-complete-guide-2025)
- [Accessible Modals & Dialogs (WCAG 2.2 Guide)](https://www.thewcag.com/examples/modals-dialogs)
- [Accessible Navigation (WCAG 2.2 Guide)](https://www.thewcag.com/examples/navigation)
- [Keyboard Navigation & Focus (Accesify)](https://www.accesify.io/blog/keyboard-navigation-focus-wcag/)
- [ARIA Live Regions (MDN)](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions)
- [Focus Management for Dynamic Websites (Vision Australia)](https://www.visionaustralia.org/business-consulting/digital-access/blog/making-dynamic-websites-accessible-using-focus-management)
