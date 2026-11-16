import json
import os
import subprocess
import sys


def invoke(*args):
    return subprocess.run([sys.executable, "-m", "posfoxgen", *map(str, args)], capture_output=True, text=True)


def test_cli_init_and_pending_status(tmp_path):
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"paper")
    root = tmp_path / "run"
    result = invoke("init", "--run", root, "--paper", paper)
    assert result.returncode == 0, result.stderr
    status = invoke("status", "--run", root)
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["status"] == "pending"
    assert json.loads(status.stdout)["profile"] == "posfoxgen-v2"


def test_cli_can_explicitly_create_legacy_profile(tmp_path):
    paper = tmp_path / "paper.pdf"; paper.write_bytes(b"paper")
    result = invoke("init", "--run", tmp_path / "run", "--paper", paper, "--profile", "legacy-v1")
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["profile"] == "legacy-v1"


def test_delivery_validation_does_not_accept_missing_artifacts(tmp_path):
    paper = tmp_path / "paper.pdf"
    paper.write_bytes(b"paper")
    root = tmp_path / "run"
    invoke("init", "--run", root, "--paper", paper)
    result = invoke("validate-delivery", "--run", root)
    assert result.returncode != 0
    assert json.loads(result.stdout)["pass"] is False
