---
id: SPEC-003
title: Resolve offline extension architecture and runtime boundaries
type: research
status: in_progress
created: 2026-10-19
cortex_cites: [1592]
---

## Authorization

Owner requested research to close gaps in the agreed extension architecture.
Research and disposable browser probes only; no production extension implementation.

## Fixed owner decisions

- One package with optional convention/UI facets; declarative and custom compiled
  renderers both supported by the design. Plugins extend public entry points in
  the stock viewer; broader core behavior/capability requests become GitHub issues.
- Packages, contracts, guidance, examples, renderers and assets remain local in
  the copied board; no network/service/package install is needed to use them.
- Board enablement and local approval of exact custom-code version/bytes differ.
- Initial powers: render data and collect typed replies; trusted host validates
  and writes. Agents discover enabled contracts through a bounded local catalog.
- Supported convention/viewer API ranges may have upper bounds and exclusions.
- Required readable fallback. Retain exact historical contracts/renderers;
  compatible renderer substitution is explicit, reversible and viewer-local.
  Replacement renderers explicitly declare supported older contract versions.

## Acceptance

1. Use primary platform/library sources and actual file-page browser probes to
   establish loading, isolation, messaging, network and lifecycle limits. Record
   failures rather than assuming iframe sandbox implies offline containment.
2. Recommend package format, identity/digests, local import, installation/trust,
   registry/discovery, bounded cross-language validation, compatibility rules,
   history/renderer substitution and migration from current strict core contracts.
3. Evaluate arbitrary React iframe bundles against a worker/host-rendered option
   where needed. Distinguish ordinary offline operation from enforceable hostile-
   code confinement, including navigation and CPU exhaustion. Do not call an
   unsatisfied requirement solved; surface any owner tradeoff in one question.
4. Retain a source-grounded architecture/research document and reproducible probe
   evidence in repository docs, without shipping executable plugin support.

## Completion

Pending source research and disposable runtime evidence.
