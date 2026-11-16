from pathlib import Path
import json
import subprocess
import sys
import fitz

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "skills" / "posfoxgen" / "scripts" / "run.py"


def test_skill_runner_top_level_help_discovers_routed_file_tools(tmp_path):
    result = subprocess.run([sys.executable, str(RUNNER), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for command in ("assets", "editable", "render"):
        assert f"  {command} " in result.stdout
        routed_help = subprocess.run([sys.executable, str(RUNNER), command, "--help"], cwd=tmp_path, capture_output=True, text=True)
        assert routed_help.returncode == 0, routed_help.stderr
        assert "--out" in routed_help.stdout


def test_skill_runner_initializes_a_real_run_outside_workspace(tmp_path):
    pdf = tmp_path / "source.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((30, 50), "A source-bound research result")
    doc.save(pdf)
    out = tmp_path / "run"
    result = subprocess.run([sys.executable, str(RUNNER), "init", "--run", str(out), "--paper", str(pdf)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    record = json.loads((out / "run.json").read_text())
    assert record["stage"] == "input"
    assert record["status"] == "pending"
    assert record["paper"]["sha256"]


def test_skill_runner_extracts_actual_source_without_model_service(tmp_path):
    pdf = tmp_path / "source.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((30, 50), "Measured value is 42")
    doc.save(pdf)
    out = tmp_path / "evidence"
    result = subprocess.run([sys.executable, str(RUNNER), "assets", str(pdf), "--out", str(out)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    table = json.loads((out / "asset_table.json").read_text())
    assert any("42" in x.get("text", "") for x in table["assets"])
