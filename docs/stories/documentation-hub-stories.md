# Documentation Hub — User Stories

**Feature:** Add a "Documentation" section to the admin console sidebar with sub-navigation for Research, API Docs, Architecture, Changelog, and Product documentation.

**Context:** Several markdown documentation files exist in `/docs/` but are only accessible on disk. This feature surfaces them inside the console UI so operators can browse documentation without leaving the admin interface. FastAPI already serves Swagger at `/docs` and ReDoc at `/redoc`.

**Date:** 2026-03-14

---

## Story 1: Documentation Sidebar Group

**As** an operator using the admin console,
**I want** a "Documentation" group in the sidebar with sub-items for each documentation section,
**so that** I can navigate to documentation pages without leaving the console.

### Acceptance Criteria

1. A new nav group labeled "Documentation" appears in the sidebar between the existing "Operations" group and the "Logout" button, separated by a `nav-divider`.
2. The group contains exactly 5 nav items in this order: Research, API Docs, Architecture, Changelog, Product.
3. Each nav item links to its respective console route (see Story 2).
4. The active nav item is visually highlighted when the user is on that page (uses the existing `active` class pattern).
5. Each nav item has an appropriate Unicode icon consistent with the existing sidebar style (single-character symbols like the current `$`, `♥`, `⚙`, `?` icons).
6. On mobile, the sidebar items behave identically to existing nav items (close sidebar on click, accessible via hamburger menu).
7. `aria-current="page"` is set on the active item, matching the existing accessibility pattern.

### Implementation Notes
- Edit `app/templates/console/base.html` to add the new nav group.
- Use `active_nav` values: `docs-research`, `docs-api`, `docs-architecture`, `docs-changelog`, `docs-product`.

---

## Story 2: Markdown Rendering Backend

**As** the system,
**I want** console routes that read markdown files from disk and render them as HTML,
**so that** documentation pages display formatted content inside the console layout.

### Acceptance Criteria

1. Five new GET routes are added to `app/api/console.py`:
   - `/console/docs/research` — renders the Research section
   - `/console/docs/api` — renders the API Docs section
   - `/console/docs/architecture` — renders the Architecture section
   - `/console/docs/changelog` — renders the Changelog section
   - `/console/docs/product` — renders the Product section
2. All routes require authentication (use `_require_auth` pattern).
3. Each route reads the relevant markdown file(s) from `/docs/`, converts to HTML, and passes the HTML content to a shared Jinja2 template.
4. Markdown-to-HTML conversion uses the `markdown` Python library (or similar lightweight library) with support for tables, fenced code blocks, and heading IDs.
5. If a markdown file is missing or unreadable, the page displays a user-friendly "Document not found" message instead of crashing.
6. The route passes `active_nav` and `page_title` to the template, consistent with all other console routes.

### Implementation Notes
- Add `markdown` to `requirements.txt` (with `tables` and `fenced_code` extensions).
- Consider a shared helper function like `_render_markdown(filepath)` that reads and converts.

---

## Story 3: Documentation Page Template

**As** an operator viewing a documentation page,
**I want** the markdown content rendered with styling consistent with the console's dark theme,
**so that** documentation is readable and visually cohesive with the rest of the admin interface.

### Acceptance Criteria

1. A single shared template `app/templates/console/docs.html` extends `base.html` and renders the converted HTML content.
2. The template applies CSS styling for markdown elements (headings, paragraphs, lists, tables, code blocks, inline code, blockquotes, horizontal rules) that matches the existing dark theme (Spotify-inspired, using CSS variables like `--bg-card`, `--border`, `--accent`, `--text`, `--text-muted`).
3. The styling reuses or extends the patterns from `manual.html` (`.manual` class styles for headings, tables, code, etc.) to maintain visual consistency.
4. Content is constrained to a readable max-width (800px), matching the manual page.
5. The template includes a heading area showing the page title and, optionally, a brief description passed from the route.

### Acceptance Criteria — Sub-Navigation

6. When a section has multiple documents (Research has 4 files, Architecture has 3, Product has 3), the template renders a tabbed or linked sub-navigation at the top of the page listing each document.
7. Clicking a sub-nav item loads that document's content. This can be implemented as:
   - (Option A) Query parameter `?doc=filename` on the same route, with HTMX swapping the content area, OR
   - (Option B) Separate sub-routes per document.
8. The first document in each section loads by default when no specific document is selected.

### Implementation Notes
- The `.manual` styles in `manual.html` are a strong starting point. Extract them into a shared class (e.g., `.markdown-body`) that both manual and docs pages use.
- For multi-document sections, query parameters with HTMX swap is the lighter approach.

---

## Story 4: Research Section Content

