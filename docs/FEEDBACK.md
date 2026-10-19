# Feedback, bugs and feature requests

Reports from people and agents are welcome. You can describe a problem without
knowing its cause or designing a solution.

| Feedback about | Start here |
| --- | --- |
| File format/convention, CLI, board-loop, extension contracts or shared-state storage | [Canonical board feedback](https://github.com/sloik/agent-file-board/issues/new/choose) |
| Browser viewer/composer, notifications, native folder/upload, appearance or renderer SDK | [Viewer feedback](https://github.com/sloik/agent-file-board-ui/issues/new/choose) |

If you are unsure, pick the nearest symptom and say so. One issue is enough;
maintainers can help route it. Both repositories offer **Bug report** and
**Feature request or feedback** forms, plus a blank issue option.

For bugs, what happened versus what you expected is the useful starting point.
Add steps, a small example and versions if known. The viewer's version bar shows
viewer and board versions; browser/OS and native folder versus upload also help.
For features/general feedback, explain the problem and desired outcome. A
workaround or suggested approach is optional. Missing extension capabilities
belong here too: describe the workflow and the SDK/contract limitation rather
than bypassing the supported extension boundary.

Search existing open and closed issues first when possible. Link a related
report or add useful evidence to an existing match; lack of a duplicate search
should not stop useful feedback when you cannot access GitHub.

Issues are public. Share a minimal redacted excerpt or synthetic example instead
of whole boards, private conversations, credentials or company logs. Attaching
files is optional. Agents must distinguish a user's report from verified facts.

## Agents and offline use

The portable [board-feedback skill](../skills/board-feedback/SKILL.md) covers
routing, duplicate search, drafts and authorized submission. It works with Codex,
Claude Code and Copilot; GitHub CLI is optional. Copy the entire `board-feedback`
folder to the matching skill root (or symlink it locally):

| Harness | Example personal location |
| --- | --- |
| Codex | `~/.codex/skills/board-feedback/` |
| Claude Code | `~/.claude/skills/board-feedback/` |
| Copilot | `~/.copilot/skills/board-feedback/` or `~/.agents/skills/board-feedback/` |

Example: **Use board-feedback to draft a report about the composer losing my
selection after refresh.** Ask to **submit** it when you want it posted. The skill
respects an existing instruction to submit; installing it never starts a listener
or grants publication authority. Drafts work without a GitHub account or network.
A failed or uncertain submit is checked before retrying to avoid duplicate issues.

In the viewer, open Settings and choose **Send feedback** to open the GitHub issue
chooser explicitly. No background connection or automatic report is sent. If you
are offline, keep the title, description and relevant versions in a local note or
ask an agent for a Markdown draft, then submit when connected. This guide and the
skill are also included in the downloadable demo ZIP.
