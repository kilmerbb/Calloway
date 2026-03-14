# Spotify Design Reference Brief for Calloway Admin Console

**Prepared by:** Oracle (Research)
**Date:** 2026-03-14
**For:** Lyra (Design) and Atlas (Engineering)
**Confidence Level:** High — based on current Spotify web player inspection data, Spotify's public design system articles, and verified clone project CSS

---

## Executive Summary

Spotify's design language is built on a layered dark surface system, restrained accent color usage, generous whitespace, and subtle motion. Their internal design system, **Encore**, uses semantic design tokens for colors, spacing, and typography. The Calloway console already has the right foundation (`#121212` background, `#181818` cards, `#1ED760` green accent). This brief provides the specific CSS values, patterns, and refinements needed to push the aesthetic further.

---

## 1. Color System

### Surface Elevation Scale (Dark Theme)

Spotify uses incremental brightness to create depth without shadows. Each layer is roughly `+18` hex values brighter.

| Token Name | Hex | Current Calloway | Usage |
|---|---|---|---|
| `--surface-base` | `#000000` | — | Sidebar deepest background |
| `--surface-0` | `#121212` | `--bg: #121212` | Main content background |
| `--surface-1` | `#181818` | `--bg-card: #181818` | Cards, player bar, nav bar |
| `--surface-2` | `#282828` | `--bg-hover: #282828` | Hover states, dialogs, popovers |
| `--surface-3` | `#333333` | `--border: #333333` | Elevated cards, active surfaces |
| `--surface-4` | `#404040` | — (add) | Button hover, input focus rings |
| `--surface-5` | `#535353` | — (add) | Selected/active row highlights |

### Text Colors

| Token | Hex | Usage |
|---|---|---|
| `--text-primary` | `#FFFFFF` | Headings, primary content |
| `--text-secondary` | `#B3B3B3` | Body text, descriptions, metadata |
| `--text-subdued` | `#A7A7A7` | Timestamps, tertiary info, placeholders |
| `--text-disabled` | `#6A6A6A` | Disabled states |

### Accent Colors

| Token | Hex | Usage |
|---|---|---|
| `--accent-green` | `#1ED760` | Primary CTA, active indicators |
| `--accent-green-hover` | `#1DB954` | Green hover/pressed state (slightly darker) |
| `--accent-green-muted` | `rgba(30, 215, 96, 0.1)` | Active nav item background tint |
| `--status-error` | `#E91429` | Error states, destructive actions |
| `--status-warning` | `#FFA42B` | Warnings, pending states |
| `--status-info` | `#2E77D0` | Informational badges |

### Gradient Patterns

Spotify uses gradients sparingly in the main UI:
- **Hero/header gradient:** Dominant color extracted from content, fading into `#121212` over ~300px. For Calloway, use a subtle green-to-transparent gradient on page headers:
  ```css
  background: linear-gradient(180deg, rgba(30, 215, 96, 0.08) 0%, transparent 300px);
  ```
- **Hover glow on cards:** Subtle radial gradient on hover:
  ```css
  .card:hover {
    background: linear-gradient(135deg, rgba(255,255,255,0.05) 0%, transparent 60%),
                var(--surface-1);
  }
  ```

**Recommendation for Calloway:** The existing color variables are well-aligned. Add `--surface-4: #404040` and `--surface-5: #535353` for richer interactive states. Consider making the sidebar background `#000000` (pure black) instead of `#181818` to match Spotify's deeper sidebar contrast.

---

## 2. Typography

### Font Stack

Spotify uses their proprietary **Spotify Mix** typeface (variable font, designed by Dinamo Typefaces, launched May 2024). Since it is not publicly available, use this fallback stack:

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

**Why Inter over the current system stack:** Inter is a free Google Font designed specifically for screens, with a humanist-geometric character similar to Spotify Mix. It supports variable weights and has excellent legibility at small sizes on dark backgrounds.

### Type Scale

Spotify uses a condensed type scale with clear hierarchy through weight more than size:

| Element | Size | Weight | Letter-Spacing | Line-Height |
|---|---|---|---|---|
| Page title (h1) | 24px | 700 (Bold) | -0.5px | 1.2 |
| Section header (h2) | 18px | 700 (Bold) | -0.3px | 1.3 |
| Subsection (h3) | 16px | 600 (Semibold) | 0 | 1.4 |
| Body text | 14px | 400 (Regular) | 0 | 1.5 |
| Small/meta text | 12px | 400 (Regular) | 0.2px | 1.4 |
| Label/overline | 11px | 700 (Bold) | 1.5px | 1.2 |
| Stat number (large) | 32px | 700 (Bold) | -1px | 1.1 |

