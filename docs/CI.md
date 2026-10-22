# Required CI checks

The main-branch ruleset requires the GitHub Actions app15368 checks
`Python 3.10`, `Python 3.11`, `Python 3.12`, `Python 3.13`, and `bounded-models`.
The branch must be up to date; deletion/force-push protection and no-bypass policy
remain in force. Work on a branch and merge a PR after every required check passes.
Update the required context deliberately if a job or matrix version is renamed.
Daily `freshness` is an operational check, not a PR requirement.

Unit jobs have a15-minute bound. Dependency installation alone uses
`scripts/ci_retry.py` with two120-second attempts, request limits and owned
process-group cleanup. Formal preparation uses two60-second setup attempts inside
its existing180-second phase limit. Exhaustion fails verification. Signing
interoperability, all unit tests, original TLC cases, trace witnesses and mutation
controls remain mandatory and are not retried or weakened by the setup helper.

See [formal status](../formal/STATUS.md) for report freshness and exact proof limits.
The viewer repo owns its application package and read-only post-publication
asset/source and Chromium/Firefox live-checker verification; canonical source
continues to ship through immutable GitHub tags/source archives.
