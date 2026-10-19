# Local extension package foundation

The source CLI now supports inspecting, registering and discovering local
extension packages. This is the first implementation stage. It does **not**
execute renderers, add a posting header, or make the released viewer render
plugins. The convention remains 2.4.0 until a coordinated extension release.

The [complete architecture](https://github.com/sloik/agent-file-board-ui/blob/main/docs/EXTENSIONS.md)
keeps packages and assets in the copied board, with optional convention/UI
facets and declarative or constrained worker renderers. Future code approval is
local to each machine/profile and exact package bytes; it is never a board file.

## Try the source CLI

Use the sample `examples/extensions/example-approvals.afb-plugin.json` on a
disposable initialized board:

```sh
python3 boardctl.py extensions inspect examples/extensions/example-approvals.afb-plugin.json
python3 boardctl.py extensions install examples/extensions/example-approvals.afb-plugin.json --path /path/to/project
python3 boardctl.py extensions list --path /path/to/project
python3 boardctl.py extensions describe ARTIFACT_SHA256 --path /path/to/project
python3 boardctl.py extensions disable ARTIFACT_SHA256 --path /path/to/project
```

`inspect`, `list` and `describe` are read-only. Install and disable require those
explicit commands. Installation registers bytes; it never approves or executes
code. Reinstalling identical bytes re-enables them. Disable retains historical
packages. The CLI does not delete them or automatically fetch updates.

`list` returns a verified local catalog, including available, disabled,
incompatible, conflicting and unavailable snapshots. Available means the package
and declared schemas validate; renderer execution remains unavailable in this
stage. `describe` supplies schemas, guidance and examples. Guidance is package
content with the authority granted by the board owner; it cannot override an
agent's governing instructions. Ask for one package rather than loading every
definition into an agent prompt.

Output is bounded to 16 KiB by default. Explicit `--max-bytes` accepts 1024 through
4194304 bytes. Oversize output fails rather than silently truncating definitions.

## Artifact format 1

A single UTF-8 JSON object contains:

| Field | Meaning |
| --- | --- |
| `format` | Integer 1 |
| `id`, `version`, `name` | Reverse-domain namespace, stable numeric X.Y.Z release and display name |
| `description`, `publisher` | Optional descriptive claims; not authenticated identity |
| `compatibility` | Independent `convention` and `api` constraints |
| `capabilities` | Only `render` and `propose-reply`; declarations, never grants |
| `files` | Named entries with `encoding`, `data`, `sha256` |
| `convention` | Optional `contracts` list |
| `ui` | Optional `renderers` list |

At least one facet is required. Unknown fields are rejected. Maximum package
size is 4 MiB, 64 entries and 1 MiB decoded per entry. File names are bounded
lowercase relative logical names, without traversal or backslashes. Files use
UTF-8 strings or canonical base64; SHA-256 hashes their decoded bytes. The artifact
digest hashes the original complete file, including whitespace. Duplicate JSON
keys, invalid Unicode and nonfinite numbers are rejected. No archive extraction,
network schema or executable validator is involved.

A convention contract declares `id` under `package-id/name`, `version`, `schema`,
`guidance`, one to eight `examples`, and optional `answerSchema`. The latter
entries name package files. Schemas and example values are validated immediately.
Guidance is nonempty UTF-8 text. Up to 16 contracts may be declared.

The contract fingerprint is SHA-256 of UTF-8, with LF between these values and
no trailing LF: contract ID, version, schema file digest, guidance file digest,
answer-schema digest if present, then example digests in declared order. Any
change requires a new contract version. A renderer-only package release may
retain the exact same contract fingerprints. Conflicting retained definitions
for the same contract ID/version are rejected.

A UI facet declares up to 16 renderers with `id`, `mode` (`declarative` or
`worker`), `entry`, and `contracts`. Each target has `id` and `versions`. The
`render` capability must be declared. Entry presence and integrity are checked;
the drawing/program semantics belong to the later SDK stage. UI-only packages
can target an existing contract without redefining it. Importing worker source
does not run it, and no arbitrary React DOM runtime is supported.

## Compatibility and schemas

Extension API version is **1.0.0**. Each constraint is an object with `range` and
optional `exclude` list. Ranges are whitespace-separated comparisons, all of
which must match: `>=2.4.0 <3.0.0`, `<=2.6.1`, or an exact `=2.5.0` / `2.5.0`.
Exclusions list exact versions and take precedence. Up to eight comparisons
and 32 exclusions are supported. V1 rejects prereleases, leading zeroes,
wildcards, caret/tilde ranges and alternatives. Every numeric version component
has at most seven digits. Both convention and API must match to install.

The bounded schema dialect is deliberately smaller than JSON Schema:

- Mandatory `type`: string, number, integer, boolean, null, object or array.
- Optional boolean `nullable`; true accepts null before enum checks.
- Optional scalar `enum`, at most 64 values, matching the declared type/bounds.
- Strings require `maxLength` up to 10000 Unicode scalars, optional `minLength`.
- Numbers have optional minimum/maximum and must be finite within ±9007199254740991;
  booleans are not numbers. Integer values must be mathematically integral.
- Objects require `properties` (at most 64), `additionalProperties: false`, and
  optional unique `required` names. Property names are lowercase kebab identifiers.
- Arrays require `items` and `maxItems` up to 256, optional `minItems`.
- Schemas are limited to eight nested levels and 256 nodes. Unknown keywords,
  regexes, references and executable/cross-field rules are rejected in v1.

The shared-ready fixture `tests/fixtures/extension-parity.json` captures version,
Unicode, boolean/number, nullable, object and array edge cases. Future JavaScript
validation must pass it unchanged before it can claim the same dialect.

## Local storage and integrity

Installation retains exact bytes under:

```text
.agent-board/extensions/
  registry.json
  packages/<artifact-sha256>/package.afb-plugin.json
```

The registry contains only artifact hashes and enabled flags. Catalogs are
derived at read time; a cached catalog is not trusted. Copying this directory
with the board is sufficient for offline discovery. Expanded files and a cached
catalog may be added later as derived conveniences.

Exclusive local registry locks prevent competing CLI writes. Snapshot files are
published completely before an atomic registry replacement. A failed registry
write leaves prior registration intact; an unregistered complete snapshot can be
reused on retry. Locks are not distributed transactions across syncing replicas.
After a crashed process, inspect and remove its stale `.registry-lock` only after
establishing that no writer is active; the CLI does not guess ownership.

Managed symlinks, missing/corrupt bytes and conflicting identities fail closed.
Static path checks protect ordinary managed state; they do not authenticate
other filesystem writers or claim isolation from a hostile same-account process.
The board remains governed by filesystem access and collaboration policy.

## Creator scope

Plugins add behavior through defined public entry points. They do not override
core parser, routing, identity, statuses or write rules. More powers or different
core behavior require an issue:
[convention requests](https://github.com/sloik/agent-file-board/issues/new),
[viewer/SDK requests](https://github.com/sloik/agent-file-board-ui/issues/new).
No network, credentials or general filesystem capability exists in this API.
