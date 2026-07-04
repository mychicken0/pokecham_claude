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
from .report_engine import battle_report_template, render_battle_report
from .report_lint import battle_report_lint
from .meta_baseline import meta_baseline_gate, meta_baseline_lint
from .recommendation_lint import recommendation_provenance_lint
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

        if cmd == "meta-baseline-lint":
            if len(sys.argv) < 3:
                result = {"status": "fail", "reason": "meta-baseline-lint requires meta_baseline.json"}
            else:
                result = meta_baseline_lint(_load_json_arg(sys.argv[2]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "meta-baseline-gate":
            if len(sys.argv) < 4:
                result = {"status": "fail", "reason": "meta-baseline-gate requires team.json and meta_baseline.json"}
            else:
                fields = None
                if "--fields" in sys.argv:
                    i = sys.argv.index("--fields")
                    if i + 1 < len(sys.argv):
                        fields = [x.strip() for x in sys.argv[i + 1].split(",") if x.strip()]
                result = meta_baseline_gate(_load_json_arg(sys.argv[2]), _load_json_arg(sys.argv[3]), fields=fields)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "recommendation-provenance-lint":
            if len(sys.argv) < 4:
                result = {"status": "fail", "reason": "recommendation-provenance-lint requires answer.md and receipt.json"}
            else:
                with open(sys.argv[2], "r", encoding="utf-8") as f:
                    answer_text = f.read()
                result = recommendation_provenance_lint(answer_text, _load_json_arg(sys.argv[3]))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "battle-report-template":
            style = "standard"
            if "--style" in sys.argv:
                i = sys.argv.index("--style")
                if i + 1 < len(sys.argv):
                    style = sys.argv[i + 1]
            result = battle_report_template(style=style)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if cmd == "battle-report-render":
            if len(sys.argv) < 3:
                print("# Battle Report\n\nInvalid report payload: missing report JSON/path.")
                return
            style = "standard"
            if "--style" in sys.argv:
                i = sys.argv.index("--style")
                if i + 1 < len(sys.argv):
                    style = sys.argv[i + 1]
            payload = _load_json_arg(sys.argv[2])
            print(render_battle_report(payload, style=style), end="")
            return
        if cmd == "battle-report-lint":
            if len(sys.argv) < 4:
                result = {"status": "fail", "reason": "battle-report-lint requires answer.md and receipt.json"}
            else:
                style = "standard"
                if "--style" in sys.argv:
                    i = sys.argv.index("--style")
                    if i + 1 < len(sys.argv):
                        style = sys.argv[i + 1]
                with open(sys.argv[2], "r", encoding="utf-8") as f:
                    answer_text = f.read()
                receipt = _load_json_arg(sys.argv[3])
                result = battle_report_lint(answer_text, receipt, style=style)
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
