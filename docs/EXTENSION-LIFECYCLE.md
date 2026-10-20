# Extension lifecycle and diagnostics — SDK 1.2 (unreleased)

An **extension** is a portable package. A **component** is one rendered instance
of a renderer from that extension. The canonical board defines the contract;
the chosen viewer implements its host policy. The stock viewer works offline.
No server, collector service, shell bridge or company integration is implied.

## Three independent operations

1. An external agent/script obtains a reading, for example by running a device
   CLI, and publishes a shared local artifact using `extension-state publish`.
2. Board refresh reads local files and resolves declared shared-artifact bindings.
   Every component pointing at that artifact receives the same resolved state.
3. Component refresh recalculates presentation using the host's **cached declared
   inputs** and current host time. It does not re-read files, execute provenance,
   run a CLI, request a new observation or write any artifact/message.

A manual component refresh is operation 3. Use ordinary board refresh for 2.
Uploaded boards retain copied-file snapshots until reselected. Local producers
can continue collecting without an open viewer; the viewer cannot collect while
closed. No change in a reading does not establish a disconnected device.

Recorded message readings remain immutable. The artifact's actual `observedAt`
controls freshness, while reported availability is separate. A tick, render,
successful refresh or log entry must never renew either. Show the last reading
alongside stale/unknown/disconnected/conflicting states without inventing zero.

## Portable declarations and negotiation

A package requesting refresh declares the `refresh` capability and SDK API
compatibility including `1.2.0`. At least one renderer must declare exactly:

```json
{"refresh":{"intervalSeconds":30}}
```

The interval is an integer from 30 through 86400 inclusive. Both `worker` and
`declarative` modes support this declaration. Unknown fields reject. A declaration
without the capability, or the capability without any declaration, rejects.
Intervals express best-effort presentation cadence, not a timing guarantee.

SDK 1.2 adds this known capability; a conforming SDK 1.2 custom host may decline
its runtime implementation. It must preserve baseline rendering, explicitly
report unsupported refresh and visibly explain that automatic refresh is
unavailable. It must not silently claim support. SDK 1.0/1.1 viewers cannot parse
the new declaration/capability and must reject the package as unsupported while
preserving the readable message fallback. Do not claim old viewers ignore it.
Existing packages restricted to exactly SDK 1.0 or 1.1 remain usable unchanged
when they do not request capabilities newer than those versions. `read-state`
requires at least SDK 1.1; `refresh` requires SDK 1.2. Respect exclusions and bounds.

SDK 1.2 renderers receive host-owned context in addition to their existing inputs:

```json
{
  "host": {
    "now": "2026-10-20T12:00:00.000Z",
    "refresh": {"supported":true,"automatic":true,"intervalSeconds":30}
  },
  "information": {}
}
```

`now` is host wall-clock time for this render, not source observation time.
`information` still contains only message-declared, scope-validated bindings and
requires `read-state`; otherwise it is empty. No filesystem handles, arbitrary
lookup, commands or network access are added. `supported:false` means the host
cannot perform component refresh; its interval is null and automatic is false.
An undeclared renderer also has no automatic interval. `automatic:false` may
reflect the viewer's local automatic-refresh preference; manual refresh remains
available when supported. The host must expose the effective setting honestly.

The stock viewer offers automatic component refresh independently of board file
polling. Turning one off does not imply the other is off. Third-party hosts may
choose their scheduling/retention policy within the portable safety rules below.

## Lifecycle

Initial mount calls `render(data,state,context)` with empty explicit state and no
refresh event. Worker refresh calls the existing `event` method with exactly:

```json
{"type":"refresh","reason":"timer","now":"2026-10-20T12:00:00.000Z"}
```

Reasons are `timer`, `manual`, `source-change`, and `resume`. `now` matches the
job's `context.host.now`. The returned state is passed into `render`. A
source-change caused by changed declared input remounts with empty state, invokes
one `source-change` event and renders against the new context. Do not dispatch a
second initial refresh. Module globals never persist; use returned SDK state.
Declarative renderers rebind their trees using the updated context instead of
executing an event method. Source changes still update views when timers are off.

All refresh events are presentation-only, including manual. An `answer` produced
by a refresh must not become a reply proposal. Only the existing explicit user
input/action path can propose replies, and sending still requires review and
fresh source checks. Refresh cannot bypass typed-reply invalidation rules.

The host owns scheduling, with one coalesced pending refresh per component and
bounded global concurrency. Jobs do not overlap. Host timers skip hidden or
unmounted components; becoming visible permits one coalesced resume, not replay
of missed intervals. Disposal, source/context changes, board switch and approval
revocation cancel jobs and invalidate their results. A worker failure/timeout
stops its automatic work until explicit retry; no endless retry loop. User actions
must not fail just because a scheduled job occupies the renderer; queue/coalesce
without unbounded work. Timers in background tabs may be delayed, and a closed
page runs nothing. Refresh support never establishes producer liveness.

