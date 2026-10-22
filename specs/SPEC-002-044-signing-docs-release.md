---
id: SPEC-002-044
title: Release signing adoption documentation as canonical 2.12.2
status: done
parent: SPEC-002
type: maintenance
created: 2026-10-22
nfrs: []
---

## Scope

Publish the reviewed signing adoption documentation with accurate release metadata.
Preserve existing tags/assets and runtime signing behavior.

## Acceptance Criteria

- [x] Align convention/changelog/upgrade manifest at 2.12.2 and retain upgrade support from released 2.12.1.
- [x] Review affected formal anchors; validate release metadata and upgrade behavior, and integrate through protected required checks.
- [x] Publish an immutable tested 2.12.2 tag/release and verify downloaded source against tagged public files before the viewer consumes it.


## Preparation

Release metadata, prior-version upgrade inputs and manifest were reviewed.
Local upgrade regression and exact tag consistency checks pass; formal anchors
remain current. Required PR checks and exact-tag matrix gate publication.


## Publication

Published [v2.12.2](https://github.com/sloik/agent-file-board/releases/tag/v2.12.2)
from protected merge4b398b6 after PR matrix/formal success and the exact-tag
Python3.10–13 matrix [39844431089](https://github.com/sloik/agent-file-board/actions/runs/39844431089).
All235files in the downloaded GitHub source ZIP match tagged archive bytes.
The viewer consumes this immutable release; older tags/assets were preserved.
