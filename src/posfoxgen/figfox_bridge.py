"""Reuse FigFox's deterministic edit engine without importing its model transports."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


def apply_native_plan(svg: str, findings: dict, plan: dict, implementation: dict,
                      out_dir: str | Path, source_image: str | Path | None = None,
                      vendor_root: str | Path | None = None) -> dict:
    root = Path(vendor_root) if vendor_root else Path(__file__).resolve().parents[2] / "vendor" / "figfox"
    contract_path = root / "src" / "figfox_plus" / "factual" / "contracts.py"
    if not contract_path.is_file():
        raise FileNotFoundError("download the pinned FigFox source snapshot before native execution")
    spec = importlib.util.spec_from_file_location("posfoxgen_figfox_native_contracts", contract_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import xml.etree.ElementTree as ET
    canvas = ET.fromstring(svg)
    width, height = float(canvas.get("width")), float(canvas.get("height"))
    module.validate_findings(findings, width, height)
    module.validate_plan(plan, findings, svg)
    module.validate_implementation(implementation, plan, svg)
    edits = [edit for transaction in implementation["transactions"] for edit in transaction["edits"]]
    final, journal = module.apply_edits(svg, edits, str(source_image) if source_image else None)
    receipt = {
        "engine": "FigFox factual.contracts", "sam": False, "model_api_calls": 0,
        "engine_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "initial_sha256": hashlib.sha256(svg.encode()).hexdigest(),
        "final_sha256": hashlib.sha256(final.encode()).hexdigest(),
        "execution_accepted": True, "visual_quality_pass": None,
        "unresolved": plan["unresolved"], "journal": journal,
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "initial.svg").write_text(svg)
    (out / "repaired.svg").write_text(final)
    for name, value in [("findings", findings), ("plan", plan), ("implementation", implementation), ("native-receipt", receipt)]:
        (out / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2))
    return {"svg": final, "receipt": receipt}
