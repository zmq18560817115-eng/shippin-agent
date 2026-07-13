# Product Rules

## Universal asset-binding rules (all products)

Before scripting, storyboarding, or generating AI video for any product:

1. **Script lock**: The approved script-pack is the execution contract. Shot order, dialogue, subtitles, timing, and CTA must not change during generation or editing unless a human explicitly revises the script.
2. **White-background hero lock (highest priority)**: Product appearance must match `白底主图` exactly. **Never** use scenario images (`M端`/`副图`), lifestyle KV, or `倒出口参考` as SeedDance image-to-video reference. Those assets may only appear in prompt text for environment/usage physics.
3. **Scenario lock (prompt only)**: Usage flow, environment, props, and placement must match the selected scenario image in **written prompts** — scenario images do not define product shape or color.
4. **Detail lock**: Functional details — spout, hinge, button, port — are described in prompts using detail / usage-step images (`倒出口参考`, etc.); I2V reference remains white hero.
5. **Physics & usage logic**: Demonstrations must obey real-world physics and approved usage steps. Reject outputs with obvious pour-direction errors, wrong container relationships, impossible hand poses, or scene/use-case mismatches.
6. **Person lock**: If a person appears in multiple shots of one video, keep the same identity profile across all of them. Prefer hands-only or product-only shots when identity cannot be held.
7. **Lighting realism**: Enhance motivated lighting, soft shadows, and natural reflections to make the scene believable — without changing product identity or inventing unsupported scene elements.

When onboarding a new product category, create the same trio before production:

- `required_reference_images` → white-background hero
- `scene_reference_images` → per-scenario approved frames
- detail / usage-step images → structure and handling proof

Competitor videos never override these company assets.

## Universal rules

Use product-specific documents as the source of truth. Do not infer product functions from competitor videos, AI output, or generic market knowledge.

Universal restrictions:

- Do not show competitor brand names, logos, packaging, or model numbers unless the task is explicitly internal competitive analysis.
- Do not use medical, diagnostic, treatment, guaranteed, superlative, FDA/approval, or quantified performance claims unless explicitly approved in product docs.
- Do not turn AI-generated b-roll into evidence of real product efficacy.
- Do not imply outcomes such as increased milk supply, pain-free use, cure/treatment, sterilization guarantee, or safety certification unless approved.
- For baby/maternal products, avoid unsafe baby handling, explicit real breastfeeding scenes, and distressing medical framing.
- Use “old product,” “previous bottle warmer,” “regular pump,” or other generic wording instead of naming competitors in consumer-facing videos.

## Portable warming cup / 便携恒温杯

Known product material folders include:

- `01_素材库/产品资料/便携恒温杯/`
- `01_素材库/产品资料/便携恒温杯/listing-0602-nw/`
- `overseas-loc-mvp/knowledge/products/assets/便携恒温杯/listing-0602-nw/`

Important product identity:

- This is a rechargeable heating/insulated cup.
- It is independent from the baby bottle. It is not a container where the baby bottle is inserted.
- Key visible elements include flip/hinge lid, light purple rectangular pop key, bowl-like lid recess, small round pouring spout, deep purple ring, logo area, vertical temperature display, oval power button, and recessed charging port with silicone cover.

Correct usage flow:

1. Open or flip the lid.
2. Pour milk from an allowed source into the cup interior.
3. Heat/keep warm according to approved product wording.
4. Tilt the cup.
5. Pour through the round spout into a clean baby bottle.

Allowed input-source visuals:

- Milk storage bag.
- Household baby bottle used as a source container.

Forbidden input-source visuals:

- Commercial milk plastic bottle.
- Milk carton or Tetra Pak.
- Yogurt cup.
- Any visual implying a whole baby bottle is placed inside the cup.

Preferred scenes:

- Night bedroom feeding prep.
- Car cup-holder/travel preparation.
- Airport or travel-parent context.
- Park/stroller outing.
- Office/back-to-work parent routine.
- Restaurant or mall temporary feeding prep.

High-value reference images:

- `主图\白底主图.png` — **mandatory** product identity anchor; **the only** SeedDance I2V reference (`inputs/seedance-source.*`) whenever the product is visible.
- `主图\倒出口参考.png` — pour/lid physics guidance in **prompt text only**; never I2V垫图; never substitutes white hero for appearance.
- Listing `M端` and `副图` scene images — **prompt-only** for environment/usage flow for the selected scenario; **never** I2V垫图; **never** lock product shape/color.
- Detail images — battery, heating, waterproof, anti-leak, size, or structural inserts; only when the product doc supports the wording.

Asset binding for this product:

| Shot need | Required reference |
| --- | --- |
| Product visible (any angle, any role) | `白底主图` only (I2V) |
| Open lid / pour / tilt demo | `白底主图` (I2V) + `倒出口参考` + matching `场景图` in **prompt** |
| Bedroom / car / travel / office / mall scene | corresponding `M端` or `副图` in **prompt** for environment only |
| Port / display / hinge / spout close-up | matching `细节图` |

Do not say or show:

- Bottle inserted into the cup.
- Wide-mouth direct pour if the approved material shows the round spout as the correct outlet.
- Unsupported sterilization, guaranteed safety, medical, or quantified heating claims.
- Claims that the product replaces safe feeding judgment or parent supervision.

## Breast pump / 吸奶器

Known product material:

- Product name in current material: 熊猫布布吸奶器.
- Primary audience: 0-6 month new mothers, working/pumping mothers, night pumping users, mixed-feeding families.

Allowed positioning themes:

- More natural suction rhythm / piston-pump structure, if supported by product docs.
- Adjustable suction levels.
- Multiple flange/shield sizes.
- Rechargeable and portable use.
- Easier cleaning due to detachable structure.
- Lower-noise nighttime routine, only as relative/lifestyle wording if supported.
- Workday/back-to-office pumping convenience.

Preferred scenes:

- Night pumping routine.
- Commuting or workday pumping preparation.
- Home nursing corner.
- Private office pumping setup.
- Recovery/comfort-focused routine, without medical promises.

Forbidden or risky terms:

- `medical grade`
- `pain-free`
- `increase milk supply`
- `boost lactation`
- `cure`
- `treat`
- `diagnose`
- `best`
- `guaranteed`
- `FDA approved`
- `通乳`
- `催奶`
- `下奶`

Do not show:

- Explicit real breastfeeding as a product proof scene.
- AI b-roll as proof of lactation efficacy.
- Medical diagnosis or treatment framing.
- Before/after body claims.

Safe rewrite examples:

- Instead of “pain-free,” use “designed for a gentler-feeling routine” only if the product docs support comfort language.
- Instead of “increase milk supply,” use “helps fit pumping into your routine.”
- Instead of “medical-grade suction,” use the approved mechanical description from product docs.

## Adding a new product

Before the product can be used in generated scripts, create or update a product knowledge file with:

```yaml
product_name: ""
audience: []
main_scenes: []
correct_usage_steps: []
visible_identity_details: []
approved_features: []
approved_claims: []
forbidden_claims: []
forbidden_visuals: []
required_reference_images: []
scene_reference_images: []
person_reference_rules: ""
notes_for_ai_video: ""
```

If these fields are missing, the product can still be discussed conceptually, but production output should mark missing facts/assets as blockers or review items.
