# Calloway Digital Agency

## Agents

| Agent | Name | Role | Handle | Key Tools |
|-------|------|------|--------|-----------|
| **Chief of Staff** | Solomon | Decomposes requests, delegates, synthesizes outputs | @chief-of-staff | Agent, Read, Write |
| **Product Manager** | Mara | PRDs, user stories, backlog, technical requirements | @pm | Read, Write, Edit |
| **Engineering Lead** | Atlas | Architecture, implementation, code review, feasibility | @eng | Read, Write, Edit, Bash |
| **Program Manager** | Chronos | Project plans, risk registers, status reports, change control | @pgm | Read, Write, Edit |
| **Product Designer** | Lyra | User flows, wireframes, design systems, accessibility | @design | Read, Write, Edit |
| **Researcher** | Oracle | Competitive analysis, user research, tech evaluation, market research | @research | WebSearch, WebFetch, Read, Write |
| **Financial Analyst** | Aureus | Financial modeling, pricing, unit economics, budgeting, ROI | @finance | Read, Write, Edit |

## Agent Persona Files

| Agent | Persona File |
|-------|-------------|
| Solomon | [solomon-chief-of-staff.md](./solomon-chief-of-staff.md) |
| Mara | [mara-product-manager.md](./mara-product-manager.md) |
| Atlas | [atlas-engineering-lead.md](./atlas-engineering-lead.md) |
| Chronos | [chronos-program-manager.md](./chronos-program-manager.md) |
| Lyra | [lyra-product-designer.md](./lyra-product-designer.md) |
| Oracle | [oracle-researcher.md](./oracle-researcher.md) |
| Aureus | [aureus-financial-analyst.md](./aureus-financial-analyst.md) |

## Workflow Patterns

### New Project Kickoff

1. Research (competitive + user) runs in parallel
2. PM writes PRD based on research outputs
3. Engineering reviews for feasibility
4. PM finalizes PRD
5. Design + Architecture run in parallel
6. Program Manager builds project plan
7. Engineering implements
8. Launch coordination

### Feature Request

1. PM writes user stories
2. Engineering assesses feasibility
3. Program Manager evaluates timeline impact
4. Chief of Staff approves/rejects
5. Design → Build → Ship

## Interaction Map

```
                    ┌──────────────┐
                    │   Solomon    │
                    │ Chief of Staff│
                    └──────┬───────┘
                           │
          ┌────────┬───────┼───────┬────────┬────────┐
          │        │       │       │        │        │
     ┌────▼──┐ ┌───▼──┐ ┌─▼───┐ ┌▼─────┐ ┌▼──────┐ ┌▼───────┐
     │ Mara  │ │Atlas │ │Chro-│ │Lyra  │ │Oracle │ │Aureus  │
     │  PM   │ │ Eng  │ │ nos │ │Design│ │Resrch │ │Finance │
     └───────┘ └──────┘ └─────┘ └──────┘ └───────┘ └────────┘

  @pm ←→ @eng        Requirements ↔ Feasibility
  @pm  → @design     User stories → Design specs
  @pm  → @pgm        Scope → Timeline
  @eng → @pgm        Effort estimates → Project plan
  @research → @pm    Research → Requirements
  @research → @eng   Tech evaluation → Architecture
  @research → @finance Market data → Financial models
  @eng → @finance    Cost estimates → Financial models
  @finance → @chief-of-staff  Financial summaries → Decisions
```
