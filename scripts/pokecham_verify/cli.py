#!/usr/bin/env python3
"""Command router for PokeCham verifier.

All existing v29.42 commands delegate to legacy._main() to preserve behavior.
New v29.43 commands are handled here.
"""
from __future__ import annotations

import json
import sys

from . import legacy
from .regression import run_all_regression_tests
from .type_matrix import verify_type_matrix


def _load_json_arg(arg: str):
    return legacy._load_json_arg(arg)


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"status": "fail", "reason": "no command given"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd == "type-matrix":
            if len(sys.argv) < 3:
                result = {"status": "fail", "reason": "type-matrix requires team JSON/path"}
            else:
                team_payload = _load_json_arg(sys.argv[2])
                targets = None
                if len(sys.argv) > 3:
                    targets = _load_json_arg(sys.argv[3])
                result = verify_type_matrix(team_payload, targets=targets)
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
