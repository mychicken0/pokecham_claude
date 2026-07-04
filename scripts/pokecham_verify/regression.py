"""Regression helpers for PokeCham verifier."""
from __future__ import annotations

from pathlib import Path

from . import legacy
from .switch_matrix import verify_switch_safety_matrix
from .type_matrix import verify_incoming_defense_matrix


def _fixture_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def run_all_regression_tests() -> dict:
    checks = []
    failures = []

    def add(name: str, receipt: dict, expected_status: str = "pass"):
        checks.append({"name": name, "receipt": receipt})
        if receipt.get("status") != expected_status:
            failures.append({"name": name, "expected": expected_status, "actual": receipt.get("status"), "receipt": receipt})

    add("mechanic-data-lint", legacy.verify_mechanic_data_lint())
    add("mechanic-coverage", legacy.verify_mechanic_coverage())

    # Mirror existing CLI regression intent without shelling out.
    type_cases = [
        ("Ghost", "Dark", 0.5, "resisted"),
        ("Ghost", "Normal", 0.0, "immune"),
        ("Ghost", "Dark/Normal", 0.0, "immune"),
        ("Fire", "Steel/Dragon", 1.0, "neutral"),
        ("Ground", "Flying", 0.0, "immune"),
        ("Ground", "Sinistcha", 0.5, "resisted"),
        ("Fire", "Kingambit", 2.0, "super_effective"),
    ]
    type_failures = []
    type_receipts = []
    for atk, defender, expected, label in type_cases:
        rec = legacy.verify_type_effectiveness(atk, defender)
        type_receipts.append(rec)
        if rec.get("status") != "pass" or float(rec.get("total_type_multiplier", -1)) != expected or rec.get("label") != label:
            type_failures.append({"case": f"{atk} -> {defender}", "expected": expected, "expected_label": label, "receipt": rec})
    add("type-regression-tests", {"mode": "type_regression_tests", "status": "pass" if not type_failures else "fail", "receipts": type_receipts, "failures": type_failures})

    typepassive_cases = [
        {"name": "Dark blocks opposing Prankster Taunt", "scenario": {"defender": {"types": ["Dark"]}, "incoming": {"move": "Taunt", "category": "Status", "source_ability": "Prankster", "side": "opponent"}}, "expect": "pass"},
        {"name": "Ground blocks Thunder Wave", "scenario": {"defender": {"types": ["Ground"]}, "incoming": {"move": "Thunder Wave"}}, "expect": "pass"},
    ]
    tpass_failures = []
    tpass_receipts = []
    for c in typepassive_cases:
        rec = legacy.verify_typepassive(c["scenario"])
        tpass_receipts.append({"name": c["name"], "receipt": rec})
        if rec.get("status") != c["expect"]:
            tpass_failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
    add("typepassive-regression-tests", {"mode": "typepassive_regression_tests", "status": "pass" if not tpass_failures else "fail", "receipts": tpass_receipts, "failures": tpass_failures})

    mechanic_cases = [
        {"name": "Intimidate vs Contrary", "scenario": {"actor": {"ability": "Intimidate"}, "target": {"ability": "Contrary"}}, "expect": "pass"},
        {"name": "Pixilate Hyper Voice", "scenario": {"actor": {"ability": "Pixilate", "move": "Hyper Voice"}}, "expect": "pass"},
    ]
    mech_failures = []
    mech_receipts = []
    for c in mechanic_cases:
        rec = legacy.verify_interaction(c["scenario"])
        mech_receipts.append({"name": c["name"], "receipt": rec})
        if rec.get("status") != c["expect"]:
            mech_failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
    add("mechanic-regression-tests", {"mode": "mechanic_regression_tests", "status": "pass" if not mech_failures else "fail", "receipts": mech_receipts, "failures": mech_failures})

    # v29.44 direction-explicit matrix regressions.
    type_team = legacy._load_json_arg(str(_fixture_path("tests", "fixtures", "teams", "type_matrix_sinistcha.json")))
    incoming = verify_incoming_defense_matrix(type_team)
    ground_sin = ((incoming.get("rows") or {}).get("Sinistcha") or {}).get("Ground") or {}
    if incoming.get("status") != "pass" or ground_sin.get("value_display") != "0.5x taken":
        failures.append({"name": "incoming-defense-matrix-ground-sinistcha", "expected": "0.5x taken", "actual": ground_sin, "receipt": incoming})
    checks.append({"name": "incoming-defense-matrix-ground-sinistcha", "receipt": incoming})

    board = legacy._load_json_arg(str(_fixture_path("tests", "fixtures", "boards", "switch_charizard_weatherball_vs_p2.json")))
    switch = verify_switch_safety_matrix(board)
    expected_switch = {
        ("Kingambit", "Charizard-Mega-Y / Weather Ball [Fire]"): "2x taken",
        ("Sylveon", "Charizard-Mega-Y / Weather Ball [Fire]"): "1x taken",
        ("Dragonite", "Tyranitar / Rock Slide [Rock]"): "2x taken",
        ("Garchomp", "Charizard-Mega-Y / Thunderbolt [Electric]"): "0x taken",
    }
    switch_failures = []
    rows = switch.get("rows") or {}
    for (mon, move_label), expected in expected_switch.items():
        got = (((rows.get(mon) or {}).get("incoming_moves") or {}).get(move_label) or {}).get("value_display")
        if got != expected:
            switch_failures.append({"case": f"{mon} vs {move_label}", "expected": expected, "actual": got})
    if switch.get("status") != "pass" or switch_failures:
        failures.append({"name": "switch-safety-matrix-charizard-weatherball", "expected": "pass", "actual": switch.get("status"), "matrix_failures": switch_failures, "receipt": switch})
    checks.append({"name": "switch-safety-matrix-charizard-weatherball", "receipt": switch, "matrix_failures": switch_failures})

    # v29.44 lint gates: switch advice without matrix must fail; same advice with
    # a switch matrix receipt must pass hard failures.
    bad_answer = _fixture_path("tests", "fixtures", "answers", "answer_bad_switch_no_matrix.md")
    good_answer = _fixture_path("tests", "fixtures", "answers", "answer_good_switch_with_matrix.md")
    empty_receipt = _fixture_path("tests", "receipts", "receipt_empty.json")
    switch_receipt = _fixture_path("tests", "receipts", "receipt_switch_safety_charizard_weatherball.json")
    bad_lint = legacy.lint_public_output(bad_answer.read_text(), legacy._load_json_arg(str(empty_receipt)))
    good_lint = legacy.lint_public_output(good_answer.read_text(), legacy._load_json_arg(str(switch_receipt)))
    bad_codes = {f.get("code") for f in bad_lint.get("failures", [])}
    if "FAIL_SWITCH_RECOMMENDATION_WITHOUT_ACTION_MATRIX" not in bad_codes:
        failures.append({"name": "lint-switch-without-matrix", "expected_code": "FAIL_SWITCH_RECOMMENDATION_WITHOUT_ACTION_MATRIX", "receipt": bad_lint})
    if good_lint.get("status") != "pass":
        failures.append({"name": "lint-switch-with-matrix", "expected": "pass", "actual": good_lint.get("status"), "receipt": good_lint})
    checks.append({"name": "lint-switch-without-matrix", "receipt": bad_lint})
    checks.append({"name": "lint-switch-with-matrix", "receipt": good_lint})

    return {
        "mode": "all_regression_tests",
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "rule": "Run before and after verifier refactors. v29.44 preserves CLI compatibility and adds direction-explicit incoming/outgoing/switch matrix gates.",
    }
