---
id: SPEC-004
title: Additive offline extension packages and constrained renderer API
type: feature
status: in_progress
created: 2026-10-19
devkb_required: [python.md, frontend.md, agent-ui-protocols.md]
---

Owner authorized starting implementation after SPEC-003 research and Q&A.
Architecture: sibling UI docs/EXTENSIONS.md, Cortex1593. Owner later requested complete extension delivery under SPEC-004-002. Living
specifications are excluded and parked. No live owner board migration is authorized. Keep existing report/form meanings frozen.

Implement in reviewable stages. First deliver SPEC-004-001: local package,
compatibility, validation and agent-discovery foundation. Later stages add the
viewer installer/approval UI, declarative/worker SDK rendering, typed host reply
transport and historical compatible-renderer preferences. These later stages
remain required for the complete extension feature and are not claimed by the
foundation. All packages/contracts/assets remain local in the copied board.

The owner requires optional convention/UI facets, both rendering modes, exact
local approval of executable bytes, version upper bounds and exclusions,
readable fallback, local catalog, unchanged immutable history and additive host
entry points. Additional scope/powers require GitHub issues. Constrained SDK was
explicitly selected over unrestricted React DOM after actual egress probes.
