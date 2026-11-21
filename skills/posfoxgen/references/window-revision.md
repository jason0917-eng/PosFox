# Bounded HTML reconstruction revision

This protocol changes PosFox orchestration and prompts only, never FigFox code.
G1 is an actual Harness visual inspection; G2 is a scoped native HTML repair.
Deterministic crops, object coverage and hashes do not detect visual defects.

## Budget and stopping

Declare `max_repair_rounds` before starting: 1 for the baseline, 2 by default,
3 as the experimental ceiling. These are provisional budgets, not measured
optimal counts. Initial reconstruction is round 0. A budget of K means at most
K G2 batches and K+1 G1 inspections, including verification after the last batch.
Zero findings after complete inspection means stop without a repair. Stop blocked
on exhausted budget, unchanged render, or an unchanged confirmed issue set after
a repair. Never silently declare success because a loop ended. Keep immutable
per-round HTML, renders, issue maps, window manifests and timings. Retain the
last valid version if a candidate regresses; verify the selected final bytes.

## Windows and coverage

Start from the generated design, independently of the HTML. Freeze every module
and every repeated occurrence with separate IDs, including small diagrams,
legends, strips, labels, bullets and connectors. During G1, scan the whole source
again for omissions from the roster itself; record a supplemental finding rather
than rewriting the intake-bound roster or ignoring the newly discovered part.

Use three views: whole-poster overview, complete module with neighbours, and
detail crops for small features. `visual_windows.plan_windows(roster)` produces
an overview and a context window for each module; optional feature `region`
values (absolute canvas coordinates) add detail windows. The default context
margin is 15% per side, clipped only at the canvas edge. This is a starting
parameter for evaluation. Inputs to this planner must share the roster canvas
size; for other DPI, map both sides explicitly before using `build_windows`.
Window planning supplies no marks or visual approval.

Inspect detail windows at native pixels or uniform viewer zoom (e.g. 2x/4x),
never distort a crop. Use the same scale on both sides and retain context views.
For each cross-module connector, band or relationship, add a bridge crop that
contains both endpoints and the full intervening structure. A fixed overlap
percentage alone cannot guarantee this. Record expected/observed occurrences,
window IDs and relationship endpoints. Every module needs a full-coverage
context window; a detail-only crop cannot satisfy the module evidence check.

## G1 prompt

> Compare the accepted generated poster with this exact HTML render. Read the
> generated side first. Enumerate every visible module in reading order, including
> small blocks and repeated instances; do not merge semantic duplicates. Compare
> each against its corresponding native location and frozen IDs. Inspect the
> overview, full module context and magnified detail. Check existence, occurrence
> count, content, order, parent/child grouping, labels, bullets, rules, background,
> and connector endpoints. Check boundaries and the gaps between modules. A
> surviving heading or DOM node does not prove the visual part is present.
> For each item report present, missing, partial, changed or uncertain with exact
> window coordinates and observed evidence. Uncertain/unviewed items cannot pass.
> Report confirmed defects with stable issue ID, module/feature IDs, expected and
> observed counts, consequence and smallest repair scope. Missing objects may
> use their intended IDs even when absent from the DOM. Dismiss only immaterial
> differences with a concrete reason. Do not suggest stylistic redesign.

## G2 prompt and post-repair G1

> Restore only the confirmed issue list using the accepted design and original
> scientific assets. Preserve existing correct modules and stable IDs. Return
> changed IDs and any shared CSS/layout dependencies. Do not delete duplicates,
> shrink unrelated text, or replace missing native content with a placeholder.

Render again. For every original issue record `restored`, `partial`, `unresolved`
or `uncertain` with fresh paired evidence; an edit log is not restoration proof.
Check count, visible content and local relationships, not just DOM existence.
Inspect neighbours and all modules affected by shared styles at detail scale.
Compare all previously correct modules against both the source and pre-repair
render; review the whole poster for reflow, clipping and displacement. Record
new regressions separately and include confirmed ones in the next bounded batch.
Only pass when all original defects are restored, no material regression remains,
and every module/relationship has been checked on the final render. Reuse that
actual final G1 for delivery review, not an earlier round's declarations.

## Single-round versus limited-round experiment

Use the same frozen generated image, initial HTML, model settings and issue
definitions in paired arms with K=1,2,3. Independently label true missing parts
from source/render comparisons, including small blocks, repeated occurrences,
boundary-straddling structures and a no-defect control. Seeded HTML deletions
provide known positives but must be reported separately from natural omissions.
Do not let the final evaluator see the repair budget or G1 verdict first.

Record per poster and round: true omissions, G1 detected omissions, false alarms,
verified restorations, remaining omissions, new regressions, inspected window
count, model calls and elapsed time. Report detection recall = detected true
omissions / true omissions, restoration rate = verified restorations / initial
omissions, and final clean-poster rate. Use N/A for zero denominators. Report
small/repeated/boundary categories separately and paired per-poster differences;
do not treat correlated windows as independent samples.

First compare K with identical window policy. Then hold K fixed and ablate
context margin (0%, 15%, 30%), detail zoom and explicit bridge windows. Publish
sample size, all unresolved cases and latency alongside quality. Select the
smallest budget whose extra round has no meaningful benefit under a predefined
quality/latency criterion. Until these runs exist, report the optimum as unknown.


## Text-specific G2 execution

For confirmed SVG wrapping, missing emphasis or mathematical layout defects, use the deterministic native text repair tool documented in the repository `references/svg-text-repair.md`. Bind exact object IDs and source evidence to its issue map. Preserve font size and source text, repair only triggered objects, and inspect the actual repaired SVG plus its independent render. Zero geometry blockers do not prove exact source line breaks or scientific correctness. Unsupported or ambiguous formulae remain blockers rather than guessed Unicode substitutions.

New G2 text repairs must use the `reference-guided` mode described there: freeze the generated image hash and exact reference lines per confirmed object, restore protected phrases such as `et al.` as one line unit, and treat split phrases as severe layout faults. Do not automatically reflow healthy neighbouring text. Keep containers, positions and font sizes fixed; adapt only letter spacing and leading according to measured overflow/overlap pixels. Audit the enclosing container and neighbouring text after the change. Do not grow a box, move an author/DOI line or keep compressing beyond readable bounds to obtain a passing report. Remaining collisions stay blocked, and clean paired windows must still be visually inspected.

During reconstruction and G1, record border presence as well as color: use `stroke: "none"` for fill-only regions and an explicit source-derived stroke/width for real frames. Never add a dark outline merely because the object is a rectangle. Check source emphasis colors separately from wrapping; a passing glyph geometry report cannot detect lost orange/gold emphasis. Restore only confirmed phrase colors with `emphasis[].color`, retaining fixed frames/fonts.
