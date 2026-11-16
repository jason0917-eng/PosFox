#!/usr/bin/env python
"""Route local deterministic tools; model tasks remain in the calling Harness."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

FILE_TOOLS = {
    "assets": ("assets", "Extract PDF text, page previews and inspected crops"),
    "editable": ("editable", "Build draft editable HTML from a poster spec"),
    "render": ("render", "Render local HTML to PNG/PDF and inspect geometry"),
}

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command in FILE_TOOLS:
        del sys.argv[1]
        runpy.run_module("posfoxgen." + FILE_TOOLS[command][0], run_name="__main__")
    else:
        try:
            runpy.run_module("posfoxgen", run_name="__main__")
        except SystemExit as error:
            if sys.argv[1:] in (["-h"], ["--help"]) and error.code in (None, 0):
                print("\nRouted file tools (run.py COMMAND --help for options):")
                for name, (_, description) in FILE_TOOLS.items():
                    print(f"  {name:<18}{description}")
            raise
