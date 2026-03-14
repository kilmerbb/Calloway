# /update-docs — Living Documentation Updater

## Description
Run this skill after any code change that affects user-facing behavior, API endpoints, configuration, UI, or architecture. It ensures all documentation stays in sync with the codebase.

## When to Use
- After modifying any template in `app/templates/`
- After adding/removing/renaming API routes
- After changing console UI behavior
- After adding new features or tools
- After modifying configuration options in `app/config.py`
- After architecture changes (new services, workers, integrations)
- After any change that affects how an operator or agent interacts with Calloway

## What This Skill Does

### 1. Identify What Changed
Review the current git diff (`git diff HEAD~1 --stat` or staged changes) to understand what files were modified and what the changes do.

### 2. Update User Manual
**File:** `docs/user-manual.md`

Check if any changes affect the admin console UI, workflows, or features. If so, update the relevant sections of the user manual to match. The manual should always reflect exactly what a user sees and can do.

Key rules:
- Use "Customer" (not "Tenant" or "Agent") when referring to real estate agent accounts
- Be specific: describe what users see, what they can click, what happens when they do
- Include table column descriptions for any data tables
- Document new UI elements, buttons, filters, and tabs

### 3. Update Architecture Documentation
**File:** `docs/architecture-diagram.md`

If the change affects system architecture (new services, changed data flow, new integrations), update the architecture diagrams.

### 4. Update Engineering Standards
**File:** `docs/engineering-standards.md`

If the change establishes a new pattern or deviates from existing standards, flag it. Add new patterns to the standards doc if they should be followed going forward.

### 5. Update OpenAPI Spec
**File:** `docs/openapi-spec.yaml`

If API endpoints were added, modified, or removed, update the OpenAPI specification to match.

### 6. Update Research Briefs (if applicable)
**Directory:** `docs/research/`

If the change was informed by or invalidates a research finding, note it in the relevant research brief.

### 7. Commit Documentation Updates
After all documentation is updated, stage and commit the doc changes with a clear message:
```
docs: update [file] to reflect [change description]
```

## Output
Report what was updated and what was left unchanged (with reason).
