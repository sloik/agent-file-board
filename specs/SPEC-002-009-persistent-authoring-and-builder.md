---
id: SPEC-002-009
title: Persistent authoring drafts and visual form builder
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
nfrs: []
---

Owner authorized all suggested improvements that fit one static local webpage.
Direct implementation; no delegated workers, backend, automatic requests or
VoiceOver checks. Protocol/upstream and exact canonical v2.4.0 pin unchanged.

## Requirements and acceptance

1. Preserve unfinished report/form authoring, including invalid JSON, on reload
   using committed IndexedDB storage. Show loading and memory-only/failure states.
   Bounded named snapshots support explicit save/restore/export/import/delete;
   confirm replacement of working edits and deletion. No storage success claim
   before transaction completion. Corrupt/oversized imports never replace work.
2. Save composer attachment snapshots separately from working editor contents.
   Restore only explicitly on the same native board, revalidate the payload,
   never restore routing/sender/body or automatically post. Board changes never
   attach a saved payload to another board. Export/import is a local data-only
   backup, with a versioned envelope and documented privacy/storage limitations.
3. A visual builder creates and edits all 11 field kinds, IDs/labels/help/defaults,
   bounds/options, v3 field/option conditions, cross-field rules and editable table
   columns/baseline rows/row permissions. Add/remove/reorder fields/options/rows,
   safely change types, keep JSON and builder synchronized without silently
   dropping properties. Invalid JSON cannot be overwritten merely by opening the
   builder. Existing shared validator and preview remain authoritative; no new
   message grammar. All controls keyboard usable, EN/PL, phone/light/dark layout.
4. Provide a useful local workflow rehearsal/example and live-use checklist in
   docs and downloadable demo. Verify author → post → answer → review → CLI read
   and explicit follow-up with disposable data. Never label rehearsal as human
   adoption, fabricate human participation, or mutate an unspecified live board.
   Real human adoption remains explicitly unverified until independently observed.
5. Keep docs, examples, demo, screenshots, agent context and Cortex current.
   Meaningful reload/failure/import/builder/CLI/no-network regressions plus full
   existing checks. UI patch v2.4.2, retain canonical v2.4.0 and old tags/assets.

## State rationale

Owner commissioned the bounded local-only functionality. Acceptance checks above
are implementation/rehearsal checks; real owner adoption is not a completion
claim or a fabricated test requirement.

## Completion and evidence

UI ab980e49e7baa0e3c87a10b3cdc32ca887968b1e/v2.4.2 is published. Main CI
39169173193 and release CI39169173474 passed, including exact-tag checks, prepare
and publish. Canonical code/submodule/Latest remain v2.4.0; only public source
documentation/examples/skill and this specification change here.

225 JavaScript/browser +36 UI Python +114 canonical tests pass (375 unique).
Thirteen new authoring/builder tests cover actual reload (including invalid JSON),
named snapshots/cancellation/import/limits/cross-tab merge, unavailable/failed
storage, pending older writes versus oversized UTF-8 edits, explicit matching-
board attachment restore/foreign-board refusal, all11 fields, lossless existing
examples, conditions/rules/tables, real posting/CLI validation, inert source bytes,
phone light/dark layout and zero automatic external requests. Six locale cases
retain strict key parity and no-dead-key assertions. Existing disposable agent
question → viewer response → CLI read/follow-up coverage remains passing.

All five embedded build checks, version/release checks and diff checks pass.
172 local documentation file links and17 heading links resolve. Six tool images
and the actual extracted-demo image were regenerated/inspected. The demo packages
authoring-example.json and WORKFLOW-TRIAL.md with explicit manifest entries.
The active authoring status remains visible outside collapsed backup controls.
Current public UI/source docs and examples, agent skill, private agent contexts
and DevKB lesson are updated. Real owner adoption remains unverified; no live
owner board was touched, no agent listener/backend/network action was introduced.

All four externally downloaded assets and exact release note body are byte-
identical to the tested prepared package. Viewer1468946 bytes, SHA256
6e8163932168d9d825a8a9d12e1879fdc2dbbc91631be2db80a5294abec3874d.
DemoZIP1778040 bytes, SHA256
891f0ffda5a337b5261ad730a7e3b6ea4ee5523dd00871f80df2bde1956c43d1.
The previous2.4.1 demo was hash-verified and preserved before replacing the local
ignored ZIP. No old release/tag was changed or moved.
