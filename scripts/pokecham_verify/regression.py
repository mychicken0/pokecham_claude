"""Regression helpers for PokeCham verifier."""
from __future__ import annotations

from . import legacy


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

    return {
        "mode": "all_regression_tests",
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "rule": "Run before and after verifier refactors. Existing public CLI compatibility is preserved by scripts/verify.py facade.",
    }
