# Documentation Hub — Engineering Review

**Reviewer:** Atlas (Engineering Lead)
**Date:** 2026-03-14
**Stories Reviewed:** 8 (from `docs/stories/documentation-hub-stories.md`)

---

## Summary

All 8 stories are feasible as specified, with minor modifications and clarifications noted below. The approach is sound: read-only rendering of existing markdown files within the existing console layout, reusing established patterns (`_require_auth`, `_render`, `base.html` sidebar, `.manual` CSS). No database changes required. One new dependency (`markdown`) needed.

Key findings from codebase validation:
- **Sidebar structure confirmed.** `base.html` uses `nav-group` divs with `nav-divider` separators. Adding a new group follows the exact same pattern. The `active_nav` template variable drives highlighting.
- **`.manual` CSS confirmed.** `manual.html` has inline `<style>` with `.manual` class styles for headings, tables, code, lists, etc. These are a direct copy target.
- **`_require_auth` and `_render` patterns confirmed.** All console routes follow the same auth-check-then-render pattern. New routes slot in identically.
- **`markdown` library is NOT in `requirements.txt`.** Must be added.
- **All referenced source files exist on disk.** All 4 research files, 3 architecture files, and 3 product files are present and non-empty.
- **FastAPI `/docs` and `/redoc` are available** at default URLs (no overrides in `main.py`).
- **No `scripts/` directory exists** (only `scripts/seed.py` — actually it's at project root). Need to create `scripts/` for the changelog generator.

---

## Story-by-Story Review

### Story 1: Documentation Sidebar Group

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **File:** `app/templates/console/base.html`
- **Location:** Insert new `nav-divider` + `nav-group` between line 77 (end of Operations group) and line 79 (start of `nav-bottom`).
- **Pattern:** Exact same HTML structure as existing nav groups (lines 31-52, 56-77). Each item uses:
  ```html
  <a href="/console/docs/research" class="nav-item {% if active_nav == 'docs-research' %}active{% endif %}"
     {% if active_nav == 'docs-research' %}aria-current="page"{% endif %}
     title="Research documents and competitive analysis">
      <span class="nav-icon" aria-hidden="true">◎</span> Research
  </a>
  ```
- **`active_nav` values:** `docs-research`, `docs-api`, `docs-architecture`, `docs-changelog`, `docs-product` — as specified.
- **Icon suggestions** (single Unicode chars matching existing style):
  - Research: `◎` or `⊕`
  - API Docs: `⟁` or `⌘`
  - Architecture: `▣` or `⊞`
  - Changelog: `≡` or `☰`
  - Product: `◈` or `⊡`

**Tightened Acceptance Criteria:**
- AC 1: Specify the `aria-label` for the new `nav-group` role="group" — suggest `aria-label="Documentation"`.
- AC 5: Finalize specific Unicode icons before implementation (the story says "appropriate" but doesn't specify which). Include in the final spec.

**Risks:**
- None. This is a straightforward template edit. Mobile behavior is inherited from existing JS (lines 124-126 in `base.html` already bind click handlers to `.nav-item` elements).

---

### Story 2: Markdown Rendering Backend

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **File:** `app/api/console.py`
- **Dependency:** Add `markdown==3.7` (or latest 3.x) to `requirements.txt`. Extensions needed: `tables`, `fenced_code`, `toc` (for heading IDs).
- **Helper function:**
  ```python
  import markdown as md

  def _render_markdown(filepath: Path) -> str | None:
      """Read a markdown file and convert to HTML. Returns None if file missing."""
      try:
          text = filepath.read_text(encoding="utf-8")
          return md.markdown(text, extensions=["tables", "fenced_code", "toc"])
      except (FileNotFoundError, OSError):
          return None
  ```
- **Route pattern** (same for all 5 routes):
  ```python
  DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

  @router.get("/docs/research", response_class=HTMLResponse)
  async def docs_research(request: Request):
      auth = _require_auth(request)
      if isinstance(auth, RedirectResponse):
          return auth

      doc_name = request.query_params.get("doc", "competitive-landscape-2026-03")
      docs_map = {
          "competitive-landscape-2026-03": ("Competitive Landscape (2026-03)", DOCS_DIR / "research" / "competitive-landscape-2026-03.md"),
          "htmx-jinja2-css-a11y-reference": ("HTMX/Jinja2/CSS/A11y Reference", DOCS_DIR / "research" / "htmx-jinja2-css-a11y-reference.md"),
          # ... etc
      }
      selected = docs_map.get(doc_name, list(docs_map.values())[0])
      html_content = _render_markdown(selected[1])

      return _render(request, "docs.html",
          page_title="Research", active_nav="docs-research",
          doc_html=html_content,
          doc_title=selected[0],
          docs_list=[(k, v[0]) for k, v in docs_map.items()],
          current_doc=doc_name,
      )
  ```
- **Route URLs:** `/console/docs/research`, `/console/docs/api`, `/console/docs/architecture`, `/console/docs/changelog`, `/console/docs/product` — all under the existing `/console` prefix from the router.

**Tightened Acceptance Criteria:**
- AC 3: Specify that the `docs_map` dictionary in each route must whitelist allowed filenames. Do NOT accept arbitrary file paths from query parameters — this prevents path traversal. The `?doc=` parameter must be validated against the known keys.
- AC 4: Add `toc` extension to the list (generates `id` attributes on headings for anchor links). The story mentions "heading IDs" but only lists `tables` and `fenced_code`.
- Add AC 7: Markdown rendering must be synchronous (file I/O is negligible for files under 50KB). No need for async file reads — all source files are under 50KB.

**Risks:**
- **Path traversal:** If the `?doc=` parameter is not validated against a whitelist, an attacker could read arbitrary files. The whitelist approach above mitigates this. Flag as mandatory.
- **Large files:** `engineering-standards.md` is 47KB, which is the largest. Rendering is still fast for files this size. No concern.

---

### Story 3: Documentation Page Template

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **File:** `app/templates/console/docs.html` (new file)
- **Template structure:**
  ```html
  {% extends "base.html" %}
  {% block content %}
  <style>
  /* Extract from manual.html .manual styles, rename to .docs-content */
  .docs-content { max-width: 800px; line-height: 1.7; }
  .docs-content h1 { /* ... same as .manual h1 ... */ }
  /* ... all .manual rules copied to .docs-content ... */
  /* Additional: code block styling for fenced code */
  .docs-content pre { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; overflow-x: auto; }
  .docs-content pre code { background: none; padding: 0; }
  .docs-content blockquote { border-left: 3px solid var(--accent); padding-left: 1rem; color: var(--text-muted); margin: 1rem 0; }
  /* Sub-nav tabs */
  .docs-subnav { display: flex; gap: 0; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
  .docs-subnav a { padding: 0.5rem 1rem; color: var(--text-muted); border-bottom: 2px solid transparent; }
  .docs-subnav a.active { color: var(--accent); border-bottom-color: var(--accent); }
  .docs-subnav a:hover { color: #fff; }
  </style>

  <div class="docs-content">
    <h1>{{ page_title }}</h1>
    {% if docs_list and docs_list|length > 1 %}
    <nav class="docs-subnav" aria-label="Document navigation">
      {% for key, title in docs_list %}
      <a href="?doc={{ key }}" class="{% if key == current_doc %}active{% endif %}">{{ title }}</a>
      {% endfor %}
    </nav>
    {% endif %}

    {% if doc_html %}
    {{ doc_html | safe }}
    {% else %}
    <p style="color: var(--text-muted);">Document not found.</p>
    {% endif %}
  </div>
  {% endblock %}
  ```

**Tightened Acceptance Criteria:**
- AC 2: Add `pre` and `blockquote` styling — the `.manual` styles in `manual.html` do not include these, but markdown files will generate them (fenced code blocks, blockquotes). Must be styled for dark theme.
- AC 3: Clarify — do NOT refactor `manual.html` to share styles in this phase. Duplicating the CSS into `docs.html` is acceptable and lower risk. Refactoring the manual page is out of scope. The styles are only 15 lines of CSS.
- AC 6-8: Recommend Option A (query parameter `?doc=filename`) without HTMX — a simple full-page reload is sufficient for document switching since the pages are static content. Adding HTMX swap adds complexity with negligible UX benefit for static docs. If HTMX is desired later, it can be added as enhancement.

**Risks:**
- **XSS via `| safe`:** The `doc_html` is generated from trusted files on disk (not user input), so `| safe` is acceptable. If user-uploaded markdown is ever supported, this must be revisited. Add a code comment noting this assumption.

---

### Story 4: Research Section Content

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **Route:** `/console/docs/research` (defined in Story 2)
- **Source files verified — all exist:**
  - `docs/research/competitive-landscape-2026-03.md` (23KB)
  - `docs/research/htmx-jinja2-css-a11y-reference.md` (28KB)
  - `docs/research/postgres-stack-reference-2025.md` (24KB)
  - `docs/research/spotify-design-reference-brief.md` (19KB)
- **docs_map** dictionary with human-readable titles as shown in Story 2 tech spec.
- **Default doc:** `competitive-landscape-2026-03` (first key in the ordered dict).

**Tightened Acceptance Criteria:**
- AC 4: Titles should be hardcoded in the route's `docs_map`, not dynamically parsed from file content. Parsing H1 headings adds complexity and fragility for no real benefit since these files are known at development time.

**Risks:** None.

---

### Story 5: API Docs Section

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **Route:** `/console/docs/api`
- **Template:** Can reuse `docs.html` with a special case, or create a minimal `docs_api.html` template. Recommend a separate template since the content is fundamentally different (iframe vs. markdown).
- **File:** `app/templates/console/docs_api.html` (new file)
- **Iframe approach** (Option A — preferred):
  ```html
  {% extends "base.html" %}
  {% block content %}
  <div style="margin-bottom: 0.5rem;">
      <a href="/docs" target="_blank" rel="noopener" style="color: var(--accent);">Open Swagger UI in new tab ↗</a>
      &nbsp;|&nbsp;
      <a href="/redoc" target="_blank" rel="noopener" style="color: var(--text-muted);">ReDoc ↗</a>
  </div>
  <iframe src="/docs" style="width: 100%; height: 85vh; border: 1px solid var(--border); border-radius: 8px; background: #fff;"></iframe>
  {% endblock %}
  ```
- **FastAPI `/docs` confirmed available** — `main.py` does not override `docs_url` or `redoc_url`, so defaults (`/docs`, `/redoc`) are active.

**Tightened Acceptance Criteria:**
- AC 3: Specify iframe height as `85vh` (not 80vh) to fill the content area better, since the topbar takes ~60px.
- Add AC 6: The iframe `src` must point to `/docs` (relative URL), not an absolute URL, so it works across environments (localhost, staging, production).
- Add AC 7: Include `title="API Documentation"` attribute on the iframe for accessibility (screen readers).

**Risks:**
- **Swagger UI theme clash:** The Swagger UI has a white/light theme by default. Inside the dark console, this will be visually jarring. This is acceptable for v1 but worth noting. A future enhancement could apply a dark Swagger theme via CSS injection, but that is out of scope.
- **X-Frame-Options:** If the FastAPI app sets `X-Frame-Options: DENY` or CSP `frame-ancestors` headers, the iframe will not load. Verify middleware does not block same-origin framing. Current codebase does not appear to set these headers, so this should work.

---

### Story 6: Architecture Section Content

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **Route:** `/console/docs/architecture`
- **Source files verified — all exist:**
  - `docs/architecture-diagram.md` (29KB)
  - `docs/architecture-audit.md` (23KB)
  - `docs/engineering-standards.md` (47KB — largest file, still fine)
- **docs_map:**
  ```python
  docs_map = {
      "architecture-diagram": ("Architecture Diagram", DOCS_DIR / "architecture-diagram.md"),
      "architecture-audit": ("Architecture Audit", DOCS_DIR / "architecture-audit.md"),
      "engineering-standards": ("Engineering Standards", DOCS_DIR / "engineering-standards.md"),
  }
  ```

**Tightened Acceptance Criteria:** None needed — story is well-specified.

**Risks:**
- `architecture-diagram.md` may contain Mermaid diagrams or ASCII art. The `markdown` library does not render Mermaid. If the file uses Mermaid syntax, it will display as a code block (which is acceptable for v1). Note for future enhancement.

---

### Story 7: Changelog Generation and Display

**Feasibility:** Can do with modifications.
**Effort:** M (1-3 days)

**Technical Spec:**

- **Script:** `scripts/generate_changelog.sh` (new file). The `scripts/` directory does not exist — only `seed.py` at project root. Create `scripts/` directory.
- **Script implementation:**
  ```bash
  #!/usr/bin/env bash
  # Generate changelog from git history
  set -euo pipefail
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  OUTPUT="$REPO_ROOT/docs/changelog.md"

  echo "# Changelog" > "$OUTPUT"
  echo "" >> "$OUTPUT"
  echo "_Generated $(date -u '+%Y-%m-%d %H:%M UTC')_" >> "$OUTPUT"
  echo "" >> "$OUTPUT"

  git -C "$REPO_ROOT" log \
    --no-merges \
    --pretty=format:"## %ad%n- %s (%h)%n" \
    --date=short \
    | awk '!seen[$0]++' \
    >> "$OUTPUT"
  ```
  Note: The above is a starting point. Grouping commits by date with a single heading per date requires slightly more logic (pipe through a deduplication/grouping script).
- **Route:** `/console/docs/changelog` — renders `docs/changelog.md` using the same `_render_markdown` + `docs.html` template. No sub-nav needed (single document).
- **File:** `docs/changelog.md` will not exist initially. The route must handle this gracefully (AC 4).

**Tightened Acceptance Criteria:**
- AC 2: The script must be executable (`chmod +x`). Add a comment header documenting usage: `# Usage: ./scripts/generate_changelog.sh`
- AC 2 (modified): Simplify the "filter out trivial commits" requirement. Filtering merge commits is easy (`--no-merges`). Filtering "typo fixes" is subjective and fragile. Recommend: filter only merge commits in v1. Commit message quality is a process concern, not a script concern.
- Add AC 6: The script must work when run from any directory (use `REPO_ROOT` relative paths, not `pwd`-dependent paths).
- Add AC 7: The generated `docs/changelog.md` should be `.gitignore`d since it can be regenerated. Alternatively, commit it — this is a product decision. Recommend committing it so the console works without running the script in deployed environments.

**Risks:**
- **Git availability in production:** The script runs `git log`, which requires a git repo. In Docker/Railway deployments, the `.git` directory may not be present (common in production images). This means the script cannot be run in production. Two options:
  - (a) Generate changelog as part of CI/CD and commit the output (recommended).
  - (b) Run the script locally and commit `docs/changelog.md`.
  - Either way, the route itself just reads a static file — no runtime git dependency.
- **Large git history:** For a project with thousands of commits, the changelog could be very long. Consider limiting to the last 6 months or N commits (`--since="6 months ago"` or `-n 500`).

**Modifications Required:**
1. Create `scripts/` directory.
2. Decide whether to `.gitignore` the generated changelog or commit it.
3. Add `--since` or `-n` limit to prevent unbounded output.

---

### Story 8: Product Section Content

**Feasibility:** Can do as specified.
**Effort:** S (< 1 day)

**Technical Spec:**

- **Route:** `/console/docs/product`
- **Source files verified — all exist:**
  - `docs/prd-customer-detail-redesign.md` (36KB)
  - `docs/ux-audit.md` (35KB)
  - `docs/audit-2026-03-11.md` (14KB)
- **docs_map:**
  ```python
  docs_map = {
      "prd-customer-detail-redesign": ("PRD: Customer Detail Redesign", DOCS_DIR / "prd-customer-detail-redesign.md"),
      "ux-audit": ("UX Audit", DOCS_DIR / "ux-audit.md"),
      "audit-2026-03-11": ("System Audit (2026-03-11)", DOCS_DIR / "audit-2026-03-11.md"),
  }
  ```

**Tightened Acceptance Criteria:** None needed — story is well-specified.

**Risks:** None.

---

## Cross-Cutting Concerns

### Security
- **Path traversal prevention** is critical in Story 2. The `?doc=` parameter must be validated against a hardcoded whitelist. Never construct file paths from user input. This is flagged as a mandatory requirement.
- **XSS from `| safe`** — acceptable because source files are trusted (on-disk, not user-uploaded). Add a code comment documenting this assumption.

### Performance
- No concerns. All files are under 50KB. Markdown rendering is fast (<10ms). No caching needed for v1.
- If caching is desired later, `functools.lru_cache` on the rendered HTML (keyed by filepath + mtime) would be trivial to add.

### Testing
- Add at least one test per route verifying:
  1. Unauthenticated requests redirect to `/console/login`.
  2. Authenticated requests return 200 with expected content.
  3. Missing `?doc=` parameter falls back to default document.
  4. Invalid `?doc=` parameter falls back to default document (not 500).
- Test the `_render_markdown` helper with a known input.

### Dependency
- `markdown` library: well-maintained, pure Python, no native extensions. Current latest is 3.7. Pin to `markdown>=3.6,<4` for safety.

---

## Effort Summary

| Story | Title | Feasibility | Effort | Notes |
|-------|-------|-------------|--------|-------|
| 1 | Sidebar Group | ✓ As specified | S | Template edit only |
| 2 | Markdown Rendering Backend | ✓ As specified | S | 5 routes + helper function + new dependency |
| 3 | Documentation Page Template | ✓ As specified | S | New template + CSS |
| 4 | Research Section | ✓ As specified | S | Route config only (built on Story 2) |
| 5 | API Docs Section | ✓ As specified | S | Iframe template |
| 6 | Architecture Section | ✓ As specified | S | Route config only (built on Story 2) |
| 7 | Changelog | ✓ With modifications | M | Script creation + git-in-production concern |
| 8 | Product Section | ✓ As specified | S | Route config only (built on Story 2) |

**Total estimated effort:** 3-4 days for all 8 stories.

**Recommended implementation order** (agrees with story spec):
1. **Phase 1:** Stories 2 + 3 (backend + template foundation)
2. **Phase 2:** Story 1 (sidebar nav)
3. **Phase 3:** Stories 4, 5, 6, 8 (content sections — parallelizable)
4. **Phase 4:** Story 7 (changelog script + route)

---

## Mandatory Changes Before Implementation

1. **Add `markdown` to `requirements.txt`:** `markdown>=3.6,<4`
2. **Whitelist `?doc=` parameter values** in each route — do not construct paths from raw user input.
3. **Create `scripts/` directory** for changelog generator.
4. **Decide changelog git strategy:** commit the generated file, or `.gitignore` it and generate in CI.
