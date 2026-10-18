---
id: SPEC-002-004
title: Complete pinned static OpenUI candidate coverage
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

## Authorization

Owner requested implementation of all28 remaining static candidates against the
existing pinned upstream eb20708b9cc41afced5625e99e6ce8ec2f8a5435 catalogue
(react-lang1.0.1/react-ui0.18.1). Direct work; no autonomous-loop installation.

## Requirements

- Preserve report v1/v2. Add version3 covering pie/donut, radial, radar, scatter,
  single stacked bars; carousel/modal; card-grid variants; icon/icon-text,
  metric comparison, tag blocks, Markdown, image/image-gallery/image-text.
- Update every one of28 static-candidate entries with its exact adapted mapping
  and constraints; keep the23 interaction-contract entries deferred. These are
  board adaptations, not full upstream props/program compatibility.
- V3 is bounded data:256KiB UTF-8 header,64 component nodes, depth4,16 children;
  existing text/series bounds remain. V1/v2 keep their16KiB header limit.
- Images are embedded canonical PNG data URIs only: decoded size<=64KiB,
  width/height<=1024 and cumulative report image pixels<=4194304. Validate PNG
  structure/CRC and reject URLs, SVG, unexpected MIME, malformed/trailing data.
  A decode failure remains readable and isolated. No external asset requests.
- Markdown uses the pinned renderer/sanitizer with a restricted static tag set,
  no active URLs/resources, scripts/styles, forms or event handlers.
- Carousel/modal state is local, keyboard operable and preserved across polling;
  modal opens only on an explicit click, closes normally and cleans up portals
  on report disposal. No forms, automatic navigation or new message writes.
- Bound nonnegative part/radial/radar data and signed scatter coordinates; full
  numeric data stays readable, including zero/degenerate charts. Guard empty,
  mismatched, nonfinite and oversize values in Python/browser consistently.
- Publish v3 schema, canonical CLI examples, illustrated documentation and safe
  metadata upgrades from2.1.0, preserving custom files and history with backups.

## Acceptance criteria

- Shared fixtures cover every new type and malformed resource/shape/size/depth
  case with Python/browser agreement; old-version rejections stay effective.
- Actual file-page native and read-only uploaded reports render every new type,
  decode valid images, and emit zero HTTP/other external requests. Malicious
  Markdown/resource data cannot activate controls or alter message files.
- All charts preserve complete numbers; carousel controls, modal close/Escape,
  polling, localization and unmount cleanup pass functional browser checks.
- Desktop/375px light/dark captures are inspected; wide content stays inside
  report scrollers. No VoiceOver checks are added or run.
- CLI v3 roundtrip/refusals, pristine2.1.0 upgrade/backup and full existing suites,
  embedded assets, source pins and release checks pass before publication.

## State rationale

Owner authorized the remaining static scope. Catalogue and runtime pins remain
unchanged; a new versioned data contract preserves old payload semantics.

## Browser decode evidence

Chromium accepted a structurally valid PNG containing a corrupt zlib stream:
`img.decode()` resolved and drawing produced transparent pixels. Therefore the
fallback regression explicitly dispatches the browser error event; it proves
per-image isolation when an error is reported, not rejection of all corrupt
pixel streams. Structural/CRC validation and real valid-image decoding have
separate shared/file-page coverage. No guarantee of complete PNG pixel validation
is added. Older schema patterns also double-escaped Unicode control exclusions;
correct their serialization and strict end anchor to match existing validators.

## Validation

111 canonical Python tests and177 UI JavaScript/browser tests pass locally.
178 shared metadata vectors cover v1/v2/v3. Native/upload,375px light/dark,
local controls, polling/focus/selection, localization, image bounds/structure,
Markdown sanitization and zero external requests pass. Four CLI-generated
file-page captures are inspected. Manifest and canonical release checks pass.
Feature implementation is complete; exact vendor pin and publication verification
follow as release operations without moving existing tags.
