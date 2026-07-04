"""Direction-explicit type matrix receipts for PokeCham teams.

v29.44 intentionally avoids ambiguous names like "attack table"/"def table".
Use these receipt kinds instead:

* INCOMING_DEFENSE_MATRIX: ENEMY MOVE TYPE -> OUR DEFENDER, cell = x taken.
* OUTGOING_ATTACK_MATRIX: OUR MOVE -> ENEMY DEFENDER, cell = x dealt.

Public switch/type/coverage advice should cite these matrices, a direct
``typechart`` receipt, a ``switch-safety-matrix`` receipt, or a complete damage
receipt with typechart provenance.
"""
from __future__ import annotations

from typing import Any

from . import legacy

ENGINE_VERSION = "v29.44-action-matrix-switchgate"
INCOMING_KIND = "INCOMING_DEFENSE_MATRIX"
OUTGOING_KIND = "OUTGOING_ATTACK_MATRIX"
INCOMING_DIRECTION = "ENEMY_MOVE_TYPE_TO_OUR_DEFENDER"
OUTGOING_DIRECTION = "OUR_MOVE_TO_ENEMY_DEFENDER"


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
        "attacking_type": rec.get("attacking_type"),
        "defender_types": rec.get("defender_types"),
        "source": rec.get("source"),
    }


def _taken_cell(rec: dict) -> dict:
    entry = _compact_type_receipt(rec)
    entry.update({
        "cell_semantics": "damage_multiplier_taken_by_defender",
        "public_cell_suffix": "taken",
        "value_display": f"{entry.get('multiplier_display')} taken",
    })
    return entry


def _dealt_cell(rec: dict) -> dict:
    entry = _compact_type_receipt(rec)
    entry.update({
        "cell_semantics": "damage_multiplier_dealt_to_enemy_defender",
        "public_cell_suffix": "dealt",
        "value_display": f"{entry.get('multiplier_display')} dealt",
    })
    return entry


def build_incoming_defense_matrix(team_payload: Any) -> tuple[dict, list, list]:
    team = _team_list(team_payload)
    rows: dict[str, dict[str, dict]] = {}
    receipts: list[dict] = []
    failures: list[dict] = []
    for idx, slot in enumerate(team, start=1):
        defender_name = _display_slot(slot, idx)
        defender_query = _defender_query(slot)
        rows.setdefault(defender_name, {})
        for atk in [legacy._TYPE_NAME[t] for t in sorted(legacy.VALID_TYPES)]:
            rec = legacy.verify_type_effectiveness(atk, defender_query)
            entry = _taken_cell(rec)
            rows[defender_name][atk] = entry
            receipts.append({
                "matrix_kind": INCOMING_KIND,
                "direction": INCOMING_DIRECTION,
                "our_defender": defender_name,
                "enemy_move_type": atk,
                "cell": entry,
            })
            if rec.get("status") != "pass":
                failures.append({"matrix_kind": INCOMING_KIND, "our_defender": defender_name, "enemy_move_type": atk, "receipt": rec})
    return rows, receipts, failures


# Backward-compatible v29.43 function name.
def build_defensive_matrix(team_payload: Any) -> tuple[dict, list, list]:
    return build_incoming_defense_matrix(team_payload)


def build_outgoing_attack_matrix(team_payload: Any, targets: Any = None) -> tuple[dict, list, list, list]:
    team = _team_list(team_payload)
    target_slots = _target_list(targets, fallback_team=team)
    rows: dict[str, dict[str, dict]] = {}
    receipts: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []
    for idx, slot in enumerate(team, start=1):
        attacker_name = _display_slot(slot, idx)
        rows.setdefault(attacker_name, {})
        for move in slot.get("moves", []) or []:
            move_type, move_receipt = _move_type(str(move))
            move_key = move_receipt.get("move", str(move))
            rows[attacker_name].setdefault(move_key, {"move_receipt": move_receipt, "enemy_targets": {}})
            if not move_type:
                failures.append({"matrix_kind": OUTGOING_KIND, "our_attacker": attacker_name, "move": move, "receipt": move_receipt})
                continue
            if not target_slots:
                warnings.append({"matrix_kind": OUTGOING_KIND, "our_attacker": attacker_name, "move": move_key, "reason": "no enemy targets supplied; outgoing target matrix is empty"})
                continue
            for tidx, target in enumerate(target_slots, start=1):
                target_name = _display_slot(target, tidx) if isinstance(target, dict) else str(target)
                defender_query = _defender_query(target)
                rec = legacy.verify_type_effectiveness(move_type, defender_query)
                entry = _dealt_cell(rec)
                rows[attacker_name][move_key]["enemy_targets"][target_name] = entry
                receipts.append({
                    "matrix_kind": OUTGOING_KIND,
                    "direction": OUTGOING_DIRECTION,
                    "our_attacker": attacker_name,
                    "our_move": move_key,
                    "our_move_type": move_type,
                    "enemy_defender": target_name,
                    "cell": entry,
                })
                if rec.get("status") != "pass":
                    failures.append({"matrix_kind": OUTGOING_KIND, "our_attacker": attacker_name, "move": move_key, "enemy_defender": target_name, "receipt": rec})
    return rows, receipts, failures, warnings


# Backward-compatible v29.43 function name.
def build_offensive_matrix(team_payload: Any, targets: Any = None) -> tuple[dict, list, list, list]:
    return build_outgoing_attack_matrix(team_payload, targets=targets)


