# Calloway AI Agent Team

This directory contains the persona definitions and deliverables for Calloway's AI agent team. The team is orchestrated by **Solomon** (Chief of Staff), who decomposes requests, delegates to specialist agents, and synthesizes their outputs.

These personas are used by Claude Code via the `CLAUDE.md` configuration to spawn focused subagents for different types of work.

## Agents

| Handle | Name | Role | Persona File |
|--------|------|------|-------------|
| @chief-of-staff | Solomon | Orchestrator — decomposes, delegates, synthesizes | [solomon-chief-of-staff.md](solomon-chief-of-staff.md) |
| @pm | Mara | Product Manager — PRDs, user stories, requirements | [mara-product-manager.md](mara-product-manager.md) |
| @eng | Atlas | Engineering Lead — architecture, code, reviews | [atlas-engineering-lead.md](atlas-engineering-lead.md) |
| @pgm | Chronos | Program Manager — plans, timelines, risk | [chronos-program-manager.md](chronos-program-manager.md) |
| @design | Lyra | Product Designer — flows, wireframes, design system | [lyra-product-designer.md](lyra-product-designer.md) |
| @research | Oracle | Researcher — market, competitive, tech evaluation | [oracle-researcher.md](oracle-researcher.md) |
| @finance | Aureus | Financial Analyst — models, pricing, unit economics | [aureus-financial-analyst.md](aureus-financial-analyst.md) |

## Deliverables

The [deliverables/](deliverables/) subdirectory contains outputs produced by agents during project work (design specs, research reports, user stories, etc.).

## How It Works

See [AGENCY.md](AGENCY.md) for the full interaction map and workflow patterns.
