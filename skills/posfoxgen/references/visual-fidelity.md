# Source geometry and generated-design fidelity

Use this contract for new `posfoxgen-v3` runs. Earlier v1/v2 receipts remain historical; they do not establish these stronger checks. Python checks declarations, byte bindings and native objects. The Harness must actually inspect the pixels; no validator or score can certify unobserved visual fidelity.

## Measure before generation

Every selected PDF figure/table carries: original PDF point size, actual cropped pixel size, aspect ratio, source hash and complete source location. `assets.py`/the generation Skill's `extract_pdf.py` now emit `geometry:{pdf_size_pt,pixel_size,aspect_ratio}`. Inspect the whole crop, including labels, before using its measurements. DPI alone is insufficient.

For each generation handoff image slot, record:

```json
{
  "source_geometry": [{"asset_id":"fig1","sha256":"actual-source-hash","pixel_size":[1200,400],"aspect_ratio":3.0}],
  "planned_frame": [100,300,900,300],
  "geometry_policy": "preserve_source_aspect"
}
```

Repeat these actual dimensions/ratios and intended display sizes in the image prompt, including for unattached visuals. Plan frames from the measured ratios before spending space on prose. `contain` permits an envelope with another ratio, while the complete figure inside retains its true aspect. `native_table` plus `native_table_source_checked:true` permits an exact, readable native reflow of table rows/cells; retain its source geometry and all approved data. Neither exception permits distorted scientific content. Actual image pixels must still be inspected on intake.

## Freeze two rosters before native construction

1. The approved content/panel plan lists the scientific modules and visuals generation must include. Missing planned modules cannot be erased from that plan to justify the generated result; use the existing regeneration budget or leave the fault blocked.
2. During the reconstruction executor's ordinary image intake, inventory **every actually visible module** in `design_roster.json`, including repeated semantic content, header/footer, mini diagrams, colored section bands, bullets/dots, swatches, leaders and rules. Freeze and bind this file in `image_reviewed` before writing native code. This is part of the same reconstruction invocation, not an extra model/planning stage.

Do not derive the frozen roster by copying a completed native spec. Preserve the generated arrangement even when a repeated module could be editorially removed. A semantic duplicate is still a real visual module. Scientific corrections must restore source truth while preserving its module/frame; a conflict that cannot be reconciled remains explicit.

The roster binds `generated_image_sha256`, `canvas:[width,height]` and `modules`. Each module has:

- Unique `id`, `native_panel_ids` (declared stable correspondences), measured reference `region:[x,y,w,h]`, `area_ratio`, `background`.
- `text_area_ratio`, `text_measurement` and explicit paper/design-specific `area_tolerance`, `frame_tolerance` (normalized x/y/width/height) and `text_area_tolerance`. Use the same measurement in both views: e.g. OCR bounding boxes or documented manual text rectangles divided by module area. Label manual estimates honestly. Tolerances cover explicitly justified measurement uncertainty, pixel rounding and inconsequential wrapping; record that reason per module. A numerically within-tolerance difference can pass only when the actual paired-window inspection finds no meaningful change to section boundaries or text balance. A confirmed visible layout departure still requires repair; tolerances never waive missing modules/features or color changes. Do not invent OCR measurements, compare glyph ink with OCR rectangles, or introduce universal density targets. If required evidence cannot be measured, leave it pending.
- `features:[{id,kind,count,color,native_object_ids}]`: enumerate required occurrences, including small orange dots beside a result paragraph. Map each module to distinct native panels and each feature occurrence to distinct native objects: two repeated modules cannot share the same surviving occurrence. Use separate stable objects for individual marks; matching a section heading does not account for its bullets. Color may be omitted for multi-color source images/native tables; preserve their other evidence separately.

The native reconstruction manifest embeds this exact frozen roster. Package the clean/redline window images and their observations in the final file manifest. Package `design_roster` under the same artifact name; v3 checks it against the intake receipt. A post-hoc native inventory cannot replace it.

## Bounded window walks with red-pen evidence

Traverse every roster module in reading order, with an overview for neighbouring modules/column context and detailed paired crops where needed. Each G1 inspection follows semantic regions rather than arbitrary halves; see [window-revision.md](window-revision.md). Generated and native images must be at a common comparison scale; preserve context and aspect. For source slots additionally inspect the authoritative original crop.

Retain clean paired windows and separate redline overlays. The inspector supplies the actual observed marks, never a tool's invented diagnosis. Outline the inspected region and label it `checked`; circle/box an actual discrepancy and label it `issue`. The red annotations are review evidence, never part of the poster. Use the reusable helper:

```sh
python -m posfoxgen.visual_windows --generated generated.png --native native.png --windows windows.json --out review/windows
```

Each input window has `id`, `generated_region`, `native_region`, and `marks:[{side:'generated'|'native',bbox:[x,y,w,h],kind:'checked'|'issue',label}]`. Mark coordinates are local to that side's crop. The helper preserves original image bytes and emits a clean pair, separate annotated image, both image hashes and a source-bound windows manifest. Point each review record to its actual window ID and manifest hash. The validator checks real, distinct decodable images, their sizes/hashes, and the full generated/native input hashes. Package all clean/marked images and the manifest. After each repair, create fresh source-bound windows and actually inspect the final render, including regression checks; retain earlier evidence separately. The helper does not infer defects.

For each module record `roster_checks` in the same fidelity review: `module_id`, `background_observed`, `text_area_ratio_observed`, `paired_window_path`, `redline_path`, `window_id`, `window_manifest_path`, its actual `window_manifest_sha256`, concrete `assessment`, and `feature_checks:[{feature_id,count_observed,color_observed}]`. Inspect vertical area allocation/order, background and section-band colors, text proportion/line flow, visual size, all bullets/dots/rules, and the whole-column stack. Do not inspect only text overflow and numeric truth.

## Repair every confirmed departure in the frozen issue list

A missing module, moved section boundary, wrong area allocation, missing band/bullet/dot/rule, wrong color or materially changed text proportion is a reconstruction fault. It does not become optional polish merely because the scientific prose survived, another panel repeats it, or the DOM passes. Resolve deviations against the frozen roster and observed generated design, with exact native IDs and paired redline evidence. Do not add speculative improvements or change the design.

The source-image exception is narrow: place the complete original at its true aspect and document the source-to-generated slot correspondence. It can explain an image's changed effective envelope; it cannot excuse deleting neighbouring modules, changing their colors/proportions, losing dots, shrinking prose, or rewriting the roster. Exact native table/source corrections likewise preserve the surrounding design. Do not broaden this into a general reconstruction-fidelity waiver.

Freeze each G1 issue list and run scoped G2 repairs under [window-revision.md](window-revision.md). Verify missing-part recovery and regressions after every batch, including the last allowed batch. Unresolved or uninspected discrepancies remain blocked. Finalize unchanged only after complete G1 coverage.
