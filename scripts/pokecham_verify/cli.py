#!/usr/bin/env python3
"""Command router for PokeCham verifier.

All existing legacy commands remain available through scripts/verify.py. New
v29.43+ matrix commands are handled here with direction-explicit receipts.
"""
from __future__ import annotations

import json
import sys

from . import legacy
from .regression import run_all_regression_tests
from .switch_matrix import verify_switch_safety_matrix
from .type_matrix import verify_incoming_defense_matrix, verify_outgoing_attack_matrix, verify_type_matrix


def _load_json_arg(arg: str):
    return legacy._load_json_arg(arg)


def _parse_type_matrix_args(argv: list[str]):
    team_arg = None
    targets_arg = None
    mode = "both"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode" and i + 1 < len(argv):
            mode = argv[i + 1]
            i += 2
            continue
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
            i += 1
            continue
        if team_arg is None:
            team_arg = a
        elif targets_arg is None:
            targets_arg = a
        i += 1
    return team_arg, targets_arg, mode


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"status": "fail", "reason": "no command given"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd == "type-matrix":
            team_arg, targets_arg, mode = _parse_type_matrix_args(sys.argv[2:])
            if not team_arg:
                result = {"status": "fail", "reason": "type-matrix requires team JSON/path"}
            else:
                team_payload = _load_json_arg(team_arg)
                targets = _load_json_arg(targets_arg) if targets_arg else None
                result = verify_type_matrix(team_payload, targets=targets, mode=mode)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "incoming-defense-matrix":
            if len(sys.argv) < 3:
                result = {"status": "fail", "reason": "incoming-defense-matrix requires team JSON/path"}
            else:
                result = verify_incoming_defense_matrix(_load_json_arg(sys.argv[2]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "outgoing-attack-matrix":
            if len(sys.argv) < 4:
                result = {"status": "fail", "reason": "outgoing-attack-matrix requires our_team JSON/path and enemy_targets JSON/path"}
            else:
                result = verify_outgoing_attack_matrix(_load_json_arg(sys.argv[2]), targets=_load_json_arg(sys.argv[3]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "switch-safety-matrix":
            if len(sys.argv) < 3:
                result = {"status": "fail", "reason": "switch-safety-matrix requires board JSON/path"}
            else:
                result = verify_switch_safety_matrix(_load_json_arg(sys.argv[2]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "all-regression-tests":
            result = run_all_regression_tests()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        # Preserve every existing command and output shape.
        legacy._main()
    except IndexError:
        print(json.dumps({"status": "fail", "reason": f"missing arguments for command '{cmd}'"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
