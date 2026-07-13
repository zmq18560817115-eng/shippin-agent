# Material and Product Image Standards

## Purpose

Use this reference when selecting, adding, or judging product images and company material for overseas short-video output. The goal is to make every generated script, AI-video prompt, and editing package traceable to approved product material.

## Source locations

Preferred material locations:

- Product docs and images: `01_素材库/产品资料/`（竞品对标在 `01_素材库/竞品对标/`）
- Local knowledge fallback: `overseas-loc-mvp/knowledge/products/`
- DS223 company knowledge base: `\\DS223\obsidian知识库\shared-knowledge\products\`
- DS223 process and strategy docs: `\\DS223\obsidian知识库\shared-knowledge\processes\` and `\\DS223\obsidian知识库\shared-knowledge\concepts\`

If DS223 is unavailable, continue with local docs and clearly mark the result as not refreshed against DS223.

## Asset categories

Classify every product-related visual into one of these categories:

| Category | Use | Notes |
| --- | --- | --- |
| Product identity image | Product appearance, color, logo, shape, key UI, structural accuracy | Usually white-background main images or approved product renders |
| Usage-step image | Correct handling, pouring, opening, wearing, cleaning, charging, or assembly | Required when the script demonstrates product use |
| Scene image | Bedroom, car, airport, office, travel, nursery, kitchen, or other lifestyle context | Used to keep AI/video scene logic coherent |
| Detail/proof image | Battery, size, structure, port, spout, accessories, material detail | Only supports visual proof; do not convert into unsupported efficacy claims |
| Person image | On-camera person, hands, parent/worker/traveler identity | Must match audience and remain consistent |
| Reference-only image | Useful for mood, composition, or framing but not approved as product evidence | Mark as reference-only in output |
| Prohibited image | Wrong use, competitor brand, outdated product, unsafe scene, unsupported claim | Do not use except to explain exclusion |
| AI-generated image/video | Generated from approved refs | Must keep source refs and generation prompt record |

## Required asset metadata

For each asset used or added to the library, keep this metadata in the output or material manifest:

```yaml
asset_id: ""
product: ""
source_path: ""
asset_type: "product_identity | usage_step | scene | detail_proof | person | reference_only | prohibited | ai_generated"
approval_status: "approved | needs_review | reference_only | prohibited | generated_pending_review"
allowed_use: ""
forbidden_use: ""
scene_tags: []
person_profile: ""
claim_tags: []
shot_roles: []
notes: ""
```

Do not leave a product image as a loose file with no use rule. If the image is important enough to use in production, it needs a clear allowed use and a clear forbidden use.

## Folder and naming convention

Keep the company material library easy to search. Existing listing folders such as `主图`, `A+`, `M端`, and `副图` can remain, but production outputs should map them into the asset categories above.

Recommended future naming pattern:

`产品名_资产类型_场景或用途_版本_来源_YYYYMMDD.ext`

If renaming would break existing paths, keep original names and create a manifest instead.

## Product image hierarchy

When building a shot or AI-video prompt, choose references in this order:

1. **White-background hero (`白底主图`)**: locks exact product appearance — color, silhouette, UI, logo zone, proportions. Mandatory for every product-visible shot.
2. **Scenario image (`场景图`)**: locks environment, props, placement, and usage context for the selected scene tag.
3. **Usage-step image**: locks handling sequence — opening, pouring, wearing, cleaning, charging, assembly.
4. **Detail / proof image (`细节图`)**: locks spout, port, hinge, accessory, and structural inserts.
5. **Person or hands reference**: locks demographic and visual consistency for the whole video.
6. **AI-generated continuation**: only after the above references are bound to the shot.

For shots where the product is visible, the white-background hero is the **only** SeedDance I2V reference. Scenario and usage-step images inform prompts (environment, pour physics) but must not replace the hero as垫图.

Do not let AI “interpret” or “improve” product design from lifestyle/scenario photos. If the hero image does not show a detail, do not invent it.

## SeedDance / AI video image binding

| Runtime file | Source asset | When |
| --- | --- | --- |
| `runs/ref-*/inputs/seedance-source.*` | `主图/白底主图` | **Only** I2V reference when product is visible in frame |
| `runs/ref-*/inputs/seedance-usage-ref.*` | `主图/倒出口参考` | Staged for traceability; **prompt-only** physics hint — never I2V垫图 |
| Person staged refs | `01_素材库/人像角色/` | Person-only shots without product in frame |

If generated product shape/color drifts, verify: (1) `白底主图` exists and is staged to `seedance-source`, (2) regenerate with `--force` after updating assets, (3) do not use pour reference as the only product image.

## Syncing assets to GitHub

- **Push only on the developer's local machine** (`git add` / `commit` / `push workflow main`). Product images under `01_素材库/产品资料/` should be committed from there.
- **Intranet / LAN servers: pull only** (`git pull workflow main`). Do not run `git push`, `git commit`, or change git config on the deployment server.
- Do not commit `.env`, `03_产出库` videos, or `overseas-loc-mvp/runs/`. See workspace `README_使用说明.md` for the full checklist.

## Scene consistency rules

Choose one main scene for each short video unless the script has a clear transition reason.

Define:

- Main location: bedroom, office, car, airport, kitchen, nursery, park, etc.
- Time: morning, night, commute, travel, work break, feeding time.
- Props: bottle, milk storage bag, diaper bag, desk, stroller, suitcase, bedside table.
- Lighting and color: soft home light, office light, car interior, travel daylight — **enhance realism** with motivated light, soft shadows, natural reflections, and plausible exposure; do not use lighting to disguise product shape changes.
- Relationship to product: where the product sits, how it enters the shot, and what problem it solves.

Do not jump randomly between bedroom, office, car, and travel scenes just because those images exist. Use scene changes as story beats.

## Person consistency rules

If a person appears, define a stable profile before generating or editing:

```yaml
role: "new mother | working mother | traveler parent | caregiver | product-only"
age_range: ""
wardrobe: ""
hair: ""
hands_or_nails: ""
emotional_state: ""
relationship_to_product: ""
allowed_scene_changes: []
```

If there are no approved person references or the AI model cannot maintain identity, use product-only, hands-only, over-shoulder, or cropped lifestyle shots. This is better than an inconsistent “same person” who changes face, age, wardrobe, or family role across shots.

**Same-video rule**: once a person profile is chosen for shot 1, every later person-visible shot in that video must reuse the same profile unless the script explicitly introduces a new character.

## Material intake decision

Before using a material, ask:

1. Is it clearly tied to the target product?
2. Does it show correct product use?
3. Does it contain competitor logos, unsupported claims, unsafe behavior, or outdated packaging?
4. Does it support this shot’s purpose: identity, use, scene, person, or proof?
5. Can the editor or AI-video generator trace the exact source path?

If any answer is uncertain, mark the asset as `needs_review` instead of treating it as approved.
