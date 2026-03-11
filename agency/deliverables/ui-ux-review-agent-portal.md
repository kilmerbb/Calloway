# Calloway UI/UX Review — Agent Portal + Design System
## Date: 2026-03-11
## Reviewer: Lyra, Product Designer

---

## Design System Specification (Spotify-Inspired)

### Color Palette

The current agent portal uses a **light-mode, corporate SaaS palette** (white cards on `#f8fafc` background with blue accents). This is the single largest departure from the Spotify-inspired direction the CEO wants. The entire color system must shift to dark-mode-native.

**Proposed Calloway Dark Palette:**

| Token | Hex | Current (`style.css` var) | Usage |
|-------|-----|--------------------------|-------|
| `--bg-base` | `#121212` | `--bg: #f8fafc` (line 3) | Main app background |
| `--bg-elevated` | `#181818` | `--bg-card: #ffffff` (line 4) | Cards, panels, nav surfaces |
| `--bg-elevated-2` | `#212121` | `--bg-hover: #f1f5f9` (line 5) | Hover states, active surfaces |
| `--bg-highlight` | `#282828` | n/a | Selected/pressed states |
| `--bg-press` | `#333333` | `--border: #e2e8f0` (line 6) | Dividers, tracks, pressed |
| `--text-primary` | `#FFFFFF` | `--text: #1e293b` (line 7) | Headings, names, primary content |
| `--text-secondary` | `#B3B3B3` | `--text-muted: #64748b` (line 8) | Subtitles, metadata, timestamps |
| `--text-subdued` | `#A7A7A7` | n/a | Tertiary info, placeholders |
| `--text-disabled` | `#535353` | n/a | Disabled controls |
| `--accent` | `#1ED760` | `--accent: #2563eb` (line 9) | Primary CTAs, active nav indicators |
| `--accent-ui` | `#1DB954` | `--accent-light: #eff6ff` (line 10) | Active toggles, progress bars |
| `--success` | `#1ED760` | `--green: #16a34a` (line 11) | Confirmed status, positive metrics |
| `--success-surface` | `rgba(30, 215, 96, 0.12)` | `--green-light: #f0fdf4` (line 12) | Success badge backgrounds |
| `--warning` | `#FFA42B` | `--yellow: #ca8a04` (line 13) | Hold status, pending approvals |
| `--warning-surface` | `rgba(255, 164, 43, 0.12)` | `--yellow-light: #fefce8` (line 14) | Warning badge backgrounds |
| `--error` | `#E91429` | `--red: #dc2626` (line 15) | Failed delivery, STOP/revoked |
| `--error-surface` | `rgba(233, 20, 41, 0.12)` | `--red-light: #fef2f2` (line 16) | Error badge backgrounds |
| `--border` | `rgba(255, 255, 255, 0.08)` | `--border: #e2e8f0` (line 6) | Subtle dividers (use sparingly) |

**Key shift:** Badge backgrounds should use semi-transparent tinted overlays (`rgba`) rather than opaque pastel colors, allowing them to look correct on any dark surface.

### Typography Scale

The current CSS (line 24) uses `-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, sans-serif` at a base of `15px` (line 28). This is a reasonable system font stack, but needs restructuring for Spotify-inspired hierarchy.

**Proposed Font Stack:**
```
--font-primary: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```
Inter is the closest freely available approximation to Spotify Mix's geometric-grotesque hybrid character. It supports variable weight axes and has excellent screen legibility.

**Proposed Type Scale:**

| Token | Size | Weight | Line Height | Usage | Current Issue |
|-------|------|--------|-------------|-------|---------------|
| `--text-display` | 32px | 700 | 1.2 | Dashboard greeting (not yet implemented) | No display type exists |
| `--text-h1` | 24px | 700 | 1.3 | Page titles | `.section-title` is only 16px (line 100) |
| `--text-h2` | 20px | 700 | 1.3 | Section headers ("Today", "Upcoming") | Uses same `.section-title` at 16px |
| `--text-h3` | 16px | 600 | 1.3 | List item names (`.list-name`) | Currently 14px/500 (line 138) |
| `--text-body` | 14px | 400 | 1.5 | Descriptions, previews, metadata | Currently 15px base (line 28) — close enough |
| `--text-caption` | 12px | 400 | 1.4 | Timestamps, badge text, stat labels | Mostly correct |
| `--text-overline` | 12px | 700 | 1.4 | Category labels, uppercase tags | `.stat-label` (line 91) partially does this |

**Hierarchy through color (Spotify approach):**
- Primary content: `#FFFFFF`
- Secondary content: `#B3B3B3`
- Tertiary/timestamps: `#A7A7A7`

Currently, the hierarchy relies on a single `--text-muted` for all secondary content, collapsing two distinct levels into one.

