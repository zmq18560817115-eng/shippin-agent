# A8 10 Videos Cutover Report

- mode: `mock`
- status: `PASS`
- qualified: `10/10`
- media_concurrency: `1`

## Real Readiness

- readiness: `blocked`
- missing_env: `DOUBAO_API_KEY, SEEDANCE_API_KEY`
- warnings: `pricing not calibrated: doubao_analyze, doubao_script, doubao_shotplan, doubao_review, seedance_shot, ffmpeg_compose`

## Pricing

- `doubao_analyze`: `None`
- `doubao_script`: `None`
- `doubao_shotplan`: `None`
- `doubao_review`: `None`
- `seedance_shot`: `None`
- `ffmpeg_compose`: `None`

## Results

| # | project_id | material_id | qualified | final_qa | business | cost_cny | elapsed_s | risks |
|---|------------|-------------|-----------|----------|----------|----------|-----------|-------|
| 1 | `a8-01-000001` | `tt_7100000000000000001` | yes | PASS | accepted | 0.0000 | 2.609 | none |
| 2 | `a8-02-000002` | `tt_7100000000000000002` | yes | PASS | accepted | 0.0000 | 2.266 | none |
| 3 | `a8-03-000003` | `tt_7100000000000000003` | yes | PASS | accepted | 0.0000 | 2.328 | none |
| 4 | `a8-04-000004` | `tt_7100000000000000004` | yes | PASS | accepted | 0.0000 | 2.328 | none |
| 5 | `a8-05-000005` | `tt_7100000000000000005` | yes | PASS | accepted | 0.0000 | 2.609 | none |
| 6 | `a8-06-000006` | `tt_7100000000000000006` | yes | PASS | accepted | 0.0000 | 2.328 | none |
| 7 | `a8-07-000007` | `tt_7100000000000000007` | yes | PASS | accepted | 0.0000 | 2.344 | none |
| 8 | `a8-08-000008` | `tt_7100000000000000008` | yes | PASS | accepted | 0.0000 | 2.344 | none |
| 9 | `a8-09-000009` | `tt_7100000000000000009` | yes | PASS | accepted | 0.0000 | 2.265 | none |
| 10 | `a8-10-000010` | `tt_7100000000000000010` | yes | PASS | accepted | 0.0000 | 2.188 | none |

## Cutover Decision

- `real 10/10 PASS`: old system may be switched to read-only backup.
- `mock 10/10 PASS`: internal chain is healthy, but cutover is not approved.
- `<10/10` or any BLOCKED item: old system remains online; defects feed the next round.
