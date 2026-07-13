# Output QA Checklist

Use this checklist before delivering scripts, shot lists, SeedDance prompts, generated clips, or editing task packages.

## Blockers

Stop and ask for human review or mark as blocked if any item is true:

- Target product is unclear.
- Product-visible shot has no approved **white-background hero** reference or source path.
- Usage or scene shot has no matching **scenario image** reference when one exists for the selected scene tag.
- Structural demo shot has no **detail / usage-step** reference when one exists for that action.
- Final output deviates from the approved script (shot order, dialogue, timing, or CTA changed without revision).
- Product usage contradicts the product document.
- Obvious **physics or usage-scene error** (wrong pour direction, bottle inside cup, impossible grip, scene/use mismatch).
- A claim is not backed by product docs or approved material.
- Competitor brand/logo/model appears in consumer-facing output.
- Scene or person continuity breaks in a way that changes the story.
- AI output invents product appearance, UI, logo, accessory, bottle type, or product structure.
- AI output **modifies** product appearance relative to the white-background hero (recolor, reshape, simplify, or restyle).
- Maternal/baby product content includes prohibited medical, lactation, safety, or guarantee claims.

## Source and material checks

- Product docs were loaded from the local product folder, local knowledge fallback, or DS223.
- DS223 status is clear: refreshed, unavailable, or not needed.
- Every asset has a source path, generated asset id/path, or missing-asset status.
- Approved assets are separated from reference-only and prohibited assets.
- Product image role is clear: identity, usage, scene, detail/proof, person, or generated.

## Script logic checks

- The hook identifies the target audience or pain quickly.
- The script follows scene -> pain -> product solution -> safe demo/proof -> CTA.
- The product enters naturally from the scene.
- The script does not copy competitor wording.
- CTA is appropriate to the platform and does not overpromise.

## Visual continuity checks

- Main scene is defined and stable.
- Scene changes have a reason.
- Props, lighting, product placement, and time of day remain coherent.
- Lighting is realistic (motivated source, soft shadows, plausible reflections) without altering product identity.
- If a person appears, role, age range, wardrobe, hair, hands, and emotional state are consistent **across the whole video**.
- If consistency cannot be maintained, product-only or hands-only shots are used.

## Product-use checks

- Demonstration follows approved usage steps and the matching scenario image.
- Product-visible details match the **white-background hero** and relevant **detail images**.
- Pour/open/charge/assembly actions follow **physics-safe** motion and container relationships.
- Accessories and containers are approved.
- Forbidden visuals are excluded.
- Detail/proof images support only the exact safe wording used.

## Compliance checks

- No unsupported medical, diagnostic, treatment, guarantee, superlative, certification, or quantified claim.
- No restricted lactation terms for breast pump content.
- No unsafe baby/maternal scene.
- No AI-generated b-roll presented as real proof.
- No hidden competitor comparison in consumer-facing language.

## Delivery package checks

The final package should include:

- Final script.
- Subtitle/SRT or subtitle lines when needed.
- Shot list with time ranges.
- Asset manifest.
- Shot-to-asset map.
- AI prompt list with source refs and negative constraints.
- Editing notes for overlays, captions, music, sound effects, crops, and exports.
- Human-review blockers and warnings.

## Output risk labels

Use these labels in final reviews:

- `PASS`: ready for editor/human review with no known blocker.
- `WARNING`: usable, but has a noted risk or missing nice-to-have asset.
- `BLOCKED`: cannot safely produce or publish until a source, asset, claim, or human decision is provided.
