"""Switch safety matrix receipts.

SWITCH_SAFETY_MATRIX is explicitly directional:
ENEMY LIKELY MOVE -> OUR SWITCH-IN, cell = x taken.
"""
from __future__ import annotations

from typing import Any

from . import legacy
from .type_matrix import ENGINE_VERSION, _defender_query, _display_slot, _move_type, _taken_cell

SWITCH_KIND = "SWITCH_SAFETY_MATRIX"
SWITCH_DIRECTION = "ENEMY_LIKELY_MOVE_TO_OUR_SWITCH_IN"


def _as_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _slot_name(slot: Any, index: int) -> str:
    if isinstance(slot, dict):
        return _display_slot(slot, index)
    return str(slot)


def _candidate_switchins(board: dict) -> list[Any]:
    our = board.get("our_side") or board.get("player_side") or board.get("side") or {}
    candidates = []
    for key in ("switch_ins", "switchins", "bench", "available_switchins", "available_switch_ins", "candidates"):
        if isinstance(our, dict) and key in our:
            candidates.extend(_as_list(our.get(key)))
    if not candidates and isinstance(board.get("switch_ins"), list):
        candidates = board.get("switch_ins")
    return candidates


def _likely_moves(board: dict) -> list[dict]:
    enemy = board.get("enemy_side") or board.get("opponent_side") or board.get("opposing_side") or {}
    moves = []
    if isinstance(enemy, dict):
        moves.extend(_as_list(enemy.get("likely_moves")))
        moves.extend(_as_list(enemy.get("incoming_moves")))
    moves.extend(_as_list(board.get("likely_moves")))
    cleaned = []
    for idx, m in enumerate(moves, start=1):
        if isinstance(m, str):
            cleaned.append({"move": m})
        elif isinstance(m, dict):
            cleaned.append(m)
        elif m is not None:
            cleaned.append({"move": str(m), "label": f"incoming_{idx}"})
    return cleaned


def _move_label(move: dict, idx: int) -> str:
    user = move.get("user") or move.get("attacker") or move.get("source")
    name = move.get("move") or move.get("name") or move.get("label") or f"incoming_{idx}"
    rtype = move.get("resolved_type") or move.get("move_type") or move.get("type") or "?"
    if user:
        return f"{user} / {name} [{rtype}]"
    return f"{name} [{rtype}]"


def _resolve_likely_move_type(move: dict) -> tuple[str | None, dict]:
    for key in ("resolved_type", "move_type", "type", "attacking_type"):
        val = move.get(key)
        if val:
            return str(val), {"status": "pass", "source": key, "type": str(val), "rule": "Switch-safety uses resolved incoming move type supplied by board receipt."}
    move_name = move.get("move") or move.get("name")
    if move_name:
        mtype, rec = _move_type(str(move_name))
        if mtype:
            rec = dict(rec)
            rec["warning"] = "Move type came from 08 base type. Dynamic moves such as Weather Ball should supply resolved_type in board input."
            return mtype, rec
        return None, rec
    return None, {"status": "fail", "reason": "likely move must include resolved_type/type or move name"}


def _verdict(cells: dict[str, dict]) -> str:
    vals = []
    for cell in cells.values():
        try:
            vals.append(float(cell.get("multiplier", 1.0)))
        except Exception:
            pass
    if not vals:
        return "unknown_no_type_receipts"
    if any(v >= 4 for v in vals):
        return "very_bad_switch_in_4x_taken"
    if any(v >= 2 for v in vals):
        return "bad_into_at_least_one_likely_move"
    if all(v <= 0.5 for v in vals):
        return "strong_defensive_switch_in"
    if any(v == 0 for v in vals) and max(vals) <= 1:
        return "good_mixed_defensive_switch_in"
    if max(vals) <= 1:
        return "usable_no_super_effective_taken"
    return "mixed_risk"


def verify_switch_safety_matrix(board_payload: Any) -> dict:
    if not isinstance(board_payload, dict):
        return {"mode": "switch_safety_matrix", "matrix_kind": SWITCH_KIND, "status": "fail", "reason": "board payload must be a JSON object"}

    candidates = _candidate_switchins(board_payload)
    moves = _likely_moves(board_payload)
    if not candidates:
        return {"mode": "switch_safety_matrix", "matrix_kind": SWITCH_KIND, "status": "fail", "reason": "board payload must include our_side.bench/switch_ins/candidates"}
    if not moves:
        return {"mode": "switch_safety_matrix", "matrix_kind": SWITCH_KIND, "status": "fail", "reason": "board payload must include enemy_side.likely_moves/incoming_moves"}

    rows: dict[str, dict] = {}
    receipts: list[dict] = []
    failures: list[dict] = []
    warnings: list[dict] = []
    resolved_moves = []

    for midx, move in enumerate(moves, start=1):
        mtype, mrec = _resolve_likely_move_type(move)
        label = _move_label(move, midx)
        resolved_moves.append({"label": label, "move": move, "resolved_type": mtype, "resolution_receipt": mrec})
        if not mtype:
            failures.append({"matrix_kind": SWITCH_KIND, "incoming_move": move, "receipt": mrec})
        elif mrec.get("warning"):
            warnings.append({"matrix_kind": SWITCH_KIND, "incoming_move": label, "warning": mrec.get("warning")})

    for cidx, cand in enumerate(candidates, start=1):
        cname = _slot_name(cand, cidx)
        defender_query = _defender_query(cand)
        rows.setdefault(cname, {"incoming_moves": {}, "verdict": "unknown"})
        for rm in resolved_moves:
            if not rm.get("resolved_type"):
                continue
            rec = legacy.verify_type_effectiveness(str(rm["resolved_type"]), defender_query)
            cell = _taken_cell(rec)
            rows[cname]["incoming_moves"][rm["label"]] = cell
            receipts.append({
                "matrix_kind": SWITCH_KIND,
                "direction": SWITCH_DIRECTION,
                "enemy_likely_move": rm["label"],
                "enemy_move_type": rm["resolved_type"],
                "our_switch_in": cname,
                "cell": cell,
            })
            if rec.get("status") != "pass":
                failures.append({"matrix_kind": SWITCH_KIND, "our_switch_in": cname, "enemy_likely_move": rm["label"], "receipt": rec})
        rows[cname]["verdict"] = _verdict(rows[cname]["incoming_moves"])

    return {
        "mode": "switch_safety_matrix",
        "engine_version": ENGINE_VERSION,
        "matrix_kind": SWITCH_KIND,
        "direction": SWITCH_DIRECTION,
        "public_table_header_required": "ENEMY LIKELY MOVE → OUR SWITCH-IN",
        "cell_semantics": "x taken",
        "status": "pass" if not failures else "fail",
        "public_switch_recommendation_allowed": not failures,
        "rows": rows,
        "resolved_incoming_moves": resolved_moves,
        "receipts": receipts,
        "receipt_counts": {"switch_safety_typechart_receipts": len(receipts)},
        "failures": failures,
        "warnings": warnings,
        "rule": "No public swap/switch/pivot/safe-switch recommendation without this receipt or an incoming-defense matrix. Direction is ENEMY LIKELY MOVE → OUR SWITCH-IN; cells must be written as x taken.",
    }