### Key Typography Patterns

- **Tight negative letter-spacing** on large headings creates the punchy, modern feel
- **ALL-CAPS overlines** with wide letter-spacing for section labels (e.g., "ACTIVE TRIGGERS", "COST OVERVIEW")
- **Weight contrast** over size contrast — a 14px bold label next to 14px regular value creates hierarchy without size changes
- **No underlines on links** — color differentiation only, underline on hover

**Recommendation for Calloway:** Switch from system font stack to Inter (400, 600, 700 weights). Add negative letter-spacing to headings. Use all-caps overlines with `letter-spacing: 1.5px` for dashboard section labels.

---

## 3. Card Design

### Card Specifications

```css
.card {
  background: var(--surface-1);        /* #181818 */
  border-radius: 8px;                  /* Spotify uses 8px consistently */
  padding: 16px;
  border: none;                        /* No visible borders — depth via bg color */
  transition: background-color 0.3s ease;
}

.card:hover {
  background: var(--surface-2);        /* #282828 */
}
```

### Key Card Patterns

| Property | Value | Notes |
|---|---|---|
| Border radius | `8px` | Consistent across all cards |
| Padding | `16px` or `20px` | Standard internal spacing |
| Border | `none` | Depth from background color layers, NOT borders |
| Shadow | `none` on most cards | Spotify avoids box-shadow in dark mode |
| Hover transition | `background-color 0.3s ease` | Smooth background shift |
| Gap between cards | `16px` or `24px` | Grid gap |

### Card Grid Layout

```css
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 24px;
}
```

### Stat Cards (for Calloway Dashboard)

```css
.stat-card {
  background: var(--surface-1);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-card__label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text-subdued);
}

.stat-card__value {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -1px;
  color: var(--text-primary);
}
```

**Recommendation for Calloway:** Remove all card borders. Use `border-radius: 8px` universally. Use background-color transitions for hover instead of border/shadow changes. Remove box-shadows from cards.

---

## 4. Navigation (Sidebar)

### Current Spotify Sidebar Structure

```
[Logo / Brand]
─────────────
Home            (icon + label)
Search          (icon + label)
─────────────
Your Library    (section header with collapse toggle)
  ├─ Playlists  (filter chip)
  ├─ Artists    (filter chip)
  └─ Albums     (filter chip)

  [Scrollable list of items]
  Each item: thumbnail + title + subtitle
```

### Sidebar CSS Patterns

```css
.sidebar {
  background: #000000;              /* Pure black, not #181818 */
  border-right: none;               /* No visible border */
  border-radius: 8px;               /* Spotify wraps sidebar in rounded container */
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Sidebar sections are separate rounded cards */
.sidebar-section {
  background: var(--surface-1);     /* #121212 */
  border-radius: 8px;
  padding: 12px;
}

/* Nav items */
.nav-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  border-radius: 4px;
  color: var(--text-secondary);
  font-weight: 700;
  font-size: 14px;
  transition: color 0.2s ease;
}

.nav-item:hover {
  color: var(--text-primary);
}

.nav-item.active {
  color: var(--text-primary);
  background: transparent;          /* Active state uses text color, not bg */
}
```

### Spotify Sidebar Key Patterns

1. **Sidebar is split into sections** — each section is a rounded card on a black background
2. **Icons + labels side by side** — 24px icons with 16px gap to text
3. **Bold nav text** — `font-weight: 700` for all nav items
4. **No background highlight on hover** — just text color change from `#B3B3B3` to `#FFFFFF`
5. **Active item** — white text, no background fill (some implementations add a subtle left accent)
6. **Section headers** — "Your Library" with a collapse/expand chevron icon
7. **Filter chips** — small pill-shaped buttons to filter sidebar content

**Recommendation for Calloway:** Make sidebar background `#000000`. Wrap nav groups in rounded `#121212` sections. Remove the right border. Use text-color-only hover states. Add icons to every nav item (24px, use a consistent icon set like Lucide or Phosphor).

---

## 5. Tables & List Views

Spotify does NOT use traditional HTML tables. They use styled list rows that look like tables but are built with flexbox/grid.

### Track List Pattern (Adaptable to Calloway Data Tables)

