---
name: overseas-video-output-standards
description: "Use this skill when building, reviewing, or generating overseas video localization output: strict script execution, product appearance locked to white-background hero images, usage/scene locked to scenario images, structural details locked to detail assets, physics-safe demonstrations, same-video person consistency, SeedDance/AI-video prompts, shot-to-asset mapping, editing task packs, and compliance checks. Apply the same asset-binding rules when onboarding new product categories."
---

# Overseas Video Output Standards

## Overview

This skill turns viral-video analysis into a brand-safe, material-aware production workflow. Use it to ensure every script, storyboard, AI-video prompt, and editing task package is grounded in approved company product material instead of improvised product details.

The core logic is:

`competitor structure/rhythm -> audience scenario -> company product facts -> approved assets -> shot task package -> human review`

## Start every task with source grounding

Before writing or reviewing output, identify the target product, target platform, and requested deliverable: script, shot list, SeedDance prompt, editing package, material-library intake, or QA.

Load product and process sources in this priority order when available:

1. Workspace product docs: `01_素材库/产品资料/{产品名}.md`（或联接路径 `海外视频本地化MVP/产品资料/`）
2. Local MVP knowledge fallback: `overseas-loc-mvp/knowledge/products/{产品名}.md`
3. DS223 Obsidian knowledge base: `\\DS223\obsidian知识库\shared-knowledge\products\`
4. Global process/compliance docs, especially `overseas-loc-mvp\knowledge\processes\海外短视频合规禁词.md` and DS223 `shared-knowledge\processes\`

Use competitor/TikTok content only for structure, pacing, hook style, shot rhythm, and audience insight. Do not copy competitor dialogue, claims, logos, product positioning, or product details.

## Load the right reference file

- For product image selection, company material intake, or image-library cleanup, load `references/material-asset-standards.md`.
- For converting a decomposed viral video or base script into a branded shot list, storyboard, SeedDance prompt, or editing task package, load `references/script-to-asset-workflow.md`.
- For product-specific usage, prohibited visuals, and allowed/forbidden claims, load `references/product-rules.md`.
- Before final delivery, load `references/qa-checklist.md`.

For most production tasks, load at least `script-to-asset-workflow.md`, `product-rules.md`, and `qa-checklist.md`.

## Non-negotiable production logic

The story line should usually be:

`scene -> pain -> product as solution -> safe proof/demo -> CTA`

Keep the user and scene first. The product should feel like the answer to a concrete moment, not like a hard advertisement dropped into a random viral template.

### Product video fidelity (mandatory)

When generating or reviewing product videos, treat approved assets as hard constraints — not inspiration.

| Dimension | Source of truth | Rule |
| --- | --- | --- |
| Script | Approved script-pack / storyboard | Execute shot order, dialogue, timing, and CTA exactly. Do not improvise new beats, claims, or scenes. |
| Product appearance & structure | White-background hero image (`白底主图`) | Match color, silhouette, lid, ports, display, logo zone, and proportions exactly. **Only** approved SeedDance I2V reference when product is visible. Never use scenario/lifestyle images as垫图. |
| Usage flow & scene behavior | Matching scenario image (`场景图` / `M端` / `副图`) | Environment, props, and usage steps in **prompt text** only — do not derive product shape from scene photos. |
| Structural & functional details | Detail / proof images (`细节图`, usage-step refs such as `倒出口参考`) | Spout, hinge, buttons, charging port, accessories, and assembly must match detail assets. |
| Physics & usage logic | Product docs + usage-step refs | No impossible pours, wrong container relationships, reversed gravity, wrong hand grip, or usage that contradicts the product type. |
| Person continuity | Person reference or stable profile | Same role, age range, wardrobe, hair, skin tone, and hands across all person-visible shots in one video. |
| Lighting & realism | Scene reference + physical plausibility | Enhance cinematic lighting (soft shadows, motivated light, natural reflections) while keeping scene identity stable. Do not use lighting to hide product shape changes. |

If a visual detail is not visible in approved assets, mark it `missing` or `needs_review`. Never ask AI to infer product appearance.

### Every generated output must preserve

- **Script fidelity**: final edit and AI generation follow the approved script-pack; no silent rewrites during generation.
- **Product factuality**: product shape, usage steps, accessories, and claims come from approved materials only.
- **Asset traceability**: every product image, scene image, generated clip, and reference image has a source path or status.
- **Scene continuity**: location, lighting, props, time of day, and family/work/travel context do not drift without a scripted reason.
- **Person continuity**: if a person appears, age range, role, wardrobe, hair, hands, and relationship to the product remain consistent for the whole video.
- **Compliance**: no unsupported medical, guaranteed, superlative, competitor, or restricted platform claims.

### Onboarding new product categories

When adding a new category for competitor benchmarking or production, require the same asset trio before scripting or generating:

1. `白底主图` — product identity anchor (appearance lock)
2. `场景图` — one or more approved scenario references per selectable use case
3. `细节图` — structure, ports, accessories, and usage-step proof images

Map every shot in `shot_asset_map` to one of these references. Competitor videos supply rhythm only; they never override company product assets.

## Required output contract

When generating or reviewing a script/shot list/prompt, include these sections unless the user explicitly asks for a lighter answer:

1. `product_sources`: product docs and material folders consulted.
2. `asset_manifest`: approved/reference-only/missing assets with source paths, tagged as `product_identity` (白底主图), `scene`, `usage_step`, or `detail_proof`.
3. `shot_asset_map`: each shot mapped to script purpose, visual, exact asset path/status, generation method, and `prompt_guardrails`.
4. `scene_continuity`: main scene, lighting intent, allowed transitions, and visual constraints.
5. `character_continuity`: person profile or reason to use product-only/hands-only shots.
6. `production_fidelity`: script-lock, white-hero lock, scenario lock, detail lock, physics checks, and lighting notes.
7. `claim_guardrails`: allowed claims, forbidden claims, and wording rewrites.
8. `delivery_risks`: blockers, warnings, and what needs human review.

Never say “let the AI infer the product appearance.” If a product detail matters visually, require an approved product reference or mark the asset as missing.

## Updating the standard

Put cross-product workflow rules in this skill. Put single-product facts in the product’s own material/knowledge file, then reference those facts from outputs. When a new product is added, require at minimum: product identity, target audience, allowed scenes, correct usage steps, prohibited visuals, approved claims, forbidden claims, and asset folder paths.
