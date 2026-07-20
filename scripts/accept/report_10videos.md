# A8 10 Videos Cutover Report

- mode: `mock`
- status: `PASS`
- qualified: `10/10`
- media_concurrency: `1`

## Real Readiness

- readiness: `blocked`
- missing_env: `DOUBAO_API_KEY, SEEDANCE_API_KEY`
- warnings: `none`

## Pricing

- `doubao_analyze`: `0.093`
- `doubao_script`: `0.119`
- `doubao_shotplan`: `0.082`
- `doubao_review`: `0.033`
- `seedance_shot`: `5.96`
- `ffmpeg_compose`: `0.0`

## Results

| # | project_id | material_id | qualified | final_qa | business | cost_cny | elapsed_s | risks |
|---|------------|-------------|-----------|----------|----------|----------|-----------|-------|
| 1 | `a8-cbe1babf-01-000001` | `tt_7100000000000000001` | yes | PASS | accepted | 0.0000 | 1.656 | none |
| 2 | `a8-cbe1babf-02-000002` | `tt_7100000000000000002` | yes | PASS | accepted | 0.0000 | 1.234 | none |
| 3 | `a8-cbe1babf-03-000003` | `tt_7100000000000000003` | yes | PASS | accepted | 0.0000 | 1.235 | none |
| 4 | `a8-cbe1babf-04-000004` | `tt_7100000000000000004` | yes | PASS | accepted | 0.0000 | 1.156 | none |
| 5 | `a8-cbe1babf-05-000005` | `tt_7100000000000000005` | yes | PASS | accepted | 0.0000 | 1.109 | none |
| 6 | `a8-cbe1babf-06-000006` | `tt_7100000000000000006` | yes | PASS | accepted | 0.0000 | 1.125 | none |
| 7 | `a8-cbe1babf-07-000007` | `tt_7100000000000000007` | yes | PASS | accepted | 0.0000 | 1.172 | none |
| 8 | `a8-cbe1babf-08-000008` | `tt_7100000000000000008` | yes | PASS | accepted | 0.0000 | 1.110 | none |
| 9 | `a8-cbe1babf-09-000009` | `tt_7100000000000000009` | yes | PASS | accepted | 0.0000 | 1.093 | none |
| 10 | `a8-cbe1babf-10-000010` | `tt_7100000000000000010` | yes | PASS | accepted | 0.0000 | 1.141 | none |

## Cutover Decision

- `real 10/10 PASS`: old system may be switched to read-only backup.
- `mock 10/10 PASS`: internal chain is healthy, but cutover is not approved.
- `<10/10` or any BLOCKED item: old system remains online; defects feed the next round.
