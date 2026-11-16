# 2026-11-17: FigFox pilot feedback and contract correction

The v2 pilot accepted removal of a repeated lower-left module and treated the surviving text as adequate coverage. It missed small orange dots and changes in vertical/text allocation. The historical issue map only repaired two arrows. This is the observed behavioral baseline; it is not evidence that those other visual differences were acceptable.

V3 preserves the generated visual roster independently of the native spec. Regression tests reproduce a module or bullet disappearing from both the manifest and native output, changed module area/color/text proportion, absent redline evidence, and missing measured source geometry. Tests must reject these even when other scientific text, tables and DOM geometry are correct.

The source-aspect exception remains: a1200x400 figure can be contained at600x200 inside a600x600 envelope. That cannot excuse deleting a repeated module or dropping orange dots beside a paragraph. The generation-only Skill now carries measurements and intended display frames; the full pipeline freezes the actual generated design before native construction and reviews every module through clean/marked paired windows.

This change updates the workflow and executable gates. It does not retroactively revise the old poster, replace historical review evidence, or demonstrate that a fresh v3 end-to-end poster run passed.
