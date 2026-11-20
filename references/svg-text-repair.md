# Native SVG text repair

Run this deterministic tool after a confirmed typography issue, before closing
G2 or accepting final exports. It repairs existing SVG nodes, not the poster's
scientific content. Original inputs must remain untouched.

```sh
pip install -e '.[text-repair]'
# Use an already installed Chrome; no browser download is required.
# Install librsvg/rsvg-convert for independent SVG-to-PNG verification.
PYTHONPATH=src python -m posfoxgen.svg_text_repair path/to/poster.svg \
  --spec path/to/poster_spec.json --issues confirmed-text-issues.json --out repaired
```

The spec supplies the native object IDs, text, font sizes, text frames and panel
offsets missing from ordinary SVG text. Text-frame geometry must describe the
actual SVG; this is not a generic repair tool for arbitrary unindexed SVG files.

## Issue contract

The issue map is keyed by exact object ID. Only supply observations grounded in
paired source/generated and native image windows. Retain the evidence path and
issue ID in the caller's G1/G2 transaction records.

```json
{
  "body-copy": {
    "emphasis": [
      {"text": "Important result", "font_weight": 600},
      {"text": "Measured improvement", "font_weight": 800}
    ],
    "lines": ["First exact reference line", "Second exact reference line"]
  },
  "equation": {
    "math_runs": [
      {"text": "QKT/sqrt(d_k)", "latex": "\\frac{QK^T}{\\sqrt{d_k}}"}
    ]
  }
}
```

`lines` must preserve the complete source text modulo whitespace. Alternatively,
`rewrap_soft_breaks: true` discards isolated obsolete newlines and recomputes wraps;
blank-line paragraph boundaries remain. Do not use it on verified reference lines.
`style` may set `font_family`, `font_style` and `font_weight`, only with source
evidence. It cannot shrink font size or change panel geometry. Overlapping
emphasis/formula ranges are rejected; divide them into disjoint runs.

## Mechanism and limits

- G1 triggers: actual SVG glyph bounds outside a spec frame; explicit issue-map
  targets; Unicode script characters needing structural layout. Healthy text with
  no trigger is retained. Original images, rules and other native objects remain.
- Browser Range measurements determine wrapping, inline font weight and each
  baseline. SVG receives explicit `tspan` positions, not browser-only CSS wrapping.
- Regular/medium/semibold/bold/heavy/black correspond to 400/500/600/700/800/900.
  Reports isolate emphasized objects and their exact runs. Real weight availability
  depends on the chosen font: Arial's regular/bold faces cannot supply six genuinely
  distinct weights. Browser synthesis is not proof of exact source-weight recovery.
- Unicode script glyphs become positioned ordinary letters/digits with reduced
  script size. Ambiguous scientific notation such as ΩM is never silently guessed.
  Supply the source-verified TeX explicitly. Unsupported TeX raises an error.
- Formula runs use Matplotlib MathText's supported TeX subset and native SVG paths,
  with the source expression in `data-latex`; they are movable formula units, not
  individually editable text letters. No screenshot or foreignObject replaces them.
  Unsupported full-LaTeX constructs need a real TeX backend or retained blocker.
- Final SVG is re-opened for geometry checks and independently rasterized by
  librsvg. A surviving overflow is reported, never clipped or concealed by smaller
  type. Font portability, original line-count fidelity, exact emphasis recovery
  and scientific correctness still require paired visual inspection; zero frame
  blockers alone is not full poster acceptance.

Outputs: `poster.svg`, `poster.png`, `text-repair-report.json`. The report separates
before/after geometry, applied targets, emphasized runs/levels, compiled formulae
and remaining blockers. Do not reuse HTML-only acceptance for SVG delivery.


## Integrated deterministic export and repeat execution

A spec may opt in with `typography_repair: {format: "posfoxgen-svg-text-repair-v1", issues: {...}}`. `export_svg` then replays the measured repair after its base export and creates HTML from that same native SVG. The formal export-binding validator regenerates the full sequence; it does not waive signature checks. This opt-in replay requires the optional text-repair dependencies, a local Chrome and rsvg-convert. Normal exports remain unchanged.

Repeated repair removes prior formula groups for each affected owner before inserting replacements. Retyping an existing formula without its original math_runs is rejected rather than losing its semantic source. `style_runs: [{text: "exact phrase", font_style: "italic"}]` supports partial italic styling without changing the rest of a paragraph; overlapping style/formula requests must remain disjoint.

Formula references use SVG2 `href` instead of an arbitrary XML namespace prefix: the latter can work in an XML SVG viewer but fail when inlined into HTML. HTML rendering now reports SVG glyph-frame checks separately from HTML scroll metrics, and checks each formula use reference and its visible geometry. Final acceptance still requires inspecting actual screenshots: reference checks alone do not prove exact source fidelity.