def verify_incoming_defense_matrix(team_payload: Any) -> dict:
    team = _team_list(team_payload)
    if not team:
        return {"mode": "incoming_defense_matrix", "matrix_kind": INCOMING_KIND, "status": "fail", "reason": "team payload must be a list or object with team/sets list"}
    team_receipt = legacy.verify_team(team_payload)
    rows, receipts, failures = build_incoming_defense_matrix(team_payload)
    return {
        "mode": "incoming_defense_matrix",
        "engine_version": ENGINE_VERSION,
        "matrix_kind": INCOMING_KIND,
        "direction": INCOMING_DIRECTION,
        "public_table_header_required": "ENEMY MOVE TYPE → OUR DEFENDER",
        "cell_semantics": "x taken",
        "status": "pass" if not failures else "fail",
        "team_status": "pass" if team_receipt.get("team_ok") else "fail",
        "team_receipt": team_receipt,
        "rows": rows,
        "defensive_matrix": rows,  # compatibility alias
        "receipts": receipts,
        "receipt_counts": {"incoming_defense_typechart_receipts": len(receipts)},
        "failures": failures,
        "rule": "Use this matrix before public switch/pivot/defensive resistance/weakness claims. Direction is ENEMY MOVE TYPE → OUR DEFENDER; cells must be written as x taken.",
    }


def verify_outgoing_attack_matrix(team_payload: Any, targets: Any = None) -> dict:
    team = _team_list(team_payload)
    if not team:
        return {"mode": "outgoing_attack_matrix", "matrix_kind": OUTGOING_KIND, "status": "fail", "reason": "team payload must be a list or object with team/sets list"}
    team_receipt = legacy.verify_team(team_payload)
    rows, receipts, failures, warnings = build_outgoing_attack_matrix(team_payload, targets=targets)
    return {
        "mode": "outgoing_attack_matrix",
        "engine_version": ENGINE_VERSION,
        "matrix_kind": OUTGOING_KIND,
        "direction": OUTGOING_DIRECTION,
        "public_table_header_required": "OUR MOVE → ENEMY DEFENDER",
        "cell_semantics": "x dealt",
        "status": "pass" if not failures else "fail",
        "team_status": "pass" if team_receipt.get("team_ok") else "fail",
        "team_receipt": team_receipt,
        "rows": rows,
        "offensive_matrix": rows,  # compatibility alias
        "receipts": receipts,
        "receipt_counts": {"outgoing_attack_typechart_receipts": len(receipts)},
        "failures": failures,
        "warnings": warnings,
        "rule": "Use this matrix before public offensive coverage claims. Direction is OUR MOVE → ENEMY DEFENDER; cells must be written as x dealt.",
    }


def verify_type_matrix(team_payload: Any, targets: Any = None, mode: str = "both") -> dict:
    """Backward-compatible v29.43 command plus v29.44 direction metadata."""
    mode_norm = str(mode or "both").strip().lower().replace("_", "-")
    if mode_norm in {"incoming", "incoming-defense", "defensive", "defense"}:
        return verify_incoming_defense_matrix(team_payload)
    if mode_norm in {"outgoing", "outgoing-attack", "offensive", "attack"}:
        return verify_outgoing_attack_matrix(team_payload, targets=targets)

    team = _team_list(team_payload)
    if not team:
        return {"mode": "type_matrix", "status": "fail", "reason": "team payload must be a list or object with team/sets list"}
    team_receipt = legacy.verify_team(team_payload)
    incoming_rows, in_receipts, in_failures = build_incoming_defense_matrix(team_payload)
    outgoing_rows, out_receipts, out_failures, warnings = build_outgoing_attack_matrix(team_payload, targets=targets)
    failures = in_failures + out_failures
    return {
        "mode": "type_matrix",
        "engine_version": ENGINE_VERSION,
        "status": "pass" if not failures else "fail",
        "team_status": "pass" if team_receipt.get("team_ok") else "fail",
        "team_receipt": team_receipt,
        "team_gate": {
            "team_ok": team_receipt.get("team_ok"),
            "warnings": team_receipt.get("warnings", []),
        },
        "matrices": {
            INCOMING_KIND: {
                "matrix_kind": INCOMING_KIND,
                "direction": INCOMING_DIRECTION,
                "cell_semantics": "x taken",
                "rows": incoming_rows,
            },
            OUTGOING_KIND: {
                "matrix_kind": OUTGOING_KIND,
                "direction": OUTGOING_DIRECTION,
                "cell_semantics": "x dealt",
                "rows": outgoing_rows,
            },
        },
        "defensive_matrix": incoming_rows,  # compatibility alias
        "offensive_matrix": outgoing_rows,  # compatibility alias
        "receipts": in_receipts + out_receipts,
        "receipt_counts": {
            "incoming_defense_typechart_receipts": len(in_receipts),
            "outgoing_attack_typechart_receipts": len(out_receipts),
        },
        "failures": failures,
        "warnings": warnings,
        "rule": "Direction is mandatory. INCOMING_DEFENSE_MATRIX = ENEMY MOVE TYPE → OUR DEFENDER, x taken. OUTGOING_ATTACK_MATRIX = OUR MOVE → ENEMY DEFENDER, x dealt. No public type/switch/coverage claim without direct typechart, direction-explicit matrix, switch-safety, or damage receipt provenance.",
    }