### Spacing Scale

The current CSS uses inconsistent `rem`-based spacing throughout (`0.75rem`, `1rem`, `1.25rem`, `0.5rem`, etc.). There is no defined spacing scale.

**Proposed 4px Base Grid:**

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Tight inner gaps (badge padding, icon-to-text) |
| `--space-2` | 8px | Component internal padding, small gaps |
| `--space-3` | 12px | List item vertical padding, small margins |
| `--space-4` | 16px | Standard card padding, grid gaps, page margin (mobile) |
| `--space-5` | 20px | Medium gaps |
| `--space-6` | 24px | Section spacing, card grid gaps |
| `--space-8` | 32px | Page margins (desktop), major section gaps |
| `--space-10` | 40px | Large layout gaps |
| `--space-12` | 48px | Desktop page top margin |

**Current violations:**
- `.agent-main` padding: `1rem` (line 76) = 16px — fine for mobile, too tight for desktop
- `.card` padding: `1rem` (line 83) = 16px — matches Spotify's `--md`
- `.stat-card` padding: `1.25rem 1rem` (line 89) — 20px/16px — awkward non-grid value
- `.list-item` padding: `0.75rem 1rem` (line 113) = 12px/16px — acceptable
- `.card-grid` gap: `0.75rem` (line 87) = 12px — should be 16px for breathing room

### Component Specs

#### Cards (`.card`, `.stat-card`)

**Current state (lines 79-95):**
- White background, 1px border `#e2e8f0`, 12px radius, light box-shadow
- Stat cards are center-aligned with colored values

