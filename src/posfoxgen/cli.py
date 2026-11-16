"""CLI file tools; all model actions remain the responsibility of the Harness."""

import argparse
import json
from pathlib import Path
import sys

from .logic import read_object, validate_logic
from .memory import append_experience, retrieve_experience, select_best_valid
from .state import accept_stage, init_run, status_run, validate_delivery


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a pending run bound to a source PDF")
    init.add_argument("--run", required=True)
    init.add_argument("--paper", required=True)
    init.add_argument("--split", default="development")
    init.add_argument("--profile", choices=("posfoxgen-v3", "posfoxgen-v2", "legacy-v1"), default="posfoxgen-v3", help="New runs enforce measured source geometry and frozen design-roster fidelity")
    for name in ("status", "validate-delivery"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)
    logic = commands.add_parser("check-logic", help="Check provenance and independent review without calling a model")
    for name in ("assets", "logic", "panels"):
        logic.add_argument("--" + name, required=True)
    logic.add_argument("--review")
    logic.add_argument("--out")
    stage = commands.add_parser("accept-stage", help="Accept a sequential stage, binding file hashes and review")
    stage.add_argument("--run", required=True)
    stage.add_argument("--stage", required=True)
    stage.add_argument("--artifact", action="append", default=[], help="File path or key=path; repeat for each artifact")
    stage.add_argument("--review")
    stage.add_argument("--reviewer", default="harness")
    memory = commands.add_parser("memory", help="Append development evidence or retrieve relevant experience")
    memory.add_argument("action", choices=("append", "retrieve", "best"))
    memory.add_argument("--path", required=True)
    memory.add_argument("--entry")
    memory.add_argument("--issue", action="append", default=[])
    memory.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = init_run(args.run, args.paper, args.split, args.profile)
        elif args.command == "status":
            result = status_run(args.run)
        elif args.command == "validate-delivery":
            result = validate_delivery(args.run)
        elif args.command == "check-logic":
            result = validate_logic(args.assets, args.logic, args.panels, args.review)
            if args.out:
                Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        elif args.command == "accept-stage":
            artifacts = {}
            for item in args.artifact:
                if "=" in item:
                    key, value = item.split("=", 1)
                else:
                    key, value = Path(item).stem, item
                artifacts[key] = value
            result = accept_stage(args.run, args.stage, artifacts, args.review, args.reviewer)
        elif args.action == "append":
            if not args.entry:
                raise ValueError("memory append requires --entry")
            result = append_experience(args.path, read_object(args.entry))
        elif args.action == "retrieve":
            result = retrieve_experience(args.path, args.issue, args.limit)
        else:
            result = select_best_valid(read_object(args.path))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if isinstance(result, dict) and result.get("pass") is False else 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"pass": False, "status": "blocked", "error": str(error)}, ensure_ascii=False))
        return 2