```css
/* Table header */
.list-header {
  display: grid;
  grid-template-columns: 40px 1fr 1fr 100px;  /* # | title | detail | meta */
  padding: 8px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  color: var(--text-subdued);
  font-size: 12px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

/* Table row */
.list-row {
  display: grid;
  grid-template-columns: 40px 1fr 1fr 100px;
  padding: 8px 16px;
  border-radius: 4px;
  align-items: center;
  transition: background-color 0.2s ease;
}

.list-row:hover {
  background: rgba(255, 255, 255, 0.1);  /* Subtle white overlay, NOT a solid color */
}

/* Selected row */
.list-row.selected {
  background: rgba(255, 255, 255, 0.15);
}

/* Active/playing row */
.list-row.active .list-row__title {
  color: var(--accent-green);
}
```

### Key Table/List Patterns

| Pattern | Spotify Approach |
|---|---|
| Zebra striping | **Not used** — hover state provides differentiation |
| Row borders | **Not used** — clean, borderless rows |
| Row hover | `rgba(255, 255, 255, 0.1)` overlay |
| Row height | `52px` for standard rows, `56px` for rows with subtitles |
| Column alignment | Left-aligned text, right-aligned numbers/timestamps |
| Header separator | Single `1px` border with `rgba(255, 255, 255, 0.1)` |
| Row padding | `8px 16px` horizontal |
| Active row indicator | Text color changes to green, no row background change |

**Recommendation for Calloway:** Replace HTML `<table>` elements with CSS Grid-based list views. Remove zebra striping. Use `rgba(255, 255, 255, 0.1)` hover overlays. Highlight active items with green text, not background color.

---

## 6. Motion & Animation

### Core Transition Values

```css
/* Standard transitions */
--transition-fast: 150ms ease;        /* Hover states, small UI changes */
--transition-normal: 300ms ease;      /* Card hovers, panel opens */
--transition-slow: 500ms ease;        /* Page-level transitions, modals */
```

### Specific Patterns

| Element | Transition | Duration | Easing |
|---|---|---|---|
| Button hover | `background-color, transform` | 150ms | ease |
| Card hover | `background-color` | 300ms | ease |
| Nav item hover | `color` | 200ms | ease |
| Sidebar expand/collapse | `width, opacity` | 300ms | ease-in-out |
| Modal appear | `opacity, transform` | 200ms | ease-out |
| Toast notification | `transform, opacity` | 300ms | ease-out |
| Loading skeleton | `background-position` | 1.5s | linear (infinite) |

### Button Hover Micro-interaction

```css
.btn-primary {
  background: var(--accent-green);
  color: #000000;                    /* Black text on green — high contrast */
  border: none;
  border-radius: 500px;             /* Pill shape — Spotify's signature */
  padding: 8px 32px;
  font-weight: 700;
  font-size: 14px;
  transform: scale(1);
  transition: transform 150ms ease, background-color 150ms ease;
}

.btn-primary:hover {
  transform: scale(1.04);           /* Subtle scale-up */
  background: var(--accent-green-hover);
}

.btn-primary:active {
  transform: scale(0.98);           /* Press-down effect */
}
```

### Loading Skeleton

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--surface-1) 25%,
    var(--surface-2) 50%,
    var(--surface-1) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### Accessibility

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Recommendation for Calloway:** Add the three transition speed variables. Use pill-shaped (`border-radius: 500px`) primary buttons with scale hover. Add skeleton loading states for HTMX partial loads. Respect `prefers-reduced-motion`.

---

## 7. Information Density & Spacing

### Spotify's Spacing Scale

Spotify uses a **4px base grid** with an 8-point spacing system:

| Token | Value | Usage |
|---|---|---|
| `--space-1` | `4px` | Tight inline gaps, icon-to-text in compact views |
| `--space-2` | `8px` | Between related items (e.g., card internal elements) |
| `--space-3` | `12px` | Nav item padding, compact section gaps |
| `--space-4` | `16px` | Standard card padding, grid gaps |
| `--space-5` | `20px` | Generous card padding |
| `--space-6` | `24px` | Section gaps, card grid gaps |
| `--space-8` | `32px` | Page section dividers |
| `--space-10` | `40px` | Large section spacing |

### Information Density Principles

1. **Progressive disclosure** — Show summary first, detail on click/hover. Spotify shows track title + artist, but duration/album only appear on hover or in expanded views.
2. **Generous whitespace around groups, tight within** — Cards have 16-20px internal padding, but 24px gaps between them. Within a card, related items have 4-8px gaps.
3. **Fixed sidebar, scrolling content** — Sidebar remains stable; content area scrolls independently.
4. **No visual noise** — Avoid dividers between every item. Use spacing and subtle background shifts to separate groups.
5. **Consistent row heights** — All list rows are the same height (52px). This creates scannable rhythm.

