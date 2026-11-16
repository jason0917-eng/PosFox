# Fixed generation brief

这是一张供同行阅读的完整科研海报。先讲清问题、输入、输出、模型和创新，再用主要实验与关键指标支撑结论。保留足够的正文解释，不能把论文缩成几句口号；也不能靠缩小字号增加密度。优先展示论文中清楚、漂亮且有信息量的原图。每个已规划的图和表都必须实际画出完整内容，保留轴、图例、标签、数值、箭头和比较条件，禁止空框、示意占位、待补图或只写图名。图文就近，同类元素对齐，阅读顺序清楚，相关模块颜色连贯，背景统一，少量对比色强调重点。使用事先选定的常规字体，标题、正文与图内标签有清楚的层级。用足画面并保持科学内容可读，不凭空添加灰色小字、装饰性注释或分号串起的泛泛解释。必要限制写进正常大小的正文。分隔线、标题线和表格线属于结构，不能在重建时丢失。不借入参考海报的科研内容或标志。

# Before generation: content debate

Read the whole paper and inventory its figures/tables. Three participants read one frozen shared packet in parallel. Each returns one initial report, which may be detailed. Then permit one brief callback debate on disputed issue IDs only, without another full report or full-packet reread. Their roles are:

- Content advocate: what scientific substance, innovation, useful figures or quantitative evidence is missing? Show the strongest source figures when useful, not merely whichever crop fits a spare rectangle.
- Science reviewer: are the input/output/model and causal or evaluation relations correct? Are settings, baselines, uncertainties and numerical units kept? Does a compact claim overstate a result?
- Visual planner: can a technical reader find the story, architecture and results at poster scale? Balance content-rich text and large evidence. Do not resolve overfull panels by tiny text or silently deleting methods/limits.

Write directly: issue → source evidence → exact change → consequence. The initial report may be substantial, but avoid unnecessary recap. After that, return only short callback positions on explicit disagreements; no second long report. The main executor merges duplicate issues, resolves the bounded callback debate, applies accepted changes and verifies affected content without another broad review round. Every participant applies rigor, protects what already works, and asks why not: justify both changing and retaining the original with evidence and concrete consequences. Preserve actual reviewed snapshots and authorship. Record each position and the resolved decision with source IDs. Every technical-story item (problem, input, output, model, innovation, key metrics, source figures) and the overall logic must have a decision. Unresolved blockers stop generation. This debate is our adaptation, not a claim about upstream implementations. If another agent is unavailable, disclose actual role-pass independence as described in workflow.md.

# Per-module instructions

Give each module its purpose, exact substantive copy, evidence/source IDs, every visual to draw, intended rectangle/aspect, adjacent explanation, typography and reading position. State what input reaches what model/component and what output is produced. Give exact values and comparison settings. Decide paper-specific content/word/area budgets from its scientific story and the selected reference; record whether a constraint comes from the user or the planner. There is no universal minimum word count or OCR-area threshold.

Attach at most five reference/source images with distinct roles. A tool attachment limit never permits an empty scientific slot: supply the remaining visual's complete labels, relationships, values and visual instructions, and draw it in the generated result. Inspect every output visual immediately. If it is globally wrong or absent, regenerate from the responsible plan. Local inaccuracies can be reconstructed only with a recorded design correspondence and later review.

# Reconstruction brief

First measure the actual generated poster; do not substitute the planner's earlier imagined layout. Map every panel, figure/table, rule and text style. Preserve intended typography, positions, line lengths, alignment and background. Source aspect ratio takes precedence over filling the generated visual envelope. Use native text and tables when they reproduce the design more faithfully than pasted white source crops. Tables may extend columns/rows to their planned frame without stretching glyphs. Source plots must retain full axes/legends; use an intentional source replacement that occupies the generated design's visual envelope. Never choose an arbitrary subfigure simply because a box is narrow. Images must never be stretched independently along either axis. Keep native size when it fits; only shrink uniformly when necessary to fit. The exporter uses scale-down and SVG preserves aspect ratio. Adjust the container, whitespace or layout instead of deforming the image. Legacy allow_distortion and distortion_reason cannot waive this rule. Scaling is enforced mechanically; do not add a separate visual inspection or reviewer round for scaling. Existing scientific/content and overall design reviews retain their own scope. Fix visible background seams. Confirm requested fonts actually resolve in the renderer; SVG wrapping must use the selected family too.