**As** an operator,
**I want** to browse research documents in the console,
**so that** I can reference competitive analysis, design references, and technical research without opening files on disk.

### Acceptance Criteria

1. The Research page (`/console/docs/research`) displays a sub-navigation listing all 4 research documents:
   - Competitive Landscape (2026-03)
   - HTMX/Jinja2/CSS/A11y Reference
   - Postgres Stack Reference (2025)
   - Spotify Design Reference Brief
2. Each document renders its full markdown content when selected.
3. The default document shown on page load is "Competitive Landscape."
4. Document titles in the sub-nav are human-readable (derived from filenames or document H1 headings, not raw filenames).

### Source Files
- `docs/research/competitive-landscape-2026-03.md`
- `docs/research/htmx-jinja2-css-a11y-reference.md`
- `docs/research/postgres-stack-reference-2025.md`
- `docs/research/spotify-design-reference-brief.md`

---

## Story 5: API Docs Section

**As** an operator,
**I want** to access the API documentation from the console sidebar,
**so that** I can view endpoint documentation without knowing the separate `/docs` URL.

### Acceptance Criteria

1. The API Docs page (`/console/docs/api`) embeds or links to the existing FastAPI Swagger UI.
2. Implementation must use one of these approaches (in order of preference):
   - (a) An iframe embedding `/docs` (Swagger UI) at full width/height within the console layout, OR
   - (b) A prominent link/button that opens `/docs` in a new tab, plus a link to `/redoc` as an alternative.
3. If using an iframe, the iframe fills the content area and is at least 80vh tall.
4. If using an iframe, a fallback "Open in new tab" link is visible above the iframe.
5. The page requires authentication (same as all console routes).

### Implementation Notes
- FastAPI's built-in `/docs` does not require console auth. This is acceptable since the Swagger UI is already publicly accessible. The iframe just makes it discoverable from the console.

---

## Story 6: Architecture Section Content

**As** an operator,
**I want** to browse architecture documentation in the console,
**so that** I can reference system architecture, audit findings, and engineering standards.

### Acceptance Criteria

1. The Architecture page (`/console/docs/architecture`) displays a sub-navigation listing 3 documents:
   - Architecture Diagram
   - Architecture Audit
   - Engineering Standards
2. Each document renders its full markdown content when selected.
3. The default document shown on page load is "Architecture Diagram."
4. Document titles in the sub-nav are human-readable.

### Source Files
- `docs/architecture-diagram.md`
- `docs/architecture-audit.md`
- `docs/engineering-standards.md`

---

## Story 7: Changelog Generation and Display

**As** an operator,
**I want** to view a changelog compiled from git history,
**so that** I can see what has changed in the system over time without running git commands.

### Acceptance Criteria

1. A changelog file is generated at `docs/changelog.md` by a script or management command that extracts meaningful entries from git history.
2. The generation script (`scripts/generate_changelog.sh` or similar):
   - Groups commits by date (newest first).
   - Filters out trivial commits (merge commits, typo fixes) where practical.
   - Formats output as markdown with date headings and bullet-point entries.
   - Can be re-run to update the changelog.
3. The Changelog page (`/console/docs/changelog`) renders the generated `docs/changelog.md`.
4. If `docs/changelog.md` does not exist, the page displays a message like "Changelog has not been generated yet" instead of an error.
5. The changelog content displays in reverse chronological order (newest first).

### Implementation Notes
- A simple `git log --pretty=format:...` piped through formatting is sufficient. This does not need to be a sophisticated semantic changelog.
- The script should be documented so operators can re-run it as needed.

---

## Story 8: Product Section Content

**As** an operator,
**I want** to browse product documents (PRDs, audits) in the console,
**so that** I can reference product requirements and audit findings.

### Acceptance Criteria

1. The Product page (`/console/docs/product`) displays a sub-navigation listing 3 documents:
   - PRD: Customer Detail Redesign
   - UX Audit
   - System Audit (2026-03-11)
2. Each document renders its full markdown content when selected.
3. The default document shown on page load is "PRD: Customer Detail Redesign."
4. Document titles in the sub-nav are human-readable.

### Source Files
- `docs/prd-customer-detail-redesign.md`
- `docs/ux-audit.md`
- `docs/audit-2026-03-11.md`

---

## Implementation Order

| Phase | Stories | Rationale |
|-------|---------|-----------|
| 1 | Story 2, Story 3 | Backend routes + shared template — foundation for all pages |
| 2 | Story 1 | Sidebar navigation — connects users to the new pages |
| 3 | Stories 4, 5, 6, 8 | Content sections (can be done in parallel) |
| 4 | Story 7 | Changelog — requires script creation + content generation |

**Total estimate:** 8 stories. All are read-only rendering of existing content. No database changes. No new external dependencies beyond the `markdown` Python library.