**Spotify-inspired spec:**
- Background: `#181818` (elevated surface)
- Border: **none** — cards differentiated by surface color only, not strokes
- Border-radius: 8px (Spotify desktop standard)
- Box-shadow: **none** — dark mode uses luminance for elevation, not shadows
- Hover: background shifts to `#212121`, smooth 200ms transition
- Stat values: use `--text-primary` (#FFFFFF) with a small colored indicator dot or icon instead of coloring the entire number

#### Buttons (`.btn`, `.btn-primary`)

**Current state (lines 252-265):**
- `.btn-primary`: blue `#2563eb` background, white text, 10px radius
- `.btn-outline`: transparent with border
- No pill shape, no hover scale

**Spotify-inspired spec:**
- Primary CTA: `border-radius: 500px` (pill), `background: #1ED760`, `color: #000000`, `font-weight: 700`, sentence case
- Padding: `12px 32px` (generous horizontal)
- Hover: `transform: scale(1.04)`, `filter: brightness(1.1)`
- Press: `transform: scale(0.98)`
- Secondary: pill shape, `border: 1px solid #727272`, transparent background, white text
- Ghost/tertiary: no border, `color: #B3B3B3`, hover brightens to white
- **Contrast:** Black on `#1ED760` = 10.9:1 ratio (far exceeds WCAG AAA)

#### Inputs (`.search-bar`, form inputs)

**Current state (lines 209-220, 269-278):**
- White background, 1px border, 12px radius (`.search-bar`) or 10px (form inputs)
- Focus shows blue border color

**Spotify-inspired spec:**
- Background: `#282828` (elevated surface 2)
- Border: none
- Border-radius: `500px` (pill shape for search bar), `8px` for form inputs
- Text color: `#FFFFFF`, placeholder: `#A7A7A7`
- Focus: subtle `box-shadow: 0 0 0 2px rgba(30, 215, 96, 0.4)` (green glow, not border)
- Search icon: prepend a magnifying glass icon inside the input (left-padded)

#### Badges (`.badge`)

**Current state (lines 146-157):**
- 6px radius, 11px font, pastel backgrounds with colored text

**Spotify-inspired spec:**
- Border-radius: `500px` (pill, matching Spotify's chip pattern)
- Background: semi-transparent colored overlays (e.g., `rgba(30, 215, 96, 0.15)`)
- Text: the accent color at full opacity
- Height: 20px, padding: `2px 10px`
- Font: 11px, weight 600, uppercase for status badges

#### Navigation (`.agent-header`, `.mobile-nav`)

**Current state (lines 35-69, 281-305):**
- White header/nav background with light border
- Blue accent for active links
- HTML entities for mobile nav icons (no proper icon system)

**Spotify-inspired spec:**
- **Desktop:** Left sidebar (not top bar), background `#000000`, width 240-280px
- Nav items: 14px, `#B3B3B3` default, `#FFFFFF` active with a left green accent bar (3px)
- **Mobile:** Bottom bar with `background: #181818`, no top border — use surface elevation
- Active icon: `#FFFFFF` (filled), inactive: `#B3B3B3` (outlined)
- Replace HTML entities with an SVG icon set (Lucide, Heroicons, or custom)
- Note: Migrating from top nav to sidebar is a **full redesign** item, covered below

#### List Items (`.list-item`)

**Current state (lines 109-143):**
- White background, border, shadow, 12px radius
- Each item is visually separate (card-style)

**Spotify-inspired spec:**
- Background: transparent (inherits page background)
- No border, no shadow — items are rows, not cards
- Hover: `background: rgba(255, 255, 255, 0.05)` (subtle highlight)
- Fixed height: 56-64px
- Border-radius: 4px (row hover highlight radius)
- Separator: none between items (or very subtle `rgba(255,255,255,0.05)` bottom border)
- Avatar: keep 40px circle, but background should be `#282828` with `#B3B3B3` text

### Motion & Transitions

**Current state:** Minimal — only `transition: background 0.15s, color 0.15s` on `.nav-link` (line 62) and `transition: background 0.15s` on `.list-item` (line 119).

**Spotify-inspired spec:**

| Property | Duration | Easing | Usage |
|----------|----------|--------|-------|
| Background color | 200ms | `ease-out` | Hover states on cards, list items, nav |
| Transform (scale) | 150ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Button hover/press |
| Opacity | 200ms | `ease-out` | Page content fade-in, skeleton loading |
| Color | 150ms | `ease-out` | Text/icon active state changes |
| Box-shadow | 200ms | `ease-out` | Focus rings |

**Add these global transitions:**
```css
/* Default transition for interactive elements */
--transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
--transition-normal: 200ms ease-out;
--transition-slow: 300ms ease-out;
```

**New motion patterns to implement:**
1. **Page load:** Content sections fade in with staggered delay (0ms, 50ms, 100ms per section)
2. **List items:** Staggered entrance animation on initial load
3. **Hover play/action reveal:** On conversation list items, hover should reveal a "view" arrow icon that fades in from 0 to 1 opacity
4. **Skeleton loading:** Add `.skeleton` class with shimmer animation for HTMX loading states

---

## Agent Portal Screen-by-Screen Review

### Base Layout & Navigation

**File:** `app/templates/agent/base.html` (70 lines)
**CSS:** lines 35-69 (header), lines 281-320 (mobile nav)

**Current State:**
- Fixed top header bar (56px) with logo left, horizontal nav center, user/logout right
- 8 nav items in desktop header: Home, Contacts, Messages, Schedule, Transactions, Reminders, Scores, Campaigns (lines 16-23)
- Mobile bottom nav replicates all 8 items (lines 36-67)
- HTML entities for mobile icons (`&#8962;`, `&#9787;`, `&#9993;`, etc.)
- `max-width: 900px` content area (line 74)

**Issues:**

1. **8 nav items is too many.** Desktop header becomes cramped. Mobile bottom nav with 8 items means each target is ~45px wide — well below the 48px minimum touch target recommended by WCAG 2.1. Spotify uses only 3 primary destinations in mobile bottom nav.

2. **No icon system.** HTML entities render inconsistently across browsers and platforms. The calendar icon `&#128197;` and money bag `&#128176;` are emoji, which render with color on some platforms and monochrome on others. This violates the "Unified" Spotify principle.

3. **Content area is too narrow.** `max-width: 900px` (line 74) wastes space on desktop. Spotify's main content area can go up to ~1600px. For a dashboard with stat cards and lists, 1100-1200px would be more appropriate.

4. **No sidebar layout on desktop.** The top-nav pattern is inherently limiting for an app with 8+ sections. Spotify's desktop uses a persistent left sidebar for exactly this reason.

5. **No page transition animations.** Navigating between pages is a hard cut — no fade or transition.

**Recommendations:**
- **Phase 1 (CSS-only):** Reduce mobile nav to 5 items max (Home, Contacts, Messages, Schedule, More). Put secondary items behind a "More" menu.
- **Phase 2 (Template + CSS):** Implement a left sidebar for desktop (280px fixed) with the current items grouped semantically:
  - **Primary:** Home, Messages, Contacts, Schedule
  - **Business:** Deals, Campaigns, Scores
  - **System:** Reminders
- **Phase 3:** Replace HTML entity icons with inline SVGs (Lucide icon set recommended — open source, consistent, 24px grid).

```
+--[ SIDEBAR (280px) ]--+--[ MAIN CONTENT ]------------------+
|                        |                                     |
|  CALLOWAY              |  Good afternoon, Sarah              |
|                        |                                     |
|  Home           (icon) |  +------+ +------+ +------+ +----+ |
|  Messages    3  (icon) |  | Msgs | |Shows | |Appvl | |Cntc| |
|  Contacts       (icon) |  +------+ +------+ +------+ +----+ |
|  Schedule       (icon) |                                     |
|                        |  Needs Your Approval                |
|  BUSINESS              |  +----------------------------------+
|  Deals          (icon) |  | Avatar  Name      Draft...  12m |
|  Campaigns      (icon) |  +----------------------------------+
|  Lead Scores    (icon) |  | Avatar  Name      Draft...   8m |
|                        |  +----------------------------------+
|  AUTOMATION            |                                     |
|  Reminders      (icon) |  Upcoming Showings                  |
|                        |  +----------------------------------+
|  ──────────────        |  | 2:30pm  123 Oak St  Jane  [conf]|
|  Sarah M.    Sign out  |  | 4:00pm  456 Elm St  Mike  [hold]|
+------------------------+  +----------------------------------+
```

### Dashboard

**File:** `app/templates/agent/dashboard.html` (127 lines)
**CSS:** `.card-grid`, `.stat-card`, `.section-title`, `.list-item`, `.timeline-item`

**Current State:**
- 5 stat cards in auto-fit grid (Messages, Showings, Need Approval, Active Contacts, Active Deals)
- Pending approvals list
- Upcoming showings timeline (inside a card)
- Recent messages list (up to 8)
- Active listings list

**Issues:**

1. **No personalized greeting.** Spotify opens with "Good morning/afternoon/evening" — a small touch that makes the interface feel human. The dashboard starts cold with "Today" (line 6).

2. **Stat cards lack visual hierarchy.** All 5 cards are uniform in size and weight. "Need Approval" is the most actionable metric, but it sits visually equal to "Active Contacts" which is informational only. Spotify uses visual weight (size, color, position) to create urgency hierarchy.

3. **5 stat cards in auto-fit grid causes awkward wrapping.** With `minmax(160px, 1fr)` (line 87), at certain viewport widths you get 3 cards on row 1, 2 on row 2 — visually unbalanced. Spotify avoids this by using fixed column counts per breakpoint.

4. **Mixed list patterns.** Pending approvals and Recent Messages use `.list-item` (card-per-row). Upcoming Showings uses `.timeline-item` inside a single `.card`. This inconsistency creates visual dissonance.

5. **No empty state for the overall dashboard.** If an agent is brand new with zero data, they see nothing. Spotify's empty states include illustrations and CTAs.

6. **"View all" links are styled as badges** (lines 58, 82): `class="badge badge-blue"`. Badges are for status indicators, not navigation. This conflates two interaction patterns.

**Recommendations:**

```
+--[ DASHBOARD ]-------------------------------------------+
|                                                           |
|  Good afternoon, Sarah                                    |
|  Here's your day at a glance.                             |
|                                                           |
|  +--[ NEEDS ATTENTION (accent card, wider) ]----------+  |
|  |  3 messages need your approval    [Review now ->]   |  |
|  +----------------------------------------------------+  |
|                                                           |
|  +----------+  +----------+  +----------+  +----------+  |
|  | 12       |  | 3        |  | 47       |  | 2        |  |
|  | Messages |  | Showings |  | Contacts |  | Deals    |  |
|  +----------+  +----------+  +----------+  +----------+  |
|                                                           |
|  Upcoming Showings                         See all ->     |
|  2:30pm  123 Oak St      Jane Cooper      [confirmed]     |
|  4:00pm  456 Elm St      Mike Johnson     [hold]          |
|                                                           |
|  Recent Messages                           See all ->     |
|  JC  Jane Cooper    Can we reschedule...       Mar 11     |
|  MJ  Mike Johnson   I'm interested in...      Mar 10     |
|                                                           |
|  Your Listings                                            |
|  123 Oak St  $450,000  3bd/2ba  [active]                  |
|  456 Elm St  $325,000  2bd/1ba  [pending]                 |
+-----------------------------------------------------------+
```

- Add time-of-day greeting with agent first name
- Elevate "Needs Approval" to a prominent accent-colored banner card at the top
- Use fixed 4-column grid for stat cards, 2-column on mobile
- Replace `.badge badge-blue` "View all" links with a text link styled as ghost button: `See all` with right arrow, in `#B3B3B3` that brightens on hover
- Add staggered fade-in animation for each section on page load

### Contacts

**File:** `app/templates/agent/contacts.html` (57 lines)
**CSS:** `.search-bar`, `.filter-row`, `.filter-chip`, `.list-item`

**Current State:**
- Full-width search bar with HTMX live search
- Filter chips for role (All, Buyers, Sellers, Leads, Past Clients)
- Secondary filter row for lead sources
- Contact list with avatar initial, name, phone/email, role badge, lifecycle badge, source badge
- Contact count at bottom

**Issues:**

1. **Contact list items are overloaded with badges.** A single contact row can display role badge + lifecycle badge + source badge + STOP badge (line 34-40). With 3-4 badges per row, the visual noise overwhelms the primary info (name, phone).

2. **No contact detail/click target.** The `.list-item` containers are not links — there is no `<a>` tag wrapping them (unlike conversations). Contacts are display-only, not interactive. This is a UX gap.

3. **Search bar has border and shadow** (lines 209-220), making it look like a form field rather than a navigation element. Spotify's search is borderless and pill-shaped.

4. **Filter chips have borders** (line 228: `border: 1px solid var(--border)`). Spotify's filter chips use background color differentiation only — inactive chips have a subtle dark background, active chips flip to white background with black text.

5. **Lead source filter uses inline style** (line 17: `style="margin-top:0;"`) to fix spacing — a sign the spacing system needs proper margin handling between filter rows.

6. **No sort control.** Contacts cannot be sorted by name, last contact date, or lead score. Spotify's library includes sort + view toggle.

**Recommendations:**
- Redesign badges: show only the most relevant badge per contact (role). Move lifecycle and source to a detail view.
- Make contact rows clickable — link to a contact detail page or expand inline.
- Restyle search as pill-shaped with icon, no border: `border-radius: 500px; border: none; background: #282828;`
- Restyle filter chips: remove border, use `background: #282828` inactive / `background: #FFFFFF; color: #000000` active (Spotify pattern).
- Add sort dropdown (alphabetical, recent, lead score).

### Conversations

**File:** `app/templates/agent/conversations.html` (35 lines)
**CSS:** `.search-bar`, `.list-item`

**Current State:**
- Search bar for messages
- List of conversations as clickable items with avatar, name, channel badge, preview, date

**Issues:**

1. **No unread indicator.** Unlike the dashboard's recent messages (which show an unread badge in `dashboard.html` line 94), the conversations list template has no unread count or visual differentiation for unread threads. All conversations look identical regardless of state.

2. **Channel badge is visually heavy.** The `badge-gray` next to each contact name (line 15) adds clutter. Channel (SMS, voice, etc.) is metadata, not primary info — it should be more subdued.

3. **No empty state CTA.** The empty state (line 28) says "No conversations yet." but offers no guidance. Spotify's empty states always include an actionable button.

4. **No filter chips.** Unlike Contacts (which has role/source filters), Conversations has no filtering by channel, status, or time period. A filter row for "All / SMS / Voice / Unread" would improve navigation.

5. **Preview text truncation is template-side** (line 17: `{{ c.last_message[:70] }}`). This should be CSS-side with `text-overflow: ellipsis` to be responsive. The current approach hard-codes 70 characters, which may be too long on mobile or too short on desktop.

**Recommendations:**
- Add unread visual state: bold contact name + green dot indicator for unread threads
- Demote channel badge: replace with a small icon (speech bubble for SMS, phone for voice) in `#535353`, placed inline with the contact name
- Add filter row: All / Unread / SMS / Voice
- Move text truncation to CSS (already partially done in `.list-preview` on line 140, but the template also hard-truncates)
- Empty state: add illustration and "Your AI assistant will handle incoming messages" with visual

### Conversation Detail

**File:** `app/templates/agent/conversation_detail.html` (47 lines)
**CSS:** `.chat-thread`, `.chat-msg`, `.chat-inbound`, `.chat-outbound`, `.chat-system`

**Current State:**
- Back link at top
- Contact card with larger avatar (48px), name, phone, channel
- Chat thread with inbound (gray), outbound (blue), and system (yellow) message bubbles
- Timestamps below each message
- Delivery status indicators (checkmarks, warning for failed)

**Issues:**

1. **Chat thread is left-aligned and narrow.** `.chat-thread { max-width: 600px; }` (line 160) with no centering means the conversation hugs the left edge on wide screens. In the proposed sidebar layout, this would look even more off.

2. **Outbound messages are blue** (line 174-175: `background: var(--accent); color: white;`). In a Spotify-inspired dark theme with green accent, outbound messages should use `#1DB954` or a subtler green tint — not blue.

3. **System messages use yellow background** (line 180: `background: var(--yellow-light)`). On a dark theme, this pastel yellow would clash severely. Needs to become a dark surface with muted text.

4. **Back link is plain text** (line 5: `<a href="/agent/conversations">&larr; Back to messages</a>`). Should be a proper back button with icon, matching the navigation pattern.

5. **Contact header card uses inline styles** (line 8: `style="margin-bottom:1rem; display:flex; align-items:center; gap:0.75rem;"`). These should be extracted to CSS classes.

6. **No message input.** The conversation is read-only — there is no compose box for the agent to manually send a message. Even if Calloway is AI-driven, agents need an override to type and send directly.

7. **AI indicator is subtle.** "AI" text in the timestamp (line 30) is easy to miss. This is critical information — agents need to quickly distinguish AI-generated vs. manually-sent messages.

**Recommendations:**
- Center the chat thread: `margin: 0 auto`
- On dark theme, outbound bubbles: `background: #1DB954` with `color: #000000` (black text on green, matching Spotify's button pattern — 10.9:1 contrast)
- System messages: `background: #282828`, `color: #A7A7A7`, subtle left green border
- AI-generated messages: add a small `AI` chip/badge next to the timestamp in `rgba(30, 215, 96, 0.15)` with green text
- Add a compose bar fixed to the bottom of the conversation view (even if it is v2 functionality)
- Replace inline styles with `.contact-header` class

### Schedule

**File:** `app/templates/agent/schedule.html` (67 lines)
**CSS:** `.filter-row`, `.filter-chip`, `.timeline-item`, `.timeline-time`

**Current State:**
- Filter chips: All / Confirmed / On Hold
- "Today" section with timeline inside a card
- "Upcoming" section with date + time in timeline
- Empty state with calendar emoji

**Issues:**

1. **No visual date separation.** Upcoming showings are listed chronologically but not grouped by date. If there are 3 showings on March 12 and 2 on March 13, they all run together. The `timeline-time` shows "Mar 12" with time below (line 41-42), but there are no date headers.

2. **No calendar view.** A timeline list works for "today," but agents think in weeks. A mini calendar or week-at-a-glance view would align better with how real estate agents plan their days.

3. **Timeline time column is too narrow.** `min-width: 60px` (line 199) can clip longer date/time combos like "Mar 12\n12:30pm". Should be 72-80px.

4. **Hold status badge includes expiry time inline** (line 24: `hold — expires {{ s.hold_expires_at... }}`). This creates very long badge text that breaks the visual rhythm. Expiry should be a separate line below the badge.

5. **Same filter chip issues as Contacts** — borders, light mode styling.

**Recommendations:**
- Group upcoming showings by date with date header rows styled as overline text (`12px, bold, uppercase, #A7A7A7, letter-spacing: 0.1em`)
- Add a week-view toggle (list vs. week) using Spotify's view-toggle pattern
- Increase `timeline-time` min-width to 80px
- Separate hold expiry: badge says "hold", subtitle says "expires 2:30pm"
- Timeline items on dark theme: remove `border-bottom` dividers, use spacing only

### Login

**File:** `app/templates/agent/login.html` (38 lines)
**CSS:** `.login-container`, `.btn-primary`, form inputs

**Current State:**
- Standalone page (does not extend `base.html`)
- Centered container at `10vh` from top, max-width 400px
- "Calloway" h1 + subtitle
- Phone input + verification code input
- "Sign In" full-width primary button
- Error/success messages use inline styles (lines 15, 19)

**Issues:**

1. **Light theme on login, dark theme on dashboard.** If we move the portal to dark mode, the login page must match. Currently it would be a jarring white-to-dark transition.

2. **No visual branding.** The login page is purely typographic — no logo mark, no illustration, no brand color. This is the first impression of the product. Spotify's login uses its logo prominently and brand green on the CTA.

3. **Error/success messages use inline styles** (lines 15, 19). These should be `.alert-error` and `.alert-success` component classes.

4. **"Sign In" button is blue** (inherits `.btn-primary` which is `--accent: #2563eb`). Should be green in the Spotify-inspired system.

5. **No loading/submitting state.** After clicking "Sign In," there is no visual feedback. The button should show a loading spinner or disabled state.

6. **Instructions text is tiny** (line 31: `font-size:12px`). "Text LOGIN to your Calloway number to receive a code" is critical instruction buried in small muted text below the code input.

**Recommendations:**
- Dark background matching the app (`#121212`)
- Add Calloway logo/wordmark in green (`#1ED760`) at the top center
- CTA button: green pill (`#1ED760`, black text, `border-radius: 500px`)
- Elevate the SMS instruction: put it in a card/callout with a message icon, larger text, before the code input
- Extract error/success to `.alert` component classes
- Add `disabled` state to submit button on form submission (prevent double-submit)

```
+--[ LOGIN ]-----------------------------+
|                                         |
|          (dark background)              |
|                                         |
|          CALLOWAY  (green wordmark)     |
|                                         |
|   Your AI assistant is working.         |
|   Sign in to see how.                   |
|                                         |
|   +--[ PHONE INPUT (pill) ]----------+ |
|   | +1 (555) 123-4567                | |
|   +----------------------------------+ |
|                                         |
|   +--[ INFO CARD ]-------------------+ |
|   | (msg icon) Text LOGIN to your    | |
|   |  Calloway number to get a code.  | |
|   +----------------------------------+ |
|                                         |
|   +--[ CODE INPUT (pill) ]-----------+ |
|   | 6-digit code                     | |
|   +----------------------------------+ |
|                                         |
|   [========= Sign in =========]        |
|   (green pill button, black text)       |
|                                         |
+-----------------------------------------+
```

---

## Quick Wins (CSS-only)

These changes require modifications only to `app/static/agent/style.css` — no template changes needed.

| # | Change | CSS Target | Effort |
|---|--------|-----------|--------|
| QW-1 | **Swap entire color palette to dark mode.** Replace all `:root` custom properties (lines 2-18) with the dark palette defined above. Every component that uses these variables will automatically update. | `:root` block, lines 2-18 | 30 min |
| QW-2 | **Remove all `border` and `box-shadow` from cards and list items.** On dark backgrounds, elevation comes from lighter surfaces, not strokes/shadows. Remove `border: 1px solid var(--border)` from `.card` (line 81), `.list-item` (line 115), `.search-bar` (line 213), and form inputs (line 272). Remove `box-shadow: var(--shadow)` from the same elements. | `.card`, `.list-item`, `.search-bar`, `input` | 15 min |
| QW-3 | **Pill-ify buttons and filter chips.** Change `.btn` border-radius from `10px` (line 255) to `500px`. Change `.filter-chip` border-radius from `20px` (line 225) to `500px`. Remove border from `.filter-chip` (line 228), use background color differentiation only. | `.btn`, `.filter-chip` | 10 min |
| QW-4 | **Pill-ify the search bar.** Change `.search-bar` border-radius from `var(--radius)` (12px, line 214) to `500px`. Remove border. | `.search-bar` | 5 min |
| QW-5 | **Fix badge shape.** Change `.badge` border-radius from `6px` (line 149) to `500px` for pill shape. | `.badge` | 5 min |
| QW-6 | **Increase content max-width.** Change `.agent-main` max-width from `900px` (line 74) to `1100px`. | `.agent-main` | 2 min |
| QW-7 | **Add transitions to all interactive elements.** Add `transition: all 200ms ease-out` to `.card`, `.list-item`, `.filter-chip`, `.badge`, `.btn`. Currently only `.nav-link` and `.list-item` have transitions. | Multiple selectors | 10 min |
| QW-8 | **Add hover scale to primary buttons.** Add `.btn-primary:hover { transform: scale(1.04); }` and `.btn-primary:active { transform: scale(0.98); }`. | `.btn-primary` | 5 min |
| QW-9 | **Fix typography scale.** Increase `.section-title` from `16px` / `1.1rem` (duplicated at lines 99-100 and 379-383) to `20px` / `700` weight. Increase `.list-name` from `14px` (line 138) to `15px` / `600` weight. | `.section-title`, `.list-name` | 10 min |
| QW-10 | **Add `@media (prefers-reduced-motion)` query.** Wrap all transitions and animations in a media query that respects user OS settings. | New media query at end of file | 10 min |
| QW-11 | **Fix duplicate CSS declarations.** `.section-title` is defined twice (lines 99-106 and lines 379-383) with conflicting `font-size` values (`16px` vs `1.1rem`). `.empty-state` is also defined twice (lines 236-241 and lines 384-388) with different padding values. Remove the duplicates at lines 379-388. | Lines 379-388 | 5 min |

**Estimated total for all quick wins: ~2 hours of CSS work.**

## Medium Effort

These require CSS changes plus minor template modifications.

| # | Change | Files Affected | Effort |
|---|--------|---------------|--------|
| ME-1 | **Replace HTML entity icons with SVG icon system.** Replace all `&#XXXX;` entities in `base.html` mobile nav (lines 37-67) with inline SVGs from Lucide icon set. Add `<svg>` sprites or individual inline icons. | `base.html`, `style.css` | 4 hours |
| ME-2 | **Add time-of-day greeting to dashboard.** Add a `<h1>` greeting ("Good morning, {{ agent.first_name }}") above the stat cards in `dashboard.html`. Pass `greeting` from the backend route. Style with `--text-display` (32px bold). | `dashboard.html`, route handler, `style.css` | 1 hour |
| ME-3 | **Elevate approval banner on dashboard.** Move pending approvals count into a full-width accent card at the top of the dashboard with a CTA button. Change from a list section to a prominent banner. | `dashboard.html`, `style.css` | 2 hours |
| ME-4 | **Add unread indicators to conversation list.** Add conditional bold styling for contact name and a green dot for unread conversations. Requires passing `unread` count from backend (already available in dashboard template, line 94). | `conversations.html`, `style.css` | 2 hours |
| ME-5 | **Extract inline styles to CSS classes.** `conversation_detail.html` lines 5, 8, 28, 33 use inline styles. `dashboard.html` lines 58, 82 use inline styles. `contacts.html` line 17 uses inline style. Create proper classes: `.back-link`, `.contact-header`, `.view-all-link`, `.timestamp-light`. | Multiple templates, `style.css` | 2 hours |
| ME-6 | **Add skeleton loading states for HTMX.** Add `.skeleton` and `.skeleton-shimmer` CSS classes with keyframe animation. Add `hx-indicator` skeleton templates for search results and list loading. | `style.css`, search-related templates | 3 hours |
| ME-7 | **Redesign filter chips to Spotify pattern.** Remove borders, use `background: #282828` inactive, `background: #FFFFFF; color: #000000` active. Ensure horizontal scrolling on mobile with `-webkit-overflow-scrolling: touch`. | `style.css`, minor template tweaks | 1 hour |
| ME-8 | **Add `.alert` component classes.** Extract inline error/success styles from `login.html` (lines 15, 19) into reusable `.alert-error` and `.alert-success` classes. | `login.html`, `style.css` | 30 min |
| ME-9 | **Add date group headers to schedule.** Group upcoming showings by date with an overline header ("WEDNESDAY, MAR 12"). Requires minor template logic and a new `.date-divider` CSS class. | `schedule.html`, `style.css` | 2 hours |

**Estimated total for all medium items: ~18 hours of work.**

## Full Redesigns

These require significant template restructuring, potential backend changes, and substantial new CSS.

| # | Change | Scope | Effort |
|---|--------|-------|--------|
| FR-1 | **Desktop sidebar navigation.** Replace `agent-header` top nav with a fixed left sidebar (280px). Restructure `base.html` to use a two-column grid layout: `<aside class="sidebar">` + `<main class="agent-main">`. Group nav items semantically (Primary, Business, Automation). Add collapsible/expandable behavior. The mobile bottom nav can remain but should be trimmed to 5 items with a "More" sheet. | `base.html`, `style.css`, all templates (to adjust layout context) | 16-24 hours |
| FR-2 | **Chat compose bar + manual override.** Add a fixed-bottom compose bar to `conversation_detail.html` with text input and send button. Requires a new API endpoint for agent-initiated messages, message delivery via existing Twilio integration, and real-time thread updates (HTMX polling or SSE). | `conversation_detail.html`, `style.css`, new API route, pipeline integration | 24-40 hours |
| FR-3 | **Contact detail view.** Contacts are currently not clickable. Build a contact detail page with: contact info card, conversation history, showing history, transaction history, lead score, lifecycle timeline, notes. This is a significant new page. | New template, new route, `style.css` | 24-32 hours |
| FR-4 | **Schedule calendar view.** Add a week-at-a-glance calendar grid alongside the existing timeline list. Include day columns, time slots, showing blocks positioned by time, and a toggle between list/calendar views. | `schedule.html` (major rewrite), `style.css`, possible JS for calendar interactions | 16-24 hours |
| FR-5 | **Onboarding empty states.** Design illustrated empty states for every page (dashboard, contacts, conversations, schedule). Each should include a relevant illustration/icon, explanatory headline, supportive body text, and an actionable CTA. Requires custom SVG illustrations or a consistent icon treatment. | All major templates, `style.css`, SVG assets | 8-16 hours |
| FR-6 | **Login page redesign.** Full dark-mode login with Calloway branding, green accent CTA, improved SMS instruction callout, loading states, and form validation feedback. May include a branded illustration or subtle background pattern. | `login.html`, `style.css` | 8-12 hours |

**Estimated total for all full redesigns: ~120-170 hours of work.**

---

## Priority Recommendation

**Immediate (Week 1):** QW-1 through QW-11 — the dark mode color swap and component shape updates. This single CSS file update transforms the entire visual identity toward the Spotify-inspired direction with zero risk of breaking functionality.

**Short-term (Weeks 2-3):** ME-1 (icons), ME-2 (greeting), ME-5 (inline styles), ME-7 (filter chips), ME-8 (alerts). These are the highest-impact medium items that reinforce the dark-mode foundation.

**Medium-term (Weeks 4-8):** FR-1 (sidebar navigation) is the single most impactful structural change. It unlocks better information architecture and aligns with the Spotify desktop pattern. Pair with ME-3 (approval banner) and ME-4 (unread indicators) for dashboard and conversation improvements.

**Longer-term (Weeks 8+):** FR-2 (compose), FR-3 (contact detail), FR-4 (calendar). These are feature expansions that build on the redesigned foundation.

---

*End of Agent Portal + Design System review. The Admin Console review is covered in a separate document.*