Inspect generated and reconstructed posters side by side, panel by panel and globally. Check the eight user-raised failures: omitted rules, missing/generated placeholder visuals, sparse scientific content, font mismatch, wrong visual dimensions, background patchwork, alignment, and unnecessary gray microcopy. A passing DOM check or correct scientific prose does not establish design fidelity.

# Evidence and scoring

Read the project research record `references/poster-quality-research.md` and its source links for the exact provenance. PosterBench's faithfulness/coverage/density/visual-evidence/layout/readability/aesthetics weights are 10/10/15/10/20/25/10. Use them as a disclosed local diagnostic when assessed by the Harness; that is not official PosterBench execution. Paper2Poster additionally separates image quality, layout and aesthetics. Our generated-to-native fidelity gate complements those quality judgments.

Earlier communication sources: BioRender https://www.youtube.com/watch?v=PzTPtwhZYYU and Mike Morrison https://www.youtube.com/watch?v=SYk29tnxASs (English captions inspected). Apply hierarchy, alignment and evidence communication without forcing BetterPoster's billboard format. PosterBench's density calibration values and an individual university's word guidelines are not universal poster laws.


# User generation budget

Generate one initial image and allow at most one regeneration (two image-generation calls total). Do not run a standalone generated-image review agent or review round. The reconstruction executor reads the generated design as part of normal reconstruction intake, records actual slot completeness and blockers with review_mode:"reconstruction_intake", its real reviewer name and independent:false, and proceeds directly to reconstruction. Do not claim an independent image review occurred. Keep the existing image_reviewed receipt for compatibility, with real image/plan hashes and observations. If a global fault requires regeneration, use the single retry; unresolved faults after it remain explicitly blocked rather than triggering more generation calls.


# Conditional reconstruction repair

## One visual issue map, conditional repair

After native reconstruction, make one source/generated-versus-native paired-window comparison, grouped by semantic regions (header, methods, evidence, results), not a fixed half-image split. This is the single fidelity inspection; reuse it for fidelity_review and final review rather than launching duplicate reviewer rounds. Preserve context, aspect and a common comparison scale. Window cropping is a deterministic operation, not a model stage.

Write visual_issue_map.json as a concise list of candidate issues. An effective issue must identify: a concrete observed defect; paired evidence paths and window coordinates; exact native object IDs; the relevant approved design/source requirement; the visible or reading/scientific consequence; a scoped repair action; and certainty. Mere stylistic alternatives, a vague score improvement, uncertain observations, or a difference with no material consequence do not authorize edits. Retain their dismissal reason briefly, without generating a repair plan. A confirmed scientific/content defect or real overflow remains material even if the rest of the poster looks good.

If there are no effective issues, proceed reconstructed → finalized directly using the inspected original reconstruction. Do not create an empty repair transaction, a fake repairing receipt, a reward report or a mandatory trajectory-optimization cycle. Existing actual-file/export checks remain applicable; passing means no material unresolved defect was observed, not that an unperformed inspection passed.

If effective issues exist, freeze that issue list and execute one scoped local repair batch against those object IDs only. Do not reopen design debate, add optional polish targets, optimize global scores, write reusable strategy memory, or broaden to tool development in this run. Rerender and check the affected objects plus mechanical export integrity; do not restart the full window-review cycle. If a material issue remains after the batch, report it explicitly rather than silently iterating. Review evidence/hash bindings must describe the actual version inspected; do not claim the final render was inspected if only the earlier version was viewed.