Stock policy retains the existing maximum eight active jobs, one-second deadline,
16 KiB returned state and 64 KiB complete result. Each job uses a fresh worker
terminated on its first result. Persistent plugin timers are not the lifecycle.
No unrestricted DOM, imports, network, origin storage or shell execution is added.

## Local structured diagnostics

SDK 1.2 custom code can call:

```js
BoardExtension.log({
  level: 'info',
  code: 'view-refresh',
  message: 'Presentation refreshed',
  fields: {reason: event.reason}
});
```

The entry has exactly required `level`, `code`, `message` and optional `fields`.
Levels are `debug`, `info`, `warn`, `error`. Code and field keys use the existing
NAME grammar: `[a-z][a-z0-9-]{0,63}`. Message is a nonempty string of at most 500
Unicode code points. Fields is a flat object with at most eight entries; values
are null, boolean, finite number, or a string of at most 200 Unicode code points.
Nested objects/arrays and arbitrary data dumps are unsupported.

The trusted bootstrap buffers at most 16 entries and 8192 UTF-8 JSON bytes per
job, returning them in optional `diagnostics` on the sole result/error envelope.
It reports dropped counts. The complete worker envelope remains at most 64 KiB.
There is no streaming log message channel. Invalid/excess entries are dropped
with bounded host diagnostics; valid rendering can continue. An oversized whole
result retains the normal protocol failure. Logging does not grant any capability
or file access. It is built into SDK 1.2 without a separate permission capability.

The host annotates records with its timestamp, exact renderer package hash,
renderer ID, ephemeral component/job IDs and actual event/reason. If useful it
may attach only declared artifact revision/heads, never arbitrary filesystem
context. Extension entries cannot supply or override host metadata. Display
`host` and `extension` origins distinctly. An extension-authored claim that a
command succeeded is not proof of collection, approval or fresh observation.

Host failures, invalid output and timeout records are independent of extension
logs. Buffered extension logs are lost if a job never returns, including a hard
timeout; the host's timeout record remains. Producer diagnostics stay external;
existing inert provenance can describe collection without becoming executable.

Stock viewer retention is tab-local memory, at most 500 records and 512 KiB,
with dropped counts and an explicit Clear action; board switching clears it.
The component Diagnostics action filters by exact package/component. Extensions
also exposes all local records. Filtering never changes what an entry means.
Explicit export previews the selected diagnostic records and downloads JSON containing the dropped count and selected entries;
there is no automatic upload, persistence, board write or telemetry. Keep raw
readings, message/reply bodies, secrets and personal paths out of diagnostic
messages/fields. Arbitrary extension text may still contain sensitive information;
review export before attaching it to a public issue. Diagnostics are inert text.

## Approval and package identity

Approval belongs to exact **whole package bytes**, not publisher name, version
label or only worker source. Changes to any package bytes can require fresh
browser-local approval. Copying the board never transfers it. Approved older
pinned renderers keep their approval; installing a different version does not
silently switch or revoke them. Declarative rendering needs no custom-code approval.

A host-owned compact **Review extension** indicator at the component marks an
otherwise available selected worker renderer whose code is unapproved. It opens
inspection of that exact renderer package, without approving it. Users can leave
it unapproved; retain the readable message and normal reply review. The indicator
is nonmodal and remains visible without repeatedly notifying. Missing, disabled,
incompatible, conflicting and failed states need separate accurate explanations.
Untrusted component content cannot draw over or spoof this host approval control.

## Copyable examples

Install `examples/extensions/example-approvals.afb-plugin.json` for its contract,
then either `lifecycle-worker.afb-plugin.json` or
`lifecycle-declarative.afb-plugin.json` as a renderer. They target the same
`com.example.approvals/request` contract. Inspect/install using the normal CLI,
select the renderer in the viewer, and approve exact bytes only for the worker.
The examples update presentation time, never a source reading. Worker source:

```js
BoardExtension.define({
  render(data, state, context) {
    BoardExtension.log({level:'debug', code:'render', message:'Rendering declared inputs'});
    return {type:'column', children:[
      {type:'heading', text:data.title},
      {type:'text', text:'View updated: '+context.host.now}
    ]};
  },
  event(event, data, state) {
    if(event.type==='refresh') {
      BoardExtension.log({level:'info', code:'view-refresh', message:'Presentation refreshed', fields:{reason:event.reason}});
      return {state:{lastReason:event.reason}};
    }
    return {state};
  }
});
```

Declarative drawing can use `{ "contextPath": ["host", "now"] }`. A real battery
component should bind `information.battery.latest` (declaring `read-state`), show
its actual observation/freshness/availability, and leave collection to an external
producer publishing its shared artifact. See [EXTENSIONS.md](EXTENSIONS.md).
For additional powers, create a [convention issue](https://github.com/sloik/agent-file-board/issues/new)
or [viewer/SDK issue](https://github.com/sloik/agent-file-board-ui/issues/new).
