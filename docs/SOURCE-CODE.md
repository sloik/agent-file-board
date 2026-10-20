# Source code and diffs

Use ordinary Markdown fences for portable source presentation. Set
`CONTENT-TYPE: text/markdown` and keep a short readable explanation outside the
block. Code and patches are recorded text: the viewer never executes code,
reads a displayed filename, runs Git or applies a patch.

````markdown
```python
def battery():
    return 90
```

```diff
--- a/device.py
+++ b/device.py
@@ -1,2 +1,3 @@
 def battery():
-    return 100
+    # Last known reading
+    return 90
```
````

The stock viewer2.8 provides one presentation across message Markdown, safe HTML
pre/code, existing report code blocks/report Markdown and extension components.
Code has explicit-language syntax highlighting and Copy source. A patch has
Unified, Side by side and Source views, plus Copy source. View choices are local
to the browser tab; they never change the recorded message or board files.

## Diff meaning and limits

Store an ordinary unified patch, including its `---`, `+++` and `@@` lines when
available. The viewer validates hunk counts and displays the supplied old/new
line numbers. Multiple files/hunks, new/deleted files with zero-count sides,
rename metadata and `\ No newline at end of file` markers are supported. Split
view pairs removal/addition runs in order and leaves unmatched sides empty; it
does not claim semantic line matching or generate a patch from two source files.

A short fragment containing only context (` `), removed (`-`) and added (`+`)
lines is also valid presentation. Its line numbers are unknown and remain blank.
The viewer labels it as a fragment instead of inventing numbers.

Structured diff presentation is limited to65536 UTF-8 bytes and2000 lines.
Malformed counts, unsupported binary/combined patches and larger inputs remain
readable in Source view with an explanation. No partial success or silent
truncation. Unsupported Git metadata likewise falls back to source. Authoring
tools should prefer ordinary `git diff --no-color` output; ANSI color sequences
are not a portable highlighting format. See Git's
[patch format reference](https://git-scm.com/docs/diff-format).

Copy source returns the original supplied component text, including its line
endings. Markdown/HTML readers first apply their standard text parsing rules;
copying a fenced block copies its rendered code content, not its surrounding
fences. If clipboard access fails, Source view remains selectable and a local
message explains the fallback. Source copy never implies file access.

## Languages and safe fallback

Use a language name such as `python`, `javascript`, `typescript`, `json`, `yaml`,
`bash`, `xml`/`html`, `css`, `java`, `cpp`/`c`, `csharp`, `go`, `rust`, `swift` or
`markdown`. Common aliases such as `js`, `ts`, `py`, `sh`, `yml`, `cs`, `rs` and
`md` work. Empty/unknown language hints show plain text. There is no automatic
language guessing or remote grammar loading. Explicit `text` means plain source.

Highlighting uses pinned local grammars. Work per block is bounded to16384 UTF-8
bytes; individual long lines beyond4096 characters fall back to plain text.
Container enhancement handles at most64 code blocks, with plain pre/code retained
after that. These are presentation limits, independent of message/report/worker
transport limits. Source remains literal even if the grammar cannot color it.

HTML may use `<pre><code class="language-python">…escaped source…</code></pre>`.
The reader may interpret only the language hint, removes all author classes, and
builds trusted presentation after sanitization. Raw source, language names and
filenames cannot provide CSS, IDs, event handlers, viewer controls or resource
loads. Highlighted token markup is sanitized as inert spans.

## Existing reports

Existing `code-block` report nodes keep their exact schema: `type`, `title`,
`code`. A filename-like title such as `device.py` can supply a language hint.
An ordinary unified patch beginning with its file header uses the shared diff
view. Use a report's existing `markdown` node for explicit fenced language/diff
hints. No report wire version or schema is changed by this feature.

## Extension SDK1.3

The `render` capability includes two new drawing nodes. Authors using them must
declare API compatibility starting at1.3.0; older hosts retain readable message
fallbacks. No new permission or code-execution capability is granted. Existing
exact SDK1.0/1.1/1.2 packages remain supported unchanged by the stock viewer.

```json
{"type":"code","text":"const value = 90;\n","language":"javascript"}
```

```json
{"type":"diff","text":"-return 100;\n+return 90;\n","language":"javascript"}
```

Both fields are required. `text` is a string of at most32768 Unicode code points;
`language` is a string of at most40 characters. Either may use the existing
`path`/declared `contextPath` bindings. An empty diff language allows filename
inference per file. All ordinary worker64KiB result/tree and declared-state rules
still apply. Both declarative and approved worker renderers use the same trusted
host presentation. The shared view controls only change local presentation;
they do not dispatch an extension reply/action event.

See `examples/source-code/review.md`, `examples/source-code/device.patch` and
`examples/extensions/source-review.afb-plugin.json`. That package contains both
renderer modes; selecting its worker still requires browser-local approval of
the exact package. Declared source state continues to follow the existing
[lifecycle contract](EXTENSION-LIFECYCLE.md).
