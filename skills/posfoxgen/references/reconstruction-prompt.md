# Single-response editable reconstruction

Use this short instruction with the actual generated design, approved paper-backed copy, source asset paths and user-selected reference. The generated poster supplies the composition; the reference is not a reason to redesign it. Use the current calling Harness model; “one API call” means one reconstruction response, not a newly provisioned API service.

> Convert this accepted poster design into complete editable HTML code (or SVG when explicitly requested). Return the complete artifact in one response.
>
> During this same intake, measure and freeze every visible module/feature in the generated-design roster before native code. Preserve module count, repeated modules, vertical area allocation, background/band colors, text proportions, orange dots/bullets and structural rules. Do not silently delete or simplify any of these.
>
> Record every text object's exact reference lines and mixed emphasis (weight, italic and color), and every region's border presence as well as its fill. A fill-only rectangle must use `stroke: "none"`; source frames need explicit color/width. Keep `et al.` and other protected phrases on their observed reference line. Include title/author and citation/DOI relationships in the intake record.
>
> Build in this order: canvas and major region positions; native panel shapes and rules; full source figures and native tables; native text with the observed hierarchy. Reuse the existing rendering vocabulary.
>
> Two execution priorities: preserve visual alignment, and keep every text run inside its frame. Use measured font sizes/line heights and adequate frame dimensions; preserve scientific wording and values. Do not solve overflow by silently dropping content.
>
> Keep source figures intact and at native size when they fit. Only shrink uniformly if necessary; never stretch either axis, crop away evidence, or fill a mismatched rectangle by deformation. Adjust the frame/spacing instead. Use exact original source figures for scientific evidence, and native text/rules/tables where appropriate. Do not flatten the whole poster into a bitmap.
>
> Prefer an already inspected complete source figure. If its caption would be duplicated or it cannot be placed legibly, run `assets paper.pdf --inspect-figure-page N --out source` through scripts/run.py. Inspect the numbered page alongside the clean candidate image and the generated slot. Match figure identity, all outer modules/axes, bottom labels and any in-figure title/legend. Reject running headers or duplicated external captions. Native PDF bounds are suggestions: if they omit content, use a verified explicit crop or keep the last complete asset. No percentage trimming.
>
> No SAM3, fixed 1/2 crops, separate reconstruction-plan report, strategy search, reward scoring or new renderer implementation. Include stable object IDs, source correspondences and concise required manifest/spec data with this response or obtain them by the existing deterministic exporter. Do not write a long explanation.

Save and render the response using existing deterministic tools. Follow [bounded window revision](window-revision.md): G1 inventories and compares all frozen modules and local relationships; G2 repairs confirmed issues within the predeclared budget. Re-render after each batch, verify each original missing part and check previously correct modules for regressions. Final evidence must come from the actual final render. Stop on pass, budget exhaustion or no progress and explicitly report unresolved defects.

For new G2 runs use `typography_repair.mode: "reference-guided"` and bind exact source-image evidence per confirmed issue. Freeze all containers, positions and font sizes at this stage. Restore source hard lines, then tighten tracking/leading only as far as measured overflow/overlap and readable bounds permit. Check neighbouring text and container enclosure after repair; geometry-only pass cannot waive missing colors/highlights or a split `et al.`. Run `scripts/run.py editable` for native SVG plus matching HTML, then render the actual HTML and verify the exact export bindings. `--html-only` is historical draft behavior and does not run this chain.
