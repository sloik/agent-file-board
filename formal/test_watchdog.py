"""A monitor outage, disabled schedule or stale/foreign pass must never look green."""
from datetime import datetime, timedelta, timezone
import unittest
import copy
import json

import watchdog
import ci_dispatch
from unittest.mock import patch

# Actual read-only responses from core main43788084311/check133040165025.
# Its output.text was null. New protocol output below is explicitly a unit control.
REAL_API = json.loads(r'''
{
"check": {"id":133040165025,"name":"bounded-models","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","status":"completed","conclusion":"success","started_at":"2026-11-16T01:45:23Z","completed_at":"2026-11-16T01:51:38Z","external_id":"afb-oracle-source-43787992315-1","details_url":"https://github.com/sloik/agent-file-board/runs/133040165025","output":{"title":"Formal verification through Oracle","text":null},"app":{"id":15368,"slug":"github-actions"},"check_suite":{"id":118544587830}},
"final": {"id":43788084311,"run_attempt":1,"name":"Oracle formal 43787992315 attempt 1 completed","display_title":"Oracle formal 43787992315 attempt 1 completed","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_branch":"main","event":"workflow_run","workflow_id":419641431,"path":".github/workflows/formal-queue.yml","status":"completed","conclusion":"success","created_at":"2026-11-16T01:45:13Z","updated_at":"2026-11-16T01:51:43Z","run_started_at":"2026-11-16T01:45:13Z","check_suite_id":118544808523,"repository":{"id":1389483631,"full_name":"sloik/agent-file-board"},"head_commit":{"id":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109"}},
"final_attempt": {"id":43788084311,"run_attempt":1,"name":"Oracle formal 43787992315 attempt 1 completed","display_title":"Oracle formal 43787992315 attempt 1 completed","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_branch":"main","event":"workflow_run","workflow_id":419641431,"path":".github/workflows/formal-queue.yml","status":"completed","conclusion":"success","created_at":"2026-11-16T01:45:13Z","updated_at":"2026-11-16T01:51:43Z","run_started_at":"2026-11-16T01:45:13Z","check_suite_id":118544808523,"repository":{"id":1389483631,"full_name":"sloik/agent-file-board"},"head_commit":{"id":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109"}},
"source": {"id":43787992315,"run_attempt":1,"name":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","display_title":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_branch":"main","event":"push","workflow_id":391820399,"path":".github/workflows/formal.yml","status":"completed","conclusion":"success","created_at":"2026-11-16T01:44:22Z","updated_at":"2026-11-16T01:45:11Z","run_started_at":"2026-11-16T01:44:22Z","check_suite_id":118544587998,"repository":{"id":1389483631,"full_name":"sloik/agent-file-board"},"head_commit":{"id":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109"}},
"source_attempt": {"id":43787992315,"run_attempt":1,"name":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","display_title":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_branch":"main","event":"push","workflow_id":391820399,"path":".github/workflows/formal.yml","status":"completed","conclusion":"success","created_at":"2026-11-16T01:44:22Z","updated_at":"2026-11-16T01:45:11Z","run_started_at":"2026-11-16T01:44:22Z","check_suite_id":118544587998,"repository":{"id":1389483631,"full_name":"sloik/agent-file-board"},"head_commit":{"id":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109"}},
"source_workflow": {"id":391820399,"name":"Formal models","path":".github/workflows/formal.yml","created_at":"2026-10-21T16:42:17.000+02:00","updated_at":"2026-10-21T16:42:17.000+02:00","state":"active"},
"dispatcher": {"id":419641431,"name":"Oracle formal queue","path":".github/workflows/formal-queue.yml","created_at":"2026-11-16T02:44:21.000+01:00","updated_at":"2026-11-16T02:44:21.000+01:00","state":"active"},
"legacy": {"id":43282737470,"run_attempt":1,"name":"Formal models","display_title":"Merge pull request #33 from sloik/chore/spec-081-done","head_sha":"1e6c19058056b5d8dc58c04de4b6c027cf988d9a","head_branch":"main","event":"push","workflow_id":391820399,"path":".github/workflows/formal.yml","status":"completed","conclusion":"success","created_at":"2026-11-12T18:43:06Z","updated_at":"2026-11-12T18:46:04Z","run_started_at":"2026-11-12T18:43:06Z","check_suite_id":117209215006,"repository":{"id":1389483631,"full_name":"sloik/agent-file-board"},"head_commit":{"id":"1e6c19058056b5d8dc58c04de4b6c027cf988d9a"}},
"success_history": {
"push": [
{"id":43787992315,"name":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","display_title":"Formal preparation 11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_sha":"11828f59b8ffccdee23fdf8f68b7a05f77ecd109","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-16T01:44:22Z","updated_at":"2026-11-16T01:45:11Z","run_started_at":"2026-11-16T01:44:22Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":43282737470,"name":"Formal models","display_title":"Merge pull request #33 from sloik/chore/spec-081-done","head_sha":"1e6c19058056b5d8dc58c04de4b6c027cf988d9a","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-12T18:43:06Z","updated_at":"2026-11-12T18:46:04Z","run_started_at":"2026-11-12T18:43:06Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":43281868447,"name":"Formal models","display_title":"Merge pull request #31 from sloik/docs/related-repositories","head_sha":"226550c3b169a442f5862f763dd80267577a61c5","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-12T18:38:03Z","updated_at":"2026-11-12T18:42:10Z","run_started_at":"2026-11-12T18:38:03Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":43281149797,"name":"Formal models","display_title":"Merge pull request #32 from sloik/fix/spec-081-row15-clock","head_sha":"a3c6d49d5082212285f71eaa418c4566db7a068a","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-12T18:33:57Z","updated_at":"2026-11-12T18:37:05Z","run_started_at":"2026-11-12T18:33:57Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":41734802533,"name":"Formal models","display_title":"Merge pull request #30 from sloik/chore/spec-079-done","head_sha":"807d07ca1ac580eaa3e8bd7af2d11741899c9ebe","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-03T22:54:32Z","updated_at":"2026-11-03T22:58:44Z","run_started_at":"2026-11-03T22:54:32Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":41734008873,"name":"Formal models","display_title":"Merge pull request #29 from sloik/feat/subthreads-proof","head_sha":"5a2db3e5074fdc7a9e850bf3843cfc198fbe83e1","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-03T22:48:48Z","updated_at":"2026-11-03T22:52:57Z","run_started_at":"2026-11-03T22:48:48Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":41693990191,"name":"Formal models","display_title":"Merge pull request #28 from sloik/chore/spec-076-done","head_sha":"b98efce95391cb3a3d4ea0fdef1e465529796e46","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-03T18:27:27Z","updated_at":"2026-11-03T18:30:17Z","run_started_at":"2026-11-03T18:27:27Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":41692835569,"name":"Formal models","display_title":"Merge pull request #27 from sloik/feat/subthreads","head_sha":"bd52fb594e1890ef2986e1000d88edaf31d9122f","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-03T18:20:19Z","updated_at":"2026-11-03T18:22:41Z","run_started_at":"2026-11-03T18:20:19Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40290669471,"name":"Formal models","display_title":"Merge pull request #9 from sloik/renovate/major-github-artifact-actions","head_sha":"6a8fe97d5dbeb80e9ca94ccc707da573c355044a","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T08:12:33Z","updated_at":"2026-10-26T08:14:50Z","run_started_at":"2026-10-26T08:12:33Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40290248899,"name":"Formal models","display_title":"Merge pull request #8 from sloik/renovate/java-jdk-25.x","head_sha":"48bc3b83ac0ef781aba8a39d054d23771b377642","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T08:08:47Z","updated_at":"2026-10-26T08:11:40Z","run_started_at":"2026-10-26T08:08:47Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40289779681,"name":"Formal models","display_title":"Merge pull request #7 from sloik/renovate/python-3.x","head_sha":"c2a1a7790e2fe08f09f2ea5b482f6e7019de6530","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T08:04:32Z","updated_at":"2026-10-26T08:07:12Z","run_started_at":"2026-10-26T08:04:32Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40289173600,"name":"Formal models","display_title":"Merge pull request #6 from sloik/renovate/cryptography-50.x","head_sha":"10ea9ce05fd20c0e94de9e7b6d4b5a4168c64047","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T07:59:05Z","updated_at":"2026-10-26T08:01:18Z","run_started_at":"2026-10-26T07:59:05Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40281911315,"name":"Formal models","display_title":"Merge pull request #26 from sloik/docs/a2ui-research","head_sha":"ad063c67668ecfd194f9f9e8939586307dbf9cc2","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T06:47:45Z","updated_at":"2026-10-26T06:50:26Z","run_started_at":"2026-10-26T06:47:45Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40001666497,"name":"Formal models","display_title":"Merge pull request #25 from sloik/feat/private-key-location","head_sha":"ec55bedaf81c5af69342a0252a68044be8529b6d","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T18:14:25Z","updated_at":"2026-10-23T18:17:02Z","run_started_at":"2026-10-23T18:14:25Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39965461492,"name":"Formal models","display_title":"Merge pull request #24 from sloik/release/v3.3.0","head_sha":"e78e2ca05e28316e30a5728180e4570b5e266d6b","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T13:57:00Z","updated_at":"2026-10-23T13:59:44Z","run_started_at":"2026-10-23T13:57:00Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39964338438,"name":"Formal models","display_title":"Merge pull request #23 from sloik/feat/auto-room-history","head_sha":"3af35eccb26f171e041174129b89b62871b0372b","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T13:48:59Z","updated_at":"2026-10-23T13:50:51Z","run_started_at":"2026-10-23T13:48:59Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39935065363,"name":"Formal models","display_title":"Merge pull request #22 from sloik/release/v3.2.0","head_sha":"7d91db493310b00b33a5969eb24e446d15e0b922","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T09:52:53Z","updated_at":"2026-10-23T09:55:21Z","run_started_at":"2026-10-23T09:52:53Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39932684582,"name":"Formal models","display_title":"Merge pull request #21 from sloik/feat/signing-cli-usability","head_sha":"595ce420057c06850defbd5669e1c6b93fc446c3","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T09:33:06Z","updated_at":"2026-10-23T09:35:34Z","run_started_at":"2026-10-23T09:33:06Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39928338202,"name":"Formal models","display_title":"Merge pull request #20 from sloik/docs/signing-help","head_sha":"2f34ba0f616e9a423ca1ea5489b0cd51ca6b3161","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T08:57:21Z","updated_at":"2026-10-23T08:59:54Z","run_started_at":"2026-10-23T08:57:21Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39927723105,"name":"Formal models","display_title":"Merge pull request #19 from sloik/feat/room-history-3.1","head_sha":"ca36fcbd857da1c6471b045eb262f9b0509950c0","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T08:52:14Z","updated_at":"2026-10-23T08:54:52Z","run_started_at":"2026-10-23T08:52:14Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39921138006,"name":"Formal models","display_title":"Merge pull request #18 from sloik/docs/close-core-3.0.0","head_sha":"9bba12b8115c89f9c7acab0d4a30d225b6cf2e8c","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T07:56:19Z","updated_at":"2026-10-23T07:58:49Z","run_started_at":"2026-10-23T07:56:19Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39917051541,"name":"Formal models","display_title":"Merge pull request #17 from sloik/release/v3.0.0","head_sha":"e7a8154c7c510b231c6d0b817e1e921028b0547c","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-23T07:20:09Z","updated_at":"2026-10-23T07:24:26Z","run_started_at":"2026-10-23T07:20:09Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39845058415,"name":"Formal models","display_title":"Merge pull request #16 from sloik/docs/close-core-2.12.2","head_sha":"afc551813bffc60ffa0ec2c120a9f694ef85a63a","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T20:00:30Z","updated_at":"2026-10-22T20:02:42Z","run_started_at":"2026-10-22T20:00:30Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39844403867,"name":"Formal models","display_title":"Merge pull request #15 from sloik/release/v2.12.2","head_sha":"4b398b6e9ef0daabd1648e172bfc1b4f5632ca47","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T19:55:58Z","updated_at":"2026-10-22T19:57:47Z","run_started_at":"2026-10-22T19:55:58Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39843559205,"name":"Formal models","display_title":"Merge pull request #14 from sloik/docs/signing-adoption","head_sha":"99580f6152c1e60b66e0930ac85145e35cc83582","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T19:50:17Z","updated_at":"2026-10-22T19:51:50Z","run_started_at":"2026-10-22T19:50:17Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39804157410,"name":"Formal models","display_title":"Merge pull request #13 from sloik/fix/portable-answer-reader","head_sha":"c36f89a6f100b2a264d6f5257e85af4ccaa9ce33","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T15:22:04Z","updated_at":"2026-10-22T15:24:11Z","run_started_at":"2026-10-22T15:22:04Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39800364293,"name":"Formal models","display_title":"Merge pull request #12 from sloik/feat/recorded-answer-acceptance","head_sha":"f99a8a4b939a3839d0505bce995bd40e2b661275","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T14:57:56Z","updated_at":"2026-10-22T15:00:03Z","run_started_at":"2026-10-22T14:57:56Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39782946062,"name":"Formal models","display_title":"[SPEC-002-040] record completed protected CI integration (#11)","head_sha":"43aa23227efba3b8bae69f218934919f73055e56","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T12:59:30Z","updated_at":"2026-10-22T13:01:13Z","run_started_at":"2026-10-22T12:59:30Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39782504977,"name":"Formal models","display_title":"[SPEC-002-040] Require unit/formal checks and bound setup (#10)","head_sha":"237050eb17d59529c12c22aa9c0033d63c40b3f8","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T12:56:19Z","updated_at":"2026-10-22T12:58:00Z","run_started_at":"2026-10-22T12:56:19Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39762578182,"name":"Formal models","display_title":"[SPEC-002-039] measure watchdog rerun age from attempt start","head_sha":"cb9ff7912d306aacc870cc44071a409f85075567","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T10:22:13Z","updated_at":"2026-10-22T10:23:51Z","run_started_at":"2026-10-22T10:22:13Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39762153290,"name":"Formal models","display_title":"[SPEC-002-039] monitor formal freshness and explore bounded save sche\u2026","head_sha":"e4c79539984112dd0593902901fd035682dba32c","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T10:18:49Z","updated_at":"2026-10-22T10:20:23Z","run_started_at":"2026-10-22T10:18:49Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39738222307,"name":"Formal models","display_title":"[SPEC-002-038] validate private save and publication runtime actions","head_sha":"98d9c107a25698f7759b553ae414151b8d0fead0","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T07:06:22Z","updated_at":"2026-10-22T07:07:51Z","run_started_at":"2026-10-22T07:06:22Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39732679444,"name":"Formal models","display_title":"[SPEC-002-037] report formal verification freshness and run weekly","head_sha":"575e5800d7b5f824f8f2a84621f3eb6e21f7ccee","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T06:14:04Z","updated_at":"2026-10-22T06:15:17Z","run_started_at":"2026-10-22T06:14:04Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39728925607,"name":"Formal models","display_title":"docs: complete formal implementation alignment coverage","head_sha":"5a731cb9fb4047dfbefa0d48d512b77384172cd9","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T05:35:45Z","updated_at":"2026-10-22T05:36:53Z","run_started_at":"2026-10-22T05:35:45Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39728275138,"name":"Formal models","display_title":"[SPEC-002-036] check formal alignment and real private save recovery \u2026","head_sha":"bf0ec808bebe2d037a90aa4b9b3df20504eb6601","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-22T05:29:02Z","updated_at":"2026-10-22T05:29:57Z","run_started_at":"2026-10-22T05:29:02Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":39619173720,"name":"Formal models","display_title":"chore: complete formal protocol model integration","head_sha":"3dcd1a5718081caeceaf3091ab9e13f15d773522","head_branch":"main","event":"push","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-21T14:42:18Z","updated_at":"2026-10-21T14:43:12Z","run_started_at":"2026-10-21T14:42:18Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}}
],
"schedule": [
{"id":41475762058,"name":"Formal models","display_title":"Formal models","head_sha":"6a8fe97d5dbeb80e9ca94ccc707da573c355044a","head_branch":"main","event":"schedule","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-11-02T15:51:50Z","updated_at":"2026-11-02T15:54:41Z","run_started_at":"2026-11-02T15:51:50Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}},
{"id":40327138902,"name":"Formal models","display_title":"Formal models","head_sha":"6a8fe97d5dbeb80e9ca94ccc707da573c355044a","head_branch":"main","event":"schedule","workflow_id":391820399,"run_attempt":1,"status":"completed","conclusion":"success","created_at":"2026-10-26T13:01:51Z","updated_at":"2026-10-26T13:04:37Z","run_started_at":"2026-10-26T13:01:51Z","path":".github/workflows/formal.yml","repository":{"id":1389483631,"full_name":"sloik/agent-file-board"}}
],
"workflow_dispatch": [

]
}
}
''')


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 9, tzinfo=timezone.utc)
        self.sha = 'a' * 40
        self.run = {'id': 1, 'event': 'schedule', 'head_branch': 'main', 'head_sha': self.sha,
                    'status': 'completed', 'conclusion': 'success',
                    'updated_at': self.now.isoformat(), 'created_at': self.now.isoformat()}

    def result(self, successes=None, attempts=None, state='active'):
        return watchdog.assess({'state': state}, self.sha, [self.run] if successes is None else successes,
                               [self.run] if attempts is None else attempts, self.now)

    def test_fresh_main_successes_from_push_schedule_or_manual_are_healthy(self):
        for event in ['push', 'schedule', 'workflow_dispatch']:
            self.run['event'] = event
            self.assertEqual(self.result()['result'], 'healthy')

    def test_pr_branch_disabled_missing_or_failed_evidence_alerts(self):
        for field, value in [('event', 'pull_request'), ('head_branch', 'other'), ('head_sha', 'b'*40),
                             ('conclusion', 'failure')]:
            with self.subTest(field=field):
                changed = {**self.run, field: value}
                self.assertEqual(self.result([changed], [changed])['result'], 'alert')
        self.assertEqual(self.result(state='disabled_inactivity')['result'], 'alert')
        self.assertEqual(self.result(successes=[])['result'], 'alert')
        self.assertEqual(self.result(attempts=[])['result'], 'alert')

    def test_age_limit_and_future_clock_are_fail_closed(self):
        for age, expected in [(timedelta(days=8), 'healthy'), (timedelta(days=8, seconds=1), 'alert'),
                              (timedelta(seconds=-1), 'alert')]:
            run = {**self.run, 'updated_at': (self.now-age).isoformat(), 'created_at': (self.now-age).isoformat()}
            if age.total_seconds() < 0:
                with self.assertRaises(ValueError):
                    self.result([run], [self.run])
            else:
                self.assertEqual(self.result([run], [self.run])['result'], expected)

    def test_new_main_in_progress_is_pending_only_with_fresh_previous_success(self):
        old = {**self.run, 'head_sha': 'b'*40}
        current = {**self.run, 'status': 'in_progress', 'conclusion': None}
        self.assertEqual(self.result([old], [current])['result'], 'pending')
        current['created_at'] = (self.now-timedelta(hours=2, seconds=1)).isoformat()
        self.assertEqual(self.result([old], [current])['result'], 'alert')
        self.assertEqual(self.result([], [{**current, 'created_at': self.now.isoformat()}])['result'], 'alert')
        rerun = {**current, 'created_at': (self.now-timedelta(days=7)).isoformat(), 'run_started_at': self.now.isoformat()}
        self.assertEqual(self.result([old], [rerun])['result'], 'pending')

    def test_latest_rerun_outcome_wins_and_old_green_does_not_hide_failure(self):
        old = {**self.run, 'created_at': (self.now-timedelta(seconds=3)).isoformat(), 'updated_at': (self.now-timedelta(seconds=1)).isoformat()}
        fail = {**self.run, 'conclusion': 'failure', 'created_at': (self.now-timedelta(seconds=3)).isoformat(), 'updated_at': (self.now-timedelta(seconds=2)).isoformat()}
        self.assertEqual(self.result([old], [old, fail])['result'], 'healthy')
        failed_now = {**fail, 'updated_at': self.now.isoformat()}
        self.assertEqual(self.result([old], [old, failed_now])['result'], 'alert')
        newer = {**fail, 'updated_at': (self.now+timedelta(seconds=1)).isoformat()}
        with self.assertRaises(ValueError):
            self.result([self.run], [newer, self.run])

    def test_malformed_success_metadata_never_establishes_healthy_evidence(self):
        for field, value in [('id', True), ('head_sha', 'invalid'), ('status', 'invented'), ('updated_at', 'invalid')]:
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                self.result([{**self.run, field: value}], [self.run])

    def test_api_invalid_schema_clock_and_unavailable_status_are_alerts_without_secrets(self):
        responses = {'actions/workflows/formal.yml': {'state': 'active'},
                     'git/ref/heads/main': {'object': {'sha': self.sha}}}
        def broken(*args):
            raise OSError('sensitive-token /private/path')
        for reader in [broken, lambda repo, endpoint, token: responses.get(endpoint, {}),
                       lambda *args: []]:
            report = watchdog.monitor('owner/repo', reader=reader, now=self.now)
            self.assertEqual(report['result'], 'alert')
            self.assertNotIn('sensitive-token', str(report))
        self.run['updated_at'] = '2026-10-22T09:00:00'
        def reader(repo, endpoint, token):
            return responses.get(endpoint, {'workflow_runs': [self.run]})
        self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'alert')

    def native_fixture(self):
        run = {**self.run, 'run_attempt': 2, 'workflow_id': 8, 'name': 'Formal preparation '+self.sha,
               'display_title': 'Formal preparation '+self.sha, 'repository': {'id': 41, 'full_name': 'owner/repo'},
               'path': '.github/workflows/formal.yml', 'created_at': (self.now-timedelta(minutes=10)).isoformat(),
               'updated_at': (self.now-timedelta(minutes=5)).isoformat()}
        env = {'GITHUB_RUN_ID': '77', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_WORKFLOW_SHA': 'b'*40,
               'GITHUB_WORKFLOW_REF': 'owner/repo/.github/workflows/formal-queue.yml@refs/heads/main',
               'GITHUB_EVENT_NAME': 'workflow_run'}
        check = {'id': 55, 'name': 'bounded-models', 'head_sha': self.sha, 'external_id': 'afb-oracle-source-1-2',
                 'app': {'id': 15368, 'slug': 'github-actions'}, 'details_url': 'https://github.com/owner/repo/actions/runs/77',
                 'status': 'completed', 'conclusion': 'success', 'completed_at': self.now.isoformat(),
                 'output': {'text': watchdog.publication_text('owner/repo', run, env)}}
        final = {'id': 77, 'run_attempt': 1, 'repository': {'id': 41, 'full_name': 'owner/repo'}, 'workflow_id': 9,
                 'head_branch': 'main', 'head_sha': 'b'*40, 'head_commit': {'id': 'b'*40},
                 'event': 'workflow_run', 'name': 'Oracle formal 1 attempt 2 completed',
                 'display_title': 'Oracle formal 1 attempt 2 completed', 'path': '.github/workflows/formal-queue.yml',
                 'created_at': (self.now-timedelta(minutes=4)).isoformat(),
                 'run_started_at': (self.now-timedelta(minutes=4)).isoformat(), 'updated_at': self.now.isoformat(),
                 'status': 'completed', 'conclusion': 'success'}
        rows = {'commits/'+self.sha+'/check-runs?check_name=bounded-models&per_page=100': {'total_count': 1, 'check_runs': [check]},
                'actions/runs/77': final, 'actions/runs/77/attempts/1': final,
                'actions/runs/1': run, 'actions/runs/1/attempts/2': run,
                'actions/workflows/8': {'id': 8, 'name': 'Formal models', 'path': '.github/workflows/formal.yml'},
                'actions/workflows/9': {'id': 9, 'name': 'Oracle formal queue', 'path': '.github/workflows/formal-queue.yml'},
                'compare/'+'b'*40+'...'+self.sha+'?per_page=1': {'merge_base_commit': {'sha': 'b'*40}}}
        return run, check, final, rows

    def test_native_join_requires_exact_trusted_completed_action_and_source_attempt(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
        self.assertEqual(self.result([joined], [joined])['result'], 'healthy')
        for key, value in [('event', 'push'), ('head_branch', 'feature'), ('workflow_id', 88),
                           ('display_title', 'Oracle formal 99 attempt 2 completed'),
                           ('display_title', 'Oracle formal 1 attempt 1 completed'),
                           ('display_title', 'Oracle formal 1 attempt 2 requested'),
                           ('head_sha', 'c'*40)]:
            old = final[key];final[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            final[key] = old
        final['conclusion'] = 'failure'
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
        self.assertEqual(self.result([joined], [joined])['result'], 'alert')

    def test_source_titles_and_final_run_names_cannot_impersonate_workflow_metadata(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        for row in (run, final):
            for field in ('name', 'display_title'):
                for title in ('Formal models', 'Oracle formal queue', 'Formal preparation '+'f'*40, 'arbitrary'):
                    old = row[field];row[field] = title
                    with self.subTest(field=field, title=title), self.assertRaises(ValueError):
                        watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
                    row[field] = old

    def test_monitor_joins_exact_static_workflow_metadata_with_real_run_titles(self):
        run, check, final, rows = self.native_fixture()
        workflow = {'id': 8, 'name': 'Formal models', 'path': '.github/workflows/formal.yml', 'state': 'active'}
        dispatcher = {'id': 9, 'name': 'Oracle formal queue', 'path': '.github/workflows/formal-queue.yml', 'state': 'active'}
        rows.update({'actions/workflows/formal.yml': workflow, 'actions/workflows/formal-queue.yml': dispatcher,
                     'git/ref/heads/main': {'object': {'sha': self.sha}}})
        def reader(repository, endpoint, token):
            if endpoint.startswith('actions/workflows/formal.yml/runs?'):
                return {'workflow_runs': [run] if ('event=schedule' in endpoint or 'head_sha=' in endpoint) else []}
            return rows[endpoint]
        self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'healthy')
        for row in (workflow, dispatcher):
            for field, value in [('id', 99), ('name', 'Unrelated workflow'), ('path', '.github/workflows/other.yml')]:
                old = row[field];row[field] = value
                with self.subTest(field=field, value=value):
                    self.assertEqual(watchdog.monitor('owner/repo', reader=reader, now=self.now)['result'], 'alert')
                row[field] = old

    def test_upstream_success_wrong_attempt_or_forged_unrelated_check_never_becomes_native_success(self):
        run, check, final, rows = self.native_fixture()
        reader = lambda repository, endpoint, token: rows[endpoint]
        for key, value in [('external_id', 'afb-oracle-source-1-1'), ('head_sha', 'd'*40)]:
            old = check[key];check[key] = value
            joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            self.assertNotEqual(self.result([joined], [joined])['result'], 'healthy')
            check[key] = old
        for key, value in [('app', {'slug': 'other'}), ('details_url', 'https://evil.test/runs/77')]:
            old = check[key];check[key] = value
            with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
            check[key] = old
        rows['compare/'+'b'*40+'...'+self.sha+'?per_page=1'] = {'merge_base_commit': {'sha': 'c'*40}}
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)

    def test_legitimate_manual_bootstrap_is_never_maintained_main_freshness(self):
        run, check, final, rows = self.native_fixture()
        run.update(event='workflow_dispatch', name='Oracle bootstrap 1 attempt 2', display_title='Oracle bootstrap 1 attempt 2')
        def forbidden(*args):self.fail('bootstrap must not query/credit a normal native check')
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, forbidden)
        self.assertEqual(self.result([joined], [joined])['result'], 'alert')

    def test_publication_schema_is_bounded_duplicate_free_and_type_exact(self):
        run, check, final, rows = self.native_fixture()
        text = check['output']['text'];binding = watchdog.publication_binding(text)
        controls = [None, '', 'x' * (watchdog.PUBLICATION_LIMIT + 1),
                    text[:-1] + ',"kind":"'+watchdog.PUBLICATION_KIND+'"}', '{"kind":NaN}']
        for group, key, value in [('source', 'attempt', True), ('source', 'id', 1.0),
                                  ('repository', 'id', False), ('dispatcher', 'attempt', 1.0),
                                  ('dispatcher', 'workflow_sha', 'bad'), ('source', 'head_branch', 'main\n')]:
            changed = copy.deepcopy(binding);changed[group][key] = value;controls.append(json.dumps(changed))
        changed = copy.deepcopy(binding);changed['extra'] = 'ignored';controls.append(json.dumps(changed))
        changed = copy.deepcopy(binding);del changed['dispatcher']['attempt'];controls.append(json.dumps(changed))
        for value in controls:
            with self.subTest(value=str(value)[:80]), self.assertRaises(ValueError):
                watchdog.publication_binding(value)

    def test_rewritten_link_is_presentation_only_and_suite_cannot_supply_authority(self):
        run, check, final, rows = self.native_fixture()
        check['details_url'] = 'https://github.com/owner/repo/runs/55'
        check['check_suite'] = {'id': 123};final['check_suite_id'] = 999
        visited = []
        def reader(repository, endpoint, token):visited.append(endpoint);return rows[endpoint]
        joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)
        self.assertEqual(self.result([joined], [joined])['result'], 'healthy')
        self.assertFalse(any('check-suite' in path for path in visited))
        check['output']['text'] = None
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, reader)

    def test_source_dispatcher_attempts_and_publication_window_are_fresh(self):
        mutations = [('actions/runs/1', 'run_attempt', 3), ('actions/runs/1/attempts/2', 'run_attempt', 3),
                     ('actions/runs/77', 'run_attempt', 2), ('actions/runs/77/attempts/1', 'run_attempt', 2),
                     ('actions/runs/77', 'event', 'workflow_dispatch'), ('actions/runs/77', 'id', 77.0),
                     ('actions/runs/1', 'repository', {'id': 41.0, 'full_name': 'owner/repo'}),
                     ('actions/runs/77', 'repository', {'id': 41.0, 'full_name': 'owner/repo'}),
                     ('actions/workflows/9', 'name', 'Unrelated'), ('actions/workflows/8', 'path', 'other.yml')]
        for endpoint, key, value in mutations:
            run, check, final, rows = self.native_fixture();rows[endpoint] = {**rows[endpoint], key: value}
            with self.subTest(endpoint=endpoint, key=key), self.assertRaises(ValueError):
                watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, lambda r, p, t: rows[p])
        for completed in [self.now-timedelta(minutes=6), self.now+timedelta(seconds=1)]:
            run, check, final, rows = self.native_fixture();check['completed_at'] = completed.isoformat()
            with self.subTest(completed=completed), self.assertRaises(ValueError):
                watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, lambda r, p, t: rows[p])
        for key in ('status', 'conclusion'):
            run, check, final, rows = self.native_fixture();final[key] = 'in_progress' if key == 'status' else 'failure'
            joined = watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, lambda r, p, t: rows[p])
            self.assertNotEqual(self.result([joined], [joined])['result'], 'healthy')

    def test_binding_cannot_select_an_unrelated_successful_run_or_wrong_source(self):
        for group, key, value in [('source', 'attempt', 1), ('source', 'head_sha', 'c'*40),
                                  ('repository', 'id', 99), ('dispatcher', 'workflow_sha', 'c'*40),
                                  ('dispatcher', 'workflow_ref', 'owner/repo/.github/workflows/formal.yml@refs/heads/feature')]:
            run, check, final, rows = self.native_fixture();binding = watchdog.publication_binding(check['output']['text'])
            binding[group][key] = value;check['output']['text'] = json.dumps(binding)
            with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, lambda r, p, t: rows[p])
        run, check, final, rows = self.native_fixture();binding = watchdog.publication_binding(check['output']['text'])
        binding['dispatcher']['id'] = 88;check['output']['text'] = json.dumps(binding)
        check['details_url'] = 'https://github.com/owner/repo/runs/55'
        unrelated = {**final, 'id': 88, 'name': 'Oracle formal 99 attempt 2 completed',
                     'display_title': 'Oracle formal 99 attempt 2 completed'}
        rows.update({'actions/runs/88': unrelated, 'actions/runs/88/attempts/1': unrelated})
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', run, {'id': 9}, self.sha, lambda r, p, t: rows[p])

    def test_legacy_history_is_non_success_only_before_authoritative_cutover(self):
        run, check, final, rows = self.native_fixture()
        legacy = {**run, 'name': 'Formal models', 'display_title': 'Old commit message',
                  'created_at': (self.now-timedelta(days=2)).isoformat()}
        dispatcher = {'id': 9, 'created_at': (self.now-timedelta(days=1)).isoformat()}
        def forbidden(*args):self.fail('legacy cannot query or earn native proof credit')
        converted = watchdog.native_run('owner/repo', legacy, dispatcher, self.sha, forbidden)
        self.assertEqual(converted['conclusion'], 'failure')
        legacy['created_at'] = self.now.isoformat()
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', legacy, dispatcher, self.sha, forbidden)
        legacy['created_at'] = (self.now-timedelta(days=2)).isoformat();legacy['name'] = 'arbitrary'
        with self.assertRaises(ValueError):watchdog.native_run('owner/repo', legacy, dispatcher, self.sha, forbidden)

    def test_exact_old_null_publication_is_retired_only_after_main_advances(self):
        data = copy.deepcopy(REAL_API);repo = data['source']['repository']['full_name']
        def converted(source, check, repository=repo):
            reader = lambda *args: {'total_count': 1, 'check_runs': [check]}
            return watchdog.native_run(repository, source, data['dispatcher'], 'c'*40, reader)
        self.assertEqual(converted(data['source'], data['check'])['conclusion'], 'failure')
        mutations = [('source', 'id', 43787992316), ('source', 'run_attempt', 2),
                     ('source', 'workflow_id', 391820400), ('source', 'event', 'schedule'),
                     ('source', 'head_branch', 'other'), ('source', 'path', 'other.yml'),
                     ('source', 'repository.id', 1389483632),
                     ('source', 'repository.full_name', 'sloik/other'),
                     ('check', 'id', 133040165026), ('check', 'output.text', ''),
                     ('check', 'details_url', 'https://github.com/sloik/agent-file-board/runs/77')]
        for owner, key, value in mutations:
            with self.subTest(owner=owner, key=key):
                changed = copy.deepcopy(data);target = changed[owner]
                parts = key.split('.')
                for part in parts[:-1]:target = target[part]
                target[parts[-1]] = value
                if owner == 'source' and key in {'id', 'run_attempt'}:
                    changed['check']['external_id'] = 'afb-oracle-source-{}-{}'.format(
                        changed['source']['id'], changed['source']['run_attempt'])
                with self.assertRaises(ValueError):converted(changed['source'], changed['check'])
        for missing in ['id', 'workflow_id', 'path', 'repository']:
            changed = copy.deepcopy(data);del changed['source'][missing]
            with self.subTest(missing=missing), self.assertRaises((ValueError, KeyError)):
                converted(changed['source'], changed['check'])
        changed = copy.deepcopy(data);del changed['check']['output']['text']
        with self.assertRaises(ValueError):converted(changed['source'], changed['check'])
        changed = copy.deepcopy(data);unknown = 'd'*40
        changed['source'].update(head_sha=unknown, name='Formal preparation '+unknown,
                                 display_title='Formal preparation '+unknown)
        changed['check']['head_sha'] = unknown
        with self.assertRaises(ValueError):converted(changed['source'], changed['check'])
        with self.assertRaises(ValueError):converted(data['source'], data['check'], 'sloik/other')

    def test_new_head_publication_and_actual_old_null_history_remain_separate(self):
        data = copy.deepcopy(REAL_API);old = data['source'];repo = old['repository']['full_name']
        # Synthetic new protocol/current head; the actual historical row stays
        # byte-for-byte null and can never become the latest successful proof.
        head = 'c'*40;source = copy.deepcopy(old);source['id'] += 100
        source.update(head_sha=head, name='Formal preparation '+head, display_title='Formal preparation '+head,
                      head_commit={'id': head})
        final = copy.deepcopy(data['final']);final['id'] += 100
        final.update(head_sha=head, head_commit={'id': head},
                     name='Oracle formal '+str(source['id'])+' attempt 1 completed',
                     display_title='Oracle formal '+str(source['id'])+' attempt 1 completed')
        check = copy.deepcopy(data['check']);check['id'] += 100
        check.update(head_sha=head, external_id='afb-oracle-source-'+str(source['id'])+'-1',
                     details_url='https://github.com/'+repo+'/runs/'+str(check['id']))
        env = {'GITHUB_RUN_ID': str(final['id']), 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_WORKFLOW_SHA': head,
               'GITHUB_WORKFLOW_REF': repo+'/.github/workflows/formal-queue.yml@refs/heads/main',
               'GITHUB_EVENT_NAME': 'workflow_run'}
        check['output']['text'] = watchdog.publication_text(repo, source, env)
        rows = {'actions/workflows/formal.yml': data['source_workflow'],
                'actions/workflows/formal-queue.yml': data['dispatcher'],
                'actions/workflows/'+str(source['workflow_id']): data['source_workflow'],
                'actions/workflows/'+str(final['workflow_id']): data['dispatcher'],
                'git/ref/heads/main': {'object': {'sha': head}},
                'commits/'+head+'/check-runs?check_name=bounded-models&per_page=100': {'total_count': 1, 'check_runs': [check]},
                'commits/'+old['head_sha']+'/check-runs?check_name=bounded-models&per_page=100': {'total_count': 1, 'check_runs': [data['check']]},
                'actions/runs/'+str(source['id']): source,
                'actions/runs/'+str(source['id'])+'/attempts/1': source,
                'actions/runs/'+str(final['id']): final,
                'actions/runs/'+str(final['id'])+'/attempts/1': final,
                'compare/'+head+'...'+head+'?per_page=1': {'merge_base_commit': {'sha': head}}}
        def reader(repository, endpoint, token):
            if endpoint.startswith('actions/workflows/formal.yml/runs?'):
                if 'head_sha=' in endpoint:return {'workflow_runs': [source]}
                event = endpoint.split('event=', 1)[1].split('&', 1)[0]
                return {'workflow_runs': ([source] if event == 'push' else [])+data['success_history'][event]}
            return rows[endpoint]
        clock = watchdog.timestamp(final['updated_at'])+timedelta(seconds=1)
        report = watchdog.monitor(repo, reader=reader, now=clock)
        self.assertEqual(report['result'], 'healthy')
        self.assertEqual(report['latestSuccessCommit'], head)
        self.assertIsNone(data['check']['output']['text'])
        final['conclusion'] = 'failure'
        self.assertEqual(watchdog.monitor(repo, reader=reader, now=clock)['result'], 'alert')
        final['conclusion'] = 'success';check['output']['text'] = None
        self.assertEqual(watchdog.monitor(repo, reader=reader, now=clock)['result'], 'alert')

    def test_real_responses_rewritten_link_and_complete_legacy_search(self):
        data = copy.deepcopy(REAL_API);repo = data['source']['repository']['full_name'];head = data['source']['head_sha']
        source, check, final = data['source'], data['check'], data['final']
        rows = {'actions/workflows/formal.yml': data['source_workflow'],
                'actions/workflows/formal-queue.yml': data['dispatcher'],
                'actions/workflows/'+str(source['workflow_id']): data['source_workflow'],
                'actions/workflows/'+str(final['workflow_id']): data['dispatcher'],
                'git/ref/heads/main': {'object': {'sha': head}},
                'commits/'+head+'/check-runs?check_name=bounded-models&per_page=100': {'total_count': 1, 'check_runs': [check]},
                'actions/runs/'+str(source['id']): source,
                'actions/runs/'+str(source['id'])+'/attempts/1': data['source_attempt'],
                'actions/runs/'+str(final['id']): final,
                'actions/runs/'+str(final['id'])+'/attempts/1': data['final_attempt'],
                'compare/'+head+'...'+head+'?per_page=1': {'merge_base_commit': {'sha': head}}}
        def reader(repository, endpoint, token):
            if endpoint.startswith('actions/workflows/formal.yml/runs?'):
                return {'workflow_runs': [source] if 'head_sha=' in endpoint else
                        data['success_history'][endpoint.split('event=', 1)[1].split('&', 1)[0]]}
            return rows[endpoint]
        clock = watchdog.timestamp(final['updated_at'])+timedelta(seconds=1)
        self.assertIsNone(check['output']['text'])
        self.assertEqual(watchdog.monitor(repo, reader=reader, now=clock)['result'], 'alert')
        env = {'GITHUB_RUN_ID': str(final['id']), 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_WORKFLOW_SHA': head,
               'GITHUB_WORKFLOW_REF': repo+'/.github/workflows/formal-queue.yml@refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_run'}
        class Publisher:
            def call(inner, path, method, body):check.update(body);return check
        # A synthetic new-protocol publication over frozen real API values, not
        # a claim that the historical workflow published these missing bytes.
        with patch.object(ci_dispatch, 'datetime') as frozen:
            frozen.now.return_value = watchdog.timestamp(check['completed_at'])
            ci_dispatch.publish(Publisher(), repo, source, env, 'completed', 'success', check['id'])
        self.assertNotEqual(check['check_suite']['id'], final['check_suite_id'])
        self.assertEqual(check['details_url'], 'https://github.com/'+repo+'/runs/'+str(check['id']))
        self.assertEqual(watchdog.monitor(repo, reader=reader, now=clock)['result'], 'healthy')


if __name__ == '__main__':
    unittest.main()
