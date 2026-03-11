# Spotify Design System (Encore) Reference for Calloway

**Prepared by:** Lyra, Product Designer
**Date:** 2026-03-11
**Purpose:** Reference document for adapting Spotify's Encore design system principles to Calloway's UI/UX (Jinja2 + HTMX, server-rendered dashboard).

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Color System](#2-color-system)
3. [Typography](#3-typography)
4. [Spacing & Layout](#4-spacing--layout)
5. [Component Patterns](#5-component-patterns)
6. [Dark Mode Approach](#6-dark-mode-approach)
7. [Mobile-First Patterns](#7-mobile-first-patterns)
8. [Empty States & Loading](#8-empty-states--loading)
9. [Accessibility Practices](#9-accessibility-practices)
10. [Summary: What Calloway Should Adopt](#10-summary-what-calloway-should-adopt)

---

## 1. Design Principles

Spotify consolidated its design principles to three core tenets in 2020. Encore, the internal design system, operationalizes these into component-level decisions.

### Relevant
> "Spotify is made for you -- it should feel personalized."

Present the right information at the right time, in the right context. Avoid one-size-fits-all experiences. Personalization is the core value proposition, not decoration.

### Human
> "While rooted in technology, it's all about people."

Dial up emotion when appropriate, stick to logic when needed. The experience should feel dynamic, intuitive, and conversational -- never overly clever, technical, or coldly functional.

### Unified
> "Everything designed looks and feels reassuringly Spotify."

Coherence across products builds familiarity and trust. Follow the design system; start by reusing, not reinventing. A user should recognize the product regardless of platform or surface.

### Quality Framework: TUNE

Spotify evaluates experience quality using the TUNE framework:
- **T**one -- Is the voice right for the brand?
- **U**sable -- Is it accessible to everyone?
- **N**ecessary -- Is that functionality truly needed?
- **E**motive -- Does it feel good to use? Does it feel like somebody cares?

### Content-First Philosophy

The UI exists to serve content, not compete with it. Dark backgrounds recede so artwork and text take center stage. Every element justifies its existence by supporting the user's primary task.

### Configuration Over Customization

Encore favors configuration (constrained options that guarantee cohesion) over open customization (freedom that risks inconsistency). When both are needed, configuration is layered on top of customizable primitives.

### Calloway Adoption Notes

| Principle | Calloway Relevance |
|-----------|-------------------|
| Content-first | **High.** The console should let conversation data, lead info, and agent actions be the focal point. Chrome should be minimal. |
| Relevant / personalized | **High.** Each agent tenant sees only their data. The UI should surface what matters now (pending approvals, hot leads, upcoming showings). |
| Human tone | **High.** Calloway communicates with real estate agents who are not technical. UI copy should be warm, conversational, sentence case. |
| Unified / consistent | **High.** With HTMX partials and Jinja2 macros, define a set of configurable component templates rather than ad-hoc HTML. |
| TUNE framework | **Adopt** as a quality checklist for console feature reviews. |

---

## 2. Color System

### 2.1 Brand Colors

| Name | Hex | Usage |
|------|-----|-------|
| Spotify Green | `#1ED760` | Primary brand, logo, key CTAs |
| Black (brand) | `#191414` | Logo background (slightly warm, not pure black) |
| White | `#FFFFFF` | Primary text on dark, backgrounds in light mode |

### 2.2 UI Surface Palette

| Name | Hex | Usage |
|------|-----|-------|
| Background (base) | `#121212` | Main app background (near-black, not pure black) |
| Elevated Surface 1 | `#181818` | Cards, panels, slightly raised surfaces |
| Elevated Surface 2 | `#212121` | Hovered cards, active surfaces |
| Elevated Surface 3 | `#282828` | Higher elevation, active states |
| Subdued Surface | `#333333` | Progress bar tracks, dividers |
| Medium Gray | `#535353` | Secondary icons, inactive controls, disabled text |
| Subdued Text | `#A7A7A7` | Tertiary text, timestamps, metadata |
| Secondary Text | `#B3B3B3` | Subtitles, artist names, descriptions |
| Primary Text | `#FFFFFF` | Headings, song titles, primary content |
| UI Green (accent) | `#1DB954` | Shuffle, active indicators, progress fills |
| CTA Green | `#1ED760` | Primary CTA button backgrounds |

### 2.3 Functional Colors

| Name | Hex | Usage |
|------|-----|-------|
| Error Red | `#E91429` | Error states, destructive actions |
| Success Green | `#1ED760` | Success confirmations |
| Warning | `#FFA42B` | Warning states |

### 2.4 Semantic Token Architecture

Spotify's initial token system was non-semantic (raw values like `green-500`). They found this made safe changes impossible because the same token was used in unrelated contexts. They now invest heavily in **semantic tokens** that encode intent:

- **Non-semantic (raw):** `green-500`, `gray-800` -- raw palette values
- **Semantic (intent):** `background-base`, `text-primary`, `action-primary`, `surface-elevated` -- encode what the color means in context

This lets them change the value of `action-primary` without breaking `background-base`, even if both were originally the same hex.

Spotify built a **color-theming algorithm** that takes a few input values and generates an entire color theme with **guaranteed accessible contrast ratios**. This is how they handle contextual theming (e.g., album-colored backgrounds) without manually checking every combination.

### 2.5 Button Color Strategy: "Better in Black"

A significant design decision about green CTA buttons:

- **Old approach:** White text on a darkened "UI Green" (`#1DB954`) -- marginal contrast
- **New approach:** Black text on bright green (`#1ED760`) -- contrast ratio of **10.9:1**
- On gray backgrounds, Spotify Green achieves **9.7:1** contrast ratio
- Buttons also changed from UPPER CASE to sentence case, improving readability

### Calloway Adoption Notes

- **Adopt:** Semantic token naming as CSS custom properties (`--color-bg-base`, `--color-text-primary`, `--color-action-primary`). This is the single most valuable pattern from Encore.
- **Adopt:** The dark surface palette structure (base / elevated / muted / text hierarchy). Works well for dashboard UIs.
- **Adopt:** Separate functional colors for error/success/warning states.
- **Adapt:** Calloway's brand colors differ from Spotify's, but the token architecture is directly applicable. Define Calloway's palette, then map it through the same semantic layer.
- **Skip:** The color-theming algorithm (Calloway does not need per-content dynamic theming).
- **Skip:** Gradient storytelling (album-derived gradients are Spotify-specific).

### CSS Custom Properties Template

```css
/* Backgrounds */
--color-bg-base:         #121212;
--color-bg-elevated:     #181818;
--color-bg-elevated-2:   #212121;
--color-bg-highlight:    #282828;
--color-bg-press:        #333333;

/* Text */
--color-text-primary:    #FFFFFF;
--color-text-secondary:  #B3B3B3;
--color-text-subdued:    #A7A7A7;
--color-text-disabled:   #535353;

/* Brand */
--color-accent:          #1ED760;
--color-accent-ui:       #1DB954;

/* Functional */
--color-error:           #E91429;
--color-success:         #1ED760;
--color-warning:         #FFA42B;

/* Interactive */
--color-btn-primary-bg:    #1ED760;
--color-btn-primary-text:  #000000;
--color-btn-secondary-border: #727272;
--color-btn-hover-overlay: rgba(255, 255, 255, 0.1);
```

---

## 3. Typography

### 3.1 Typefaces

**Spotify's proprietary typefaces (not available for licensing):**

- **Circular** (2015-2024): Geometric sans-serif by Lineto. Clean, modern, friendly. Four weights plus italics.
- **Spotify Mix** (2024+): Custom variable font by Dinamo Typefaces. Variable weight, width, slant, and optical size axes.

**Spotify's recommended fallback stack for third parties:**
```
font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif;
```

### 3.2 Typographic Scale

Spotify's exact internal scale is proprietary, but UI analysis reveals this approximate system:

| Level | Mobile | Desktop | Weight | Usage |
|-------|--------|---------|--------|-------|
| Display | 28-32px | 48-64px | Bold/Black | Hero headers, featured content |
| H1 | 24px | 32px | Bold (700) | Page titles, section headers |
| H2 | 20px | 24px | Bold (700) | Card titles, subsection headers |
| H3 | 16px | 18px | Bold (700) | List item titles, song names |
| Body | 14px | 14-16px | Regular (400) | Descriptions, body content |
| Caption | 12px | 12px | Regular (400) | Timestamps, tertiary info |
| Overline | 11-12px | 12px | Bold, uppercase | Category labels, section tags |

### 3.3 Typography Principles

- **Hierarchy through weight, not just size:** Spotify differentiates elements by switching from Bold to Regular at the same size, not always by changing size.
- **Color as hierarchy:** Primary text `#FFFFFF`, secondary `#B3B3B3`, tertiary `#A7A7A7` -- three clear levels using the same font.
- **Sentence case** for all interactive UI text (buttons, labels, navigation). Never ALL CAPS except for overlines.
- **Line height:** Generous (approximately 1.3-1.5x), especially in body text, for scanability.
- **Letter spacing:** Slightly tighter on large headings, standard on body, slightly wider on overlines/uppercase.
- **Truncation:** Long text truncates with ellipsis rather than wrapping -- maintaining visual rhythm.
- **Baseline grid:** Line heights divisible by 4 for alignment to a 4pt baseline grid.

### Calloway Adoption Notes

- **Adopt:** System font stack for fastest load time and zero licensing cost. Alternatively, use **Inter** (open-source, similar geometric clarity to Circular).
- **Adopt:** The hierarchy principle of weight differentiation over size differentiation. Use 2-3 sizes with 2-3 weights rather than many distinct sizes.
- **Adopt:** Sentence case for all interactive UI text.
- **Adopt:** Three-level text color hierarchy (primary / secondary / subdued) as semantic tokens.
- **Adopt:** 4pt baseline grid for line-height alignment.
- **Adopt:** Truncation with ellipsis for conversation previews, contact names, listing addresses.
- **Skip:** Proprietary typefaces.
- **Skip:** Variable font axes (over-engineering for a dashboard).

---

## 4. Spacing & Layout

### 4.1 Base Unit: 8px

Spotify (and most modern design systems) uses an **8px base unit**:

| Token | Value | Common Usage |
|-------|-------|--------------|
| `--space-1` | 4px | Icon-to-text gap, tight inner padding |
| `--space-2` | 8px | Between icon and label, tight component padding |
| `--space-3` | 12px | Small margins, minor component gaps |
| `--space-4` | 16px | Standard card padding, list item gutters, mobile page margin |
| `--space-6` | 24px | Section spacing, card grid gaps, tablet page margin |
| `--space-8` | 32px | Major section gaps, mobile page top/bottom |
| `--space-10` | 40px | Large layout divisions |
| `--space-12` | 48px | Desktop page margins |
| `--space-16` | 64px | Major layout gaps, sidebar clearance |

### 4.2 Corner Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-xs` | 2px | Thumbnails in lists |
| `--radius-sm` | 4px | Cards on mobile, small devices |
| `--radius-md` | 8px | Cards on desktop, inputs, large devices |
| `--radius-lg` | 12px | Modal dialogs |
| `--radius-pill` | 500px | Buttons, chips, search input |
| `--radius-circle` | 50% | Avatars, play buttons |

### 4.3 Grid System

| Breakpoint | Columns | Page Margin | Card Gap | Notes |
|------------|---------|-------------|----------|-------|
| Mobile (< 768px) | 1-2 | 16px | 16px | Full-width list items |
| Tablet (768-1024px) | 3 | 24px | 16-24px | Sidebar may appear |
| Desktop (> 1024px) | 4-6 | 24-48px | 16-24px | Fixed left sidebar (280-350px), optional right panel |

Content max-width: approximately 1600px.

### 4.4 Layout Patterns

**Horizontal Shelf Pattern:**
- Section title (H2, bold) with optional "Show all" link aligned right
- Horizontally scrollable row of cards
- Last card partially visible ("peek") to indicate scrollability
- 16-24px gap between cards
- Multiple shelves stack vertically

**Responsive behavior:**
- Cards resize fluidly (grow/shrink to fill columns) rather than fixed sizes
- At narrow widths, multi-column grids become horizontally scrollable shelves
- Navigation transitions from bottom bar (mobile) to left sidebar (desktop)

### 4.5 Whitespace Philosophy

Spotify uses **generous whitespace internally but tight spacing between components**. Each card has room to breathe inside, but shelves and sections are packed closely to encourage scrolling and discovery.

### Calloway Adoption Notes

- **Adopt:** 8px spacing scale as CSS custom properties. This is foundational.
- **Adopt:** Consistent corner radius tokens.
- **Adopt:** Fluid grid using CSS Grid with `auto-fill` / `minmax()` rather than fixed column counts.
- **Adopt:** Left sidebar navigation for desktop console.
- **Adapt:** Spotify's generous internal whitespace may need to be tighter for Calloway's data-dense dashboard. Use the same scale but allow denser configurations for tables, message threads, and trigger lists.
- **Adapt:** The horizontal shelf pattern could work for "overview" screens (e.g., recent conversations, hot leads, upcoming showings as card rows) but not for detail views.
- **Skip:** The "peek" scroll pattern (less relevant for dashboard data).

---

## 5. Component Patterns

### 5.1 Buttons

Spotify's button system follows a clear three-tier hierarchy:

| Level | Style | Usage |
|-------|-------|-------|
| **Primary** | Pill-shaped, solid green (`#1ED760`), black text | Main CTA -- one per view |
| **Secondary** | Pill-shaped, 1px white/gray border, transparent background, white text | Supporting actions |
| **Tertiary / Ghost** | No border, no background, `#B3B3B3` text/icon only | Low-emphasis actions |
| **Icon Button** | Circular or no background, 24px icon standard | Toggle actions (like, shuffle) |

Key design decisions:
- **Black foreground on green:** 10.9:1 contrast ratio (far exceeding WCAG AA 4.5:1)
- **Sentence case** text, not uppercase
- **Reduced padding** (20-30% less than previous design) for space efficiency
- **Pill shape** (`border-radius: 500px`) for standalone CTAs
- **Hover:** scale up ~4% and brighten
- **Press:** scale down ~2% for tactile feedback

### 5.2 Cards

- **Primary content container** (playlists, albums, artists in Spotify; conversations, contacts, triggers in Calloway)
- Elevated surface color (`#181818`) differentiates from background (`#121212`)
- No visible border or shadow -- distinguished by surface color alone
- Square or rectangular artwork/thumbnail with rounded corners (4px mobile, 8px desktop)
- Title below in bold (1-2 lines max, truncated), subtitle in subdued text
- **Hover:** surface brightens slightly; action button fades in
- Spotify's "slots" pattern allows sub-components to be swapped while maintaining the card frame

### 5.3 Lists / Tables

- Fixed height rows (approximately 56-64px)
- Left: thumbnail (40x40px, 2px radius) or track number
- Center: primary text (white, bold) with secondary text beneath (gray, regular)
- Right: metadata (duration, date) in subdued text
- **Hover:** row background lightens subtly; action icons ("...") appear
- **Active/playing state:** primary text turns green; animated indicator replaces index
- Softly colored dividers between sections, not between every row

### 5.4 Navigation

| Platform | Pattern |
|----------|---------|
| Desktop | Persistent left sidebar (icon + label), resizable, with top bar (back/forward, profile) |
| Mobile | Bottom tab bar (3-5 items), fixed above mini-player |
| Sub-navigation | Tabs or filter chips within content area, not nested sidebars |

- **Active indicator:** Filled icon + white text (active); outlined icon + gray text (inactive)
- Platform-specific conventions are preserved (bottom tabs on mobile, sidebar on desktop)

### 5.5 Filter Chips

- Pill-shaped (`border-radius: 500px`), height ~32px
- Inactive: `#232323` background, white text
- Active: `#FFFFFF` background, black text
- Horizontally scrollable row
- Used for filtering content types (Music, Podcasts, Audiobooks)

### 5.6 Modals / Dialogs

- Focus is trapped within the modal when open
- Background dimmed with overlay
- Clear close affordance (X button or swipe-down on mobile)
- Focus moves into modal on open, returns to trigger element on close
- Corner radius: ~12px

### 5.7 Forms & Inputs

- Encore Web provides standard form controls (inputs, selects, checkboxes, radio buttons)
- Pill-shaped search input: `#242424` background, placeholder text in gray, search icon left
- Clear labels (not placeholder-only labels)
- Error states communicated through color + icon + text (multi-modal feedback, never color alone)

### 5.8 Progress Bar / Slider

- Track: thin horizontal bar in `#535353` (4px height)
- Fill: `#FFFFFF` (default) or `#1DB954` (on hover/interact)
- Knob: small white circle, appears on hover (desktop) or always visible (mobile)

### 5.9 Badges & Labels

- "NEW" badge: small, uppercase, colored pill
- "E" (Explicit): small gray rounded square with white "E", ~16px
- Notification dots: small colored circles on navigation icons

### Calloway Adoption Notes

- **Adopt:** Three-tier button hierarchy (primary/secondary/tertiary). One primary CTA per view.
- **Adopt:** Card pattern with elevated surface for conversation cards, lead cards, trigger cards.
- **Adopt:** List patterns for conversation history, message threads, contact lists.
- **Adopt:** Left sidebar navigation for desktop console; bottom tabs for mobile.
- **Adopt:** Filter chips for conversation status filters, trigger type filters, date range selections.
- **Adopt:** Modal focus trapping -- critical for HTMX-driven modals loaded via `hx-get`.
- **Adopt:** Multi-modal error feedback (icon + text + color, not color alone).
- **Adopt:** Badges for unread message counts, pending approval indicators, new lead markers.
- **Adapt:** Spotify's list items are music-focused; Calloway needs conversation-preview list items (contact avatar, last message snippet, timestamp, status indicator).
- **Skip:** Progress bar / slider (not relevant to Calloway's dashboard).
- **Skip:** Genre-specific card colors (not applicable).

---

## 6. Dark Mode Approach

### 6.1 Spotify's Dark-First Design

Spotify is **dark by default** -- there is no official light mode. The dark theme is the primary design. This serves functional purposes:

- Dark backgrounds make colorful content (album art) visually prominent
- Reduces eye strain in typical music-listening environments
- Creates a cinematic feel for media consumption

### 6.2 Surface Elevation Model

Dark mode uses **luminance to indicate elevation** (the inverse of light-mode shadow-based elevation):

| Level | Approximate Color | Meaning |
|-------|-------------------|---------|
| Background (base) | `#121212` | Lowest level, main canvas |
| Surface 1 | `#181818` - `#1E1E1E` | Slightly elevated (cards, panels) |
| Surface 2 | `#212121` | Elevated (active cards, popovers) |
| Surface 3 | `#282828` - `#333333` | Highest elevation (modals, dropdowns) |

Higher elevation = lighter surface.

### 6.3 Text on Dark Surfaces

| Role | Color | Effective Opacity |
|------|-------|-------------------|
| Primary text | `#FFFFFF` | 100% |
| Secondary text | `#B3B3B3` | ~70% |
| Subdued text | `#A7A7A7` | ~65% |
| Disabled text | `#535353` | ~33% |

### 6.4 Why Not Pure Black (`#000000`)

Spotify uses `#121212` (slightly warm near-black) rather than pure black:
- Reduces eye strain in prolonged use
- Allows elevation through lighter grays (impossible if starting at true black without visible increments)
- Creates a softer, more welcoming appearance

### Calloway Adoption Notes

- **Adapt:** Offer dark mode as an **option**, not the default. Real estate agents may prefer light mode for daytime use (showings, open houses, bright environments), but dark mode is valuable for evening/early-morning work.
- **Adopt:** Surface elevation model using luminance for dark theme. Define 3-4 surface levels as CSS custom properties.
- **Adopt:** Text opacity hierarchy (primary / secondary / subdued / disabled) using semantic tokens.
- **Adopt:** `#121212` base (not pure black) for dark theme.
- **Implementation:** Use CSS custom properties with `[data-theme="dark"]` and `[data-theme="light"]` selectors. Dark palette follows Spotify's luminance elevation; light palette uses shadows for elevation instead.

```css
/* Dark theme (Spotify-style) */
[data-theme="dark"] {
  --color-bg-base: #121212;
  --color-bg-elevated: #181818;
  --color-bg-elevated-2: #212121;
  --color-text-primary: #FFFFFF;
  --color-text-secondary: #B3B3B3;
}

/* Light theme (Calloway default) */
[data-theme="light"] {
  --color-bg-base: #FFFFFF;
  --color-bg-elevated: #F5F5F5;
  --color-bg-elevated-2: #EEEEEE;
  --color-text-primary: #121212;
  --color-text-secondary: #535353;
}
```

---

## 7. Mobile-First Patterns

### 7.1 Navigation Transformation

| Desktop | Mobile |
|---------|--------|
| Persistent left sidebar | Bottom tab bar (3-5 items) |
| Horizontal sub-tabs | Scrollable filter chips |
| Multi-column grid | Single or two-column layout |
| Hover states | Touch/press states |
| Back/forward arrows in top bar | System back gesture |

### 7.2 Touch Targets

- Minimum touch target: **44x44px** (Apple HIG) / **48x48dp** (Material Design)
- Spotify uses generous tap targets, especially for primary actions
- Interactive elements have sufficient spacing to prevent accidental taps
- Standard list item height: 56-64px (adequate touch target)

### 7.3 Responsive Behavior

- Content grids **collapse from multi-column to fewer columns**, not from grid to list
- Navigation collapses from sidebar to bottom bar
- Complex features consolidate into single views with sub-tabs/filters on mobile
- Library gets its own dedicated page with sub-tab filters

### 7.4 Device-Specific Sizing

- Artwork corners: **4px** radius on small/medium devices, **8px** on large devices
- Bottom nav bar height: ~56px
- Mini player bar: ~56px (sits above bottom nav)
- Filter chip height: ~32px
- Combined bottom chrome (nav + player): ~112px

### 7.5 Mobile Content Strategy

- Primary information visible without scrolling
- Secondary content available via scroll or tap-to-expand
- Long text truncated with ellipsis; full text accessible on tap
- Character accommodations for display: playlist name ~25 chars, artist name ~18 chars, track name ~23 chars

### Calloway Adoption Notes

- **Adopt:** Bottom tab bar for mobile console (Conversations, Contacts, Triggers, Settings -- 4 tabs).
- **Adopt:** 44px minimum touch targets for all interactive elements.
- **Adopt:** Responsive grid collapse pattern (reflow, not show/hide).
- **Adopt:** Scrollable filter chips for mobile sub-navigation (conversation status, trigger types).
- **Adopt:** 4px/8px adaptive corner radius.
- **Adapt:** Calloway's data-dense views need progressive disclosure on mobile. Prioritize the most critical information (unread count, lead status, next showing time) and use tap-to-expand for details.
- **Adapt:** The 112px combined bottom chrome (nav + player) is Spotify-specific. Calloway needs only the tab bar (~56px), freeing screen real estate.
- **Critical:** HTMX partials should serve mobile-optimized fragments. Use `hx-target` to swap smaller, mobile-appropriate content sections rather than full-page reloads.

---

## 8. Empty States & Loading

### 8.1 Skeleton Screens (Loading States)

Spotify uses skeleton screens extensively as its primary loading pattern -- **not spinners**:

- **Gray placeholder shapes** mimic the layout of real content (card outlines, text lines, circular avatars)
- **Shimmer animation** (left-to-right wave) indicates loading in progress
- Shimmer is preferred over pulse (opacity fade) because it feels faster perceptually
- Animation speed is subtle (~1.5s infinite loop)
- The app structure (navigation, bottom bar) is **always visible** even while content areas load

### 8.2 Skeleton Best Practices

- Show skeleton for **primary structural elements** (cards, text blocks, images)
- Do **not** skeleton-ize small elements (labels, buttons, form fields)
- Do **not** use skeleton for modals, toasts, or dropdown menus
- If content loads in under ~300ms, skip the skeleton entirely
- Use progressive loading: structure first, then text, then images
- The skeleton should match the expected layout dimensions to prevent layout shift

### 8.3 Shimmer Implementation (CSS-Only)

```css
.skeleton {
  background: linear-gradient(90deg, #212121 25%, #2a2a2a 50%, #212121 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Skeleton variants */
.skeleton-text   { height: 14px; width: 80%; margin-bottom: 8px; }
.skeleton-title  { height: 20px; width: 60%; margin-bottom: 12px; }
.skeleton-avatar { height: 40px; width: 40px; border-radius: 50%; }
.skeleton-card   { height: 200px; width: 100%; border-radius: 8px; }
```

### 8.4 Empty States

Spotify's empty state pattern:

1. **Illustration or icon** that relates to the empty context
2. **Clear heading** explaining the state ("Songs you like will appear here")
3. **Brief body text** with guidance on what to do next
4. **Primary action button** to resolve the empty state ("Find songs")
5. **Tone:** Encouraging, not apologetic. Consistent with the "Human" design principle.

### Calloway Adoption Notes

- **Adopt:** Skeleton screens for HTMX-loaded partials. When `hx-get` fires, show a skeleton in the target div via `hx-indicator`. Replace with real content on swap.
- **Adopt:** Shimmer animation (CSS-only, no JS required). Works perfectly with server-rendered HTML.
- **Adopt:** Progressive loading -- render page structure immediately (server-rendered), then fetch data-heavy sections via HTMX.
- **Adopt:** Empty state pattern for all zero-data screens:
  - No conversations: "No conversations yet. When clients text your Calloway number, they'll appear here."
  - No contacts: "Your contact list is empty. Import contacts or wait for inbound messages."
  - No triggers: "No scheduled follow-ups. Create a trigger to automate outreach."
  - No leads: "No active leads. Leads are created when new contacts reach out."
- **Skip:** Skeleton for sub-second loads. Calloway's server-rendered pages should load fast; only HTMX-fetched data panels need skeletons.
- **Skip:** Spinners. Follow Spotify's lead and use skeleton screens instead.

### HTMX Integration Pattern

```html
<!-- Skeleton shown while HTMX loads content -->
<div id="conversations-list"
     hx-get="/console/conversations"
     hx-trigger="load"
     hx-swap="innerHTML">
  <!-- Skeleton placeholder (shown during load) -->
  <div class="skeleton-row">
    <div class="skeleton skeleton-avatar"></div>
    <div style="flex: 1;">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton skeleton-text"></div>
    </div>
  </div>
  <!-- Repeat 5-8 skeleton rows -->
</div>
```

---

## 9. Accessibility Practices

### 9.1 Organizational Approach

Spotify has a dedicated accessibility squad ("Mandalorian") that collaborates with the Encore design system team. Their philosophy:

- **Bake accessibility into components** so product teams get it for free
- Where baking in is not possible, provide **comprehensive documentation and guidance**
- Go **beyond automated scans** -- manual testing with screen readers and keyboard navigation
- Think about accessibility as **user experience**, not compliance

### 9.2 Color Contrast

- A **color-theming algorithm** guarantees accessible contrast ratios for any generated theme
- Green-on-black button achieves **10.9:1** contrast (WCAG AAA level)
- "UI green" on gray backgrounds achieves **9.7:1** contrast ratio
- Multi-modal feedback: important information conveyed through color + icons + text -- **never color alone**
- WCAG targets: 4.5:1 minimum for body text (AA), 3:1 for large text and UI components

### 9.3 Keyboard Navigation

- Standard **tab navigation** for form elements and buttons
- **Arrow key navigation** for composite widgets (lists, grids, tab panels)
- Recognition that keyboard users include both screen reader users and motor-accessibility users -- different needs
- Preference for **native HTML elements** (`<button>`, `<input>`, `<select>`) which have built-in keyboard support

### 9.4 Focus Management

- **Modal focus trapping:** When a modal opens, focus moves into it and cannot tab out until dismissed
- **Focus restoration:** When a modal closes, focus returns to the element that triggered it
- **Visible focus indicators** on all interactive elements -- never `outline: none` without a replacement
- Testing specifically for focus behavior, not just static accessibility audits

### 9.5 ARIA Patterns

- Prefer **semantic HTML** over ARIA roles where possible
- Use ARIA only to fill gaps that semantic HTML cannot cover
- Caution against incorrect ARIA usage (wrong roles on div elements), which is **worse than no ARIA**
- Follow WAI-ARIA authoring practices for complex widgets (menus, dialogs, tab panels)
- `aria-live` regions for dynamic content updates

### 9.6 Screen Reader Support

- Components tested with major screen readers (VoiceOver, NVDA, JAWS)
- Alt text and `aria-label` requirements documented per component
- Live regions (`aria-live`) for dynamic content updates

### 9.7 Reduced Motion

Spotify implements an in-app "Reduced Animations" toggle:
- Reduces looping video and animated cards
- Replaces high-velocity transitions with subtle state changes
- Does not make the app static -- just calmer
- Respects `prefers-reduced-motion` media query

### Calloway Adoption Notes

- **Adopt:** Semantic HTML first, ARIA as supplement. Use `<button>`, `<input>`, `<dialog>`, `<nav>`, `<main>`, `<aside>` elements rather than styled divs.
- **Adopt:** Focus trapping for HTMX-loaded modals. When a modal partial loads via `hx-get`, use JS to trap focus and restore on close.
- **Adopt:** `aria-live="polite"` on HTMX target regions so screen readers announce content updates. This is **critical** for HTMX, which swaps DOM content dynamically.
- **Adopt:** Visible focus indicators (ring or outline) on all interactive elements.
- **Adopt:** Multi-modal feedback for all status changes (toast notifications should include icon + text + color).
- **Adopt:** Minimum contrast ratios: 4.5:1 for body text, 3:1 for large text and UI components.
- **Adopt:** `prefers-reduced-motion` support -- disable shimmer animations and transitions for users who prefer reduced motion.
- **Critical for Calloway:** HTMX swaps DOM content without full page reloads, which can confuse screen readers. Every `hx-target` container should have `aria-live="polite"` or use `hx-on::after-swap` to announce changes.

### HTMX Accessibility Pattern

```html
<!-- Mark HTMX target regions as live for screen readers -->
<div id="conversation-detail"
     aria-live="polite"
     aria-atomic="false"
     hx-get="/console/conversations/123"
     hx-trigger="click"
     hx-swap="innerHTML">
  <!-- Content swapped by HTMX will be announced -->
</div>

<!-- Modal with focus trapping -->
<dialog id="approval-modal" aria-labelledby="modal-title">
  <h2 id="modal-title">Approve message?</h2>
  <!-- Modal content -->
  <button hx-post="/approve/123" hx-target="#conversation-detail">
    Approve and send
  </button>
  <button onclick="this.closest('dialog').close()">Cancel</button>
</dialog>
```

---

## 10. Summary: What Calloway Should Adopt

### High Priority (Adopt Directly)

| Pattern | Why It Matters for Calloway |
|---------|----------------------------|
| Semantic color tokens as CSS custom properties | Enables theming, maintainability, dark mode support |
| 8px spacing scale | Consistent, predictable layouts across all console views |
| Three-tier button hierarchy (primary/secondary/tertiary) | Clear action hierarchy for approve/reject/dismiss flows |
| Card-based content containers | Natural fit for conversations, leads, triggers, showings |
| Skeleton screens for HTMX loads | Better perceived performance than spinners |
| Semantic HTML + ARIA live regions | Essential for HTMX accessibility |
| System font stack | Fast load, no licensing, works everywhere |
| Focus trapping for modals | Accessibility compliance for approval modals |
| Multi-modal error/status feedback | Inclusive design for varied conditions |
| Sentence case for UI labels | Approachable, professional tone |
| Empty states with guidance + CTA | Smooth onboarding for new agent tenants |
| Visible focus indicators | Keyboard accessibility |

### Medium Priority (Adapt to Calloway's Context)

| Pattern | Adaptation Needed |
|---------|-------------------|
| Dark mode | Offer as option, not default; agents work in varied lighting |
| Generous internal whitespace | Tighter for data-dense dashboard views (tables, threads) |
| Fluid grid layout | Use for overview cards; tables for detailed data |
| Mobile bottom tab bar | Map to Calloway's 4 console sections |
| Progressive disclosure on mobile | Collapse secondary info behind tap-to-expand |
| Filter chips | Use for conversation status, trigger type, date range filters |
| Horizontal shelf layout | Potential for "overview" dashboard (recent activity, hot leads) |

### Low Priority (Skip or Defer)

| Pattern | Why Skip |
|---------|----------|
| Color-theming algorithm | No per-content dynamic theming needed |
| System of systems governance | Single product, single team |
| Slots pattern for components | React-specific; Jinja2 macros + HTMX partials serve same purpose |
| Variable font (Spotify Mix) | Proprietary; system fonts sufficient |
| Component usage analytics | Premature for current scale |
| Gradient storytelling | Music/media-specific; not relevant to real estate dashboard |
| Reduced motion toggle in-app | Support `prefers-reduced-motion` CSS instead |

---

## Sources

- [Reimagining Design Systems at Spotify](https://spotify.design/article/reimagining-design-systems-at-spotify)
- [Can I Get an Encore? Three Years On](https://spotify.design/article/can-i-get-an-encore-spotifys-design-system-three-years-on)
- [How Spotify's Design System Goes Beyond Platforms (Figma Blog)](https://www.figma.com/blog/creating-coherence-how-spotifys-design-system-goes-beyond-platforms/)
- [Encore x Accessibility: A Balancing Act (Spotify Engineering)](https://engineering.atspotify.com/2023/03/encore-x-accessibility-a-balancing-act)
- [Multiple Layers of Abstraction in Design Systems (Spotify Engineering)](https://engineering.atspotify.com/2023/05/multiple-layers-of-abstraction-in-design-systems)
- [Better in Black: Rethinking Our Most Important Buttons](https://spotify.design/article/better-in-black-rethinking-our-most-important-buttons)
- [Design & Branding Guidelines (Spotify for Developers)](https://developer.spotify.com/documentation/design)
- [Spotify Brand Color Palette (Mobbin)](https://mobbin.com/colors/brand/spotify)
- [What Font Does Spotify Use? (FontsArena)](https://fontsarena.com/blog/what-font-does-spotify-use/)
- [How Spotify Leverages Design Systems (BTNG Studio)](https://www.btng.studio/insights/how-spotify-leverages-design-systems)
- [Spotify Colors: How Spotify Uses Color (Eggradients)](https://www.eggradients.com/blog/spotify-colors)
- [Spotify Color Palette (Design Pieces)](https://www.designpieces.com/palette/spotify-color-palette-hex-and-rgb/)
- [How Spotify's UX Is Helping Them Win (UX Collective)](https://uxdesign.cc/ux-ui-analysis-spotify-31f3855a1740)
