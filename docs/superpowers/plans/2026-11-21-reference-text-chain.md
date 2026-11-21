# Reference-guided text repair

User-approved scope: compare against generated target, edit only confirmed text defects, preserve exact reference lines, then audit fixed containers and adapt only tracking/leading and verify neighbours. Healthy objects stay unchanged.

1. Regression tests: supplied reference lines must never wrap again; reference-guided mode only touches explicit issue IDs; fixed containers never change and typography cannot collide with neighbouring text.
2. Extend measured SVG repair with opt-in reference-guided scope, required source image SHA binding and exact lines, and post-text container checks. Keep legacy mode for historical callers. Carry mode through deterministic exporter replay.
3. Keep all rectangles and font sizes fixed. Estimate overlap/overflow pixels and reduce only letter spacing and line height on explicit targets; remeasure within finite readable limits. Classify split protected phrases (et al.) as severe and restore reference lines. Retain blockers when spacing cannot fit.
4. Reconstruct the user-provided gravitational-wave generated design (left screenshot panel), using original paper Figure 1. Freeze initial image/spec and issue list; run revised chain and actual exports, inspect generated/initial/final and affected windows.
5. Run focused then full tests. Record limitations and actual source/target hashes. Do not label full pipeline formally accepted without required gates.
