"""Type matrix receipts for PokeCham teams.

Defensive matrix: every bundled attacking type into each active team form.
Offensive matrix: only actual move types present on the submitted sets into
explicit targets or, if targets are omitted, into the same team as a local sanity
matrix. Public type claims should cite typechart/type-matrix/damage receipts.
"""
from __future__ import annotations

from typing import Any

from . import legacy


def _team_list(team_payload: Any) -> list[dict]:
    team, _, _ = legacy._extract_team_list(team_payload)
    return team if isinstance(team, list) else []


def _target_list(targets: Any, fallback_team: list[dict]) -> list[Any]:
    if targets is None:
        return fallback_team
    if isinstance(targets, list):
        return targets
    if isinstance(targets, dict):
        if isinstance(targets.get("team"), list):
            return targets["team"]
        if isinstance(targets.get("targets"), list):
            return targets["targets"]
        if isinstance(targets.get("sets"), list):
            return targets["sets"]
    return []


def _display_slot(slot: dict, index: int) -> str:
    active = legacy.verify_active_form(slot)
    if active.get("status") == "pass":
        return active.get("display_name") or active.get("active_form", {}).get("name") or slot.get("pokemon") or f"slot_{index}"
    return str(slot.get("pokemon") or slot.get("name") or f"slot_{index}")


def _defender_query(slot_or_name: Any) -> str:
    if isinstance(slot_or_name, str):
        return slot_or_name
    if isinstance(slot_or_name, dict):
        active = legacy.verify_active_form(slot_or_name)
        if active.get("status") == "pass":
            return active.get("active_form", {}).get("name") or active.get("active_form_id") or slot_or_name.get("pokemon", "")
        types = slot_or_name.get("types")
        if types:
            return types if isinstance(types, str) else "/".join(types)
        return slot_or_name.get("pokemon") or slot_or_name.get("name") or ""
    return str(slot_or_name)


def _move_type(move_name: str) -> tuple[str | None, dict]:
    rec = legacy._global_entity_receipt("move", move_name)
    if rec.get("status") != "pass":
        return None, {"status": "fail", "reason": "move not found in 08", "move": move_name, "receipt": rec}
    move_type = str(legacy._move_global_type(move_name)).strip()
    if not move_type:
        return None, {"status": "fail", "reason": "move type missing in 08", "move": move_name, "receipt": rec}
    row = legacy._global_row("move", move_name)
    return move_type, {
        "status": "pass",
        "move": rec.get("name", move_name),
        "move_id": rec.get("id", legacy.normalize_id(move_name)),
        "type": move_type,
        "category": row.get("category", "") if row is not None else "",
        "source": "08_global_moves_abilities_items.csv",
    }


def _compact_type_receipt(rec: dict) -> dict:
    return {
        "entity": "type_effectiveness",
        "status": rec.get("status"),
        "display": rec.get("display"),
        "multiplier": rec.get("total_type_multiplier"),
        "multiplier_display": rec.get("multiplier_display"),
        "label": rec.get("label"),
        "defender_types": rec.get("defender_types"),
        "source": rec.get("source"),
    }


def build_defensive_matrix(team_payload: Any) -> tuple[dict, list, list]:
    team = _team_list(team_payload)
    matrix: dict[str, dict[str, dict]] = {}
    receipts: list[dict] = []
    failures: list[dict] = []
    for idx, slot in enumerate(team, start=1):
        defender_name = _display_slot(slot, idx)
        defender_query = _defender_query(slot)
        matrix.setdefault(defender_name, {})
        for atk in [legacy._TYPE_NAME[t] for t in sorted(legacy.VALID_TYPES)]:
            rec = legacy.verify_type_effectiveness(atk, defender_query)
            entry = _compact_type_receipt(rec)
            matrix[defender_name][atk] = entry
            receipts.append({"kind": "defensive", "defender": defender_name, "attacking_type": atk, "receipt": entry})
            if rec.get("status") != "pass":
                failures.append({"kind": "defensive", "defender": defender_name, "attacking_type": atk, "receipt": rec})
    return matrix, receipts, failures


def build_offensive_matrix(team_payload: Any, targets: Any = None) -> tuple[dict, list, list, list]:
    team = _team_list(team_payload)
    target_slots = _target_list(targets, fallback_team=team)
    matrix: dict[str, dict[str, dict]] = {}
    receipts: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []
    for idx, slot in enumerate(team, start=1):
        attacker_name = _display_slot(slot, idx)
        matrix.setdefault(attacker_name, {})
        for move in slot.get("moves", []) or []:
            move_type, move_receipt = _move_type(str(move))
            move_key = move_receipt.get("move", str(move))
            matrix[attacker_name].setdefault(move_key, {"move_receipt": move_receipt, "targets": {}})
            if not move_type:
                failures.append({"kind": "offensive", "attacker": attacker_name, "move": move, "receipt": move_receipt})
                continue
            if not target_slots:
                warnings.append({"kind": "offensive", "attacker": attacker_name, "move": move_key, "reason": "no targets supplied; offensive target matrix is empty"})
                continue
            for tidx, target in enumerate(target_slots, start=1):
                target_name = _display_slot(target, tidx) if isinstance(target, dict) else str(target)
                defender_query = _defender_query(target)
                rec = legacy.verify_type_effectiveness(move_type, defender_query)
                entry = _compact_type_receipt(rec)
                matrix[attacker_name][move_key]["targets"][target_name] = entry
                receipts.append({"kind": "offensive", "attacker": attacker_name, "move": move_key, "move_type": move_type, "target": target_name, "receipt": entry})
                if rec.get("status") != "pass":
                    failures.append({"kind": "offensive", "attacker": attacker_name, "move": move_key, "target": target_name, "receipt": rec})
    return matrix, receipts, failures, warnings


def verify_type_matrix(team_payload: Any, targets: Any = None) -> dict:
    team = _team_list(team_payload)
    if not team:
        return {"mode": "type_matrix", "status": "fail", "reason": "team payload must be a list or object with team/sets list"}
    team_receipt = legacy.verify_team(team_payload)
    defensive, def_receipts, def_failures = build_defensive_matrix(team_payload)
    offensive, off_receipts, off_failures, warnings = build_offensive_matrix(team_payload, targets=targets)
    failures = def_failures + off_failures
    return {
        "mode": "type_matrix",
        "engine_version": "v29.43-refactor-typematrix-docclean",
        "status": "pass" if not failures else "fail",
        "team_status": "pass" if team_receipt.get("team_ok") else "fail",
        "team_receipt": team_receipt,
        "team_gate": {
            "team_ok": team_receipt.get("team_ok"),
            "warnings": team_receipt.get("warnings", []),
        },
        "defensive_matrix": defensive,
        "offensive_matrix": offensive,
        "receipt_counts": {
            "defensive_typechart_receipts": len(def_receipts),
            "offensive_typechart_receipts": len(off_receipts),
        },
        "failures": failures,
        "warnings": warnings,
        "rule": "No public type matchup/weakness/resistance/coverage claim without direct typechart, type-matrix, or damage receipt provenance. Defensive matrix runs all bundled attacking types into every team slot; offensive matrix uses only actual move types on the submitted sets.",
    }