### Applying to Calloway Dashboard

For the admin console, aim for this density:
- **Dashboard stats:** 4-column grid of stat cards at desktop, 2 at tablet, 1 at mobile
- **Data tables:** 52px row height, no row borders, hover overlay
- **Sections:** 32px gap between major sections, 16px within
- **Page padding:** `24px` on desktop, `16px` on mobile

---

## 8. Component-Specific Patterns

### Badges / Pills

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.badge--success { background: rgba(30, 215, 96, 0.15); color: #1ED760; }
.badge--warning { background: rgba(255, 164, 43, 0.15); color: #FFA42B; }
.badge--error   { background: rgba(233, 20, 41, 0.15); color: #E91429; }
.badge--neutral { background: var(--surface-2); color: var(--text-secondary); }
```

### Input Fields

```css
.input {
  background: var(--surface-2);      /* #282828 */
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 10px 12px;
  color: var(--text-primary);
  font-size: 14px;
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.input:hover {
  border-color: var(--surface-4);    /* #404040 */
}

.input:focus {
  border-color: var(--text-primary); /* White focus ring */
  background: var(--surface-3);
  outline: none;
}

.input::placeholder {
  color: var(--text-subdued);
}
```

### Toggle / Switch

```css
.toggle {
  width: 32px;
  height: 20px;
  background: var(--surface-5);      /* #535353 when off */
  border-radius: 500px;
  position: relative;
  transition: background-color 0.2s ease;
  cursor: pointer;
}

.toggle.active {
  background: var(--accent-green);
}

.toggle::after {
  content: '';
  width: 14px;
  height: 14px;
  background: #FFFFFF;
  border-radius: 50%;
  position: absolute;
  top: 3px;
  left: 3px;
  transition: transform 0.2s ease;
}

.toggle.active::after {
  transform: translateX(12px);
}
```

---

## 9. Summary: Changes from Current Calloway CSS

| Area | Current State | Recommended Change |
|---|---|---|
| Sidebar background | `#181818` (--bg-card) | Change to `#000000` |
| Sidebar border | `1px solid #333333` | Remove — use color contrast only |
| Card borders | Has borders | Remove all card borders |
| Card shadows | Some box-shadows | Remove — use background elevation only |
| Border radius | Mixed | Standardize to `8px` for cards, `4px` for inputs/rows |
| Font | System stack | Switch to Inter (Google Fonts) |
| Heading letter-spacing | Default (0) | Add negative letter-spacing (-0.5px to -1px) |
| Primary buttons | Rounded corners | Pill shape (border-radius: 500px) |
| Button hover | Background change only | Add `scale(1.04)` micro-interaction |
| Table rows | Traditional table styling | CSS Grid rows, no zebra stripes, rgba hover |
| Nav hover | Background color change | Text color change only |
| Status badges | Solid colored | Semi-transparent background + colored text |
| Section labels | Standard case | ALL-CAPS overlines with letter-spacing |
| Loading states | None / basic | Add skeleton shimmer loading |
| Reduced motion | Not handled | Add `prefers-reduced-motion` media query |

---

## Sources

- [Reimagining Design Systems at Spotify](https://spotify.design/article/reimagining-design-systems-at-spotify) — Encore architecture overview
- [Can I Get an Encore? Three Years On](https://spotify.design/article/can-i-get-an-encore-spotifys-design-system-three-years-on) — Token system and layout themes
- [Spotify Mix (Dinamo Typefaces)](https://abcdinamo.com/news/spotify) — Typography details
- [What Font Does Spotify Use in 2026?](https://sensatype.com/what-font-does-spotify-use-in-2026) — Font details and history
- [Spotify Design & Branding Guidelines](https://developer.spotify.com/documentation/design) — Official brand guidelines
- [Bringing the Spotify Heart to Life](https://spotify.design/article/bringing-the-spotify-heart-to-life) — Motion design principles
- [Spotify Colors (Eggradients)](https://www.eggradients.com/blog/spotify-colors) — Color usage analysis
- [Spicetify Themes](https://spicetify.app/docs/customization/themes) — Internal CSS token reference
- [DEV Community — Recreate Spotify](https://dev.to/tsanak/recreate-spotify-part-1-141) — Detailed CSS values from inspection
- [Spotify Player Color Palette](https://www.color-hex.com/color-palette/53188) — Verified hex values
- [How Spotify's Design System Goes Beyond Platforms (Figma Blog)](https://www.figma.com/blog/creating-coherence-how-spotifys-design-system-goes-beyond-platforms/) — Cross-platform design coherence
