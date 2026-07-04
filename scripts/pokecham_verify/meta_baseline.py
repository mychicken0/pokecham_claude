"""v29.46 meta/player baseline hard gates.

This module deliberately does not add Pokémon/move/item/ability data. It only
checks that actionable recommendations are backed by approved live/player
baseline receipts, a searched local fallback, or an explicit benchmark override.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

from . import legacy

META_BASELINE_ENGINE_VERSION = "v29.46-meta-baseline-hardgate-docorder"

APPROVED_SOURCE_FAMILIES = {
    "pikalytics",
    "pokemonzone",
    "pokemonzonechampions",
    "pokebase",
    "pokebasechampions",
    "championslab",
    "opggpokemonchampions",
    "opgg",
    "limitless",
    "playlimitless",
    "rk9",
    "officialpokemon",
    "officialpokemonchampions",
    "tournamentteamlist",
    "tournamentlist",
}

BLOCKED_SOURCE_PATTERNS = {
    "bluestacks",
    "smogon",
    "showdownusage",
    "showdown",
    "genericvgc",
    "seo",
    "tierlistgeneric",
}

BASELINE_DIRECT_LABELS = {"META_DIRECT", "META_SPREAD_DIRECT", "TOURNAMENT_LIST_DIRECT", "META_PATTERN", "USER_REQUESTED"}
LOCAL_ALLOWED_LABELS = {"LOCAL_FALLBACK_AFTER_SEARCH", "LOCAL_BENCHMARK_OVERRIDE"}
DISALLOWED_FINAL_LABELS = {"LOCAL_FALLBACK", "LOCAL_TEAM_FIT", "ITEM_CLAUSE_REPAIR", "ITEMTHREATFIT", "DAMAGE_BENCHMARK", "SPEED_MODE_FIT", "EXPERIMENTAL", "LOCAL_GUESS"}
FIELDS = ("item", "moves", "spread", "nature", "ability")


def _nid(v: Any) -> str:
    return legacy.normalize_id(str(v or ""))


def _canonical_field(field: Any) -> str:
    f = _nid(field)
    if f in {"move", "moves", "moveslot"}:
        return "moves"
    if f in {"spread", "investment", "investments"}:
        return "spread"
    if f in {"item", "helditem"}:
        return "item"
    if f in {"nature"}:
        return "nature"
    if f in {"ability"}:
        return "ability"
    return str(field or "").strip().lower()


def _label(entry: dict) -> str:
    return str(entry.get("baseline_status") or entry.get("source_label") or entry.get("provenance") or entry.get("label") or "").strip().upper()


def _source_family(entry: dict) -> str:
    raw = entry.get("source_family") or entry.get("source_name") or entry.get("source_url_or_name") or entry.get("source") or ""
    return _nid(raw)


def _is_approved_source(entry: dict) -> bool:
    fam = _source_family(entry)
    if not fam:
        return False
    if any(bad in fam for bad in BLOCKED_SOURCE_PATTERNS):
        return False
    return any(ok in fam for ok in APPROVED_SOURCE_FAMILIES)


def _is_blocked_source(entry: dict) -> bool:
    fam = _source_family(entry)
    return any(bad in fam for bad in BLOCKED_SOURCE_PATTERNS)


def _entries(payload: dict, key: str) -> list[dict]:
    val = payload.get(key) if isinstance(payload, dict) else []
    return val if isinstance(val, list) else []


def _search_attempts_for(payload: dict, pokemon: str | None = None, field: str | None = None) -> list[dict]:
    attempts = _entries(payload, "search_attempts")
    out = []
    p = _nid(pokemon) if pokemon else ""
    f = _canonical_field(field) if field else ""
    for a in attempts:
        if not isinstance(a, dict):
            continue
        ap = _nid(a.get("pokemon") or a.get("species") or "")
        af = _canonical_field(a.get("field") or a.get("slot") or "")
        if p and ap and ap != p:
            continue
        if f and af and af != f:
            continue
        out.append(a)
    return out


def _has_search_attempt(payload: dict, pokemon: str | None = None, field: str | None = None) -> bool:
    return bool(_search_attempts_for(payload, pokemon, field))


def _has_no_result_attempt(payload: dict, pokemon: str | None = None, field: str | None = None) -> bool:
    for a in _search_attempts_for(payload, pokemon, field):
        status = _nid(a.get("result_status") or a.get("status"))
        if status in {"noresults", "notfound", "unavailable", "missing", "none"}:
            return True
    return False


def _value_matches(final_value: Any, baseline_value: Any, field: str) -> bool:
    if field == "spread":
        if not isinstance(final_value, dict) or not isinstance(baseline_value, dict):
            return False
        keys = ["hp", "atk", "def", "spa", "spd", "spe"]
        return all(int(final_value.get(k, -999) or 0) == int(baseline_value.get(k, -999) or 0) for k in keys)
    if field == "moves":
        final_set = {_nid(v) for v in (final_value or []) if str(v or "").strip()}
        base_set = {_nid(v) for v in (baseline_value or []) if str(v or "").strip()} if isinstance(baseline_value, list) else {_nid(baseline_value)}
        return bool(final_set) and final_set.issubset(base_set)
    return _nid(final_value) == _nid(baseline_value)


def _slot_species(slot: dict) -> str:
    return str(slot.get("pokemon") or slot.get("species") or slot.get("name") or slot.get("display_name") or "").strip()


def _slot_values(slot: dict) -> dict[str, Any]:
    return {
        "item": slot.get("item") or slot.get("held_item"),
        "moves": slot.get("moves") or slot.get("move_names") or [],
        "spread": slot.get("spread") or slot.get("investment") or slot.get("investments") or {},
        "nature": slot.get("nature"),
        "ability": slot.get("ability"),
    }


def _team_slots(team_payload: Any) -> list[dict]:
    if isinstance(team_payload, list):
        return [x for x in team_payload if isinstance(x, dict)]
    if isinstance(team_payload, dict):
        for key in ("team", "sets", "slots", "pokemon"):
            val = team_payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
    return []


def _slot_baselines(meta_payload: dict, pokemon: str, field: str) -> list[dict]:
    p = _nid(pokemon)
    f = _canonical_field(field)
    candidates = []
    for e in _entries(meta_payload, "slot_baselines") + _entries(meta_payload, "baselines"):
        if not isinstance(e, dict):
            continue
        ep = _nid(e.get("pokemon") or e.get("species") or e.get("form") or "")
        ef = _canonical_field(e.get("field") or e.get("slot") or e.get("kind") or "")
        if ep == p and ef == f:
            candidates.append(e)
    return candidates


def _slot_overrides(meta_payload: dict, pokemon: str, field: str) -> list[dict]:
    p = _nid(pokemon)
    f = _canonical_field(field)
    candidates = []
    for e in _entries(meta_payload, "overrides") + _entries(meta_payload, "local_overrides"):
        if not isinstance(e, dict):
            continue
        ep = _nid(e.get("pokemon") or e.get("species") or "")
        ef = _canonical_field(e.get("field") or e.get("slot") or "")
        if ep == p and ef == f:
            candidates.append(e)
    return candidates


def _baseline_value(entry: dict) -> Any:
    if "value" in entry:
        return entry.get("value")
    for key in ("item", "moves", "move", "spread", "nature", "ability", "final_value", "baseline_value"):
        if key in entry:
            return entry.get(key)
    return None


def meta_baseline_lint(meta_payload: dict) -> dict:
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    meta_payload = meta_payload or {}

    attempts = _entries(meta_payload, "search_attempts")
    baselines = _entries(meta_payload, "slot_baselines") + _entries(meta_payload, "baselines")
    overrides = _entries(meta_payload, "overrides") + _entries(meta_payload, "local_overrides")

    for idx, a in enumerate(attempts):
        if not isinstance(a, dict):
            failures.append({"code": "FAIL_META_SEARCH_ATTEMPT_INVALID", "index": idx})
            continue
        if _is_blocked_source(a):
            failures.append({"code": "FAIL_META_BASELINE_SOURCE_NOT_APPROVED", "index": idx, "source": a.get("source_family") or a.get("source_name"), "detail": "Blocked source family cannot be used as a searched baseline source."})
        elif not _is_approved_source(a):
            failures.append({"code": "FAIL_META_BASELINE_SOURCE_NOT_APPROVED", "index": idx, "source": a.get("source_family") or a.get("source_name"), "detail": "Search attempt must use an approved Champions/player source family."})
        if not (a.get("query") or a.get("source_url_or_name") or a.get("source_name")):
            failures.append({"code": "FAIL_META_SEARCH_ATTEMPT_MISSING_QUERY", "index": idx})
        status = _nid(a.get("result_status") or a.get("status"))
        if status not in {"found", "noresults", "notfound", "unavailable", "missing", "blocked", "none"}:
            warnings.append({"code": "WARN_META_SEARCH_ATTEMPT_STATUS_UNUSUAL", "index": idx, "result_status": a.get("result_status") or a.get("status")})

    for idx, b in enumerate(baselines):
        if not isinstance(b, dict):
            failures.append({"code": "FAIL_META_BASELINE_ENTRY_INVALID", "index": idx})
            continue
        label = _label(b)
        pokemon = b.get("pokemon") or b.get("species")
        field = _canonical_field(b.get("field") or b.get("slot") or b.get("kind"))
        if not pokemon or field not in FIELDS:
            failures.append({"code": "FAIL_META_BASELINE_SLOT_MISSING", "index": idx, "detail": "Baseline entries require pokemon and field=item|moves|spread|nature|ability."})
        if label == "LOCAL_FALLBACK":
            failures.append({"code": "FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT", "index": idx, "detail": "Use LOCAL_FALLBACK_AFTER_SEARCH and attach a matching search_attempt receipt."})
        if label in DISALLOWED_FINAL_LABELS:
            failures.append({"code": "FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE" if label == "ITEMTHREATFIT" else "FAIL_LOCAL_TEAM_FIT_USED_AS_FINAL_RECOMMENDATION", "index": idx, "label": label, "detail": "Local fit/item clause/experimental labels cannot be used as final meta baseline evidence."})
        if label in BASELINE_DIRECT_LABELS:
            if not _is_approved_source(b) and label != "USER_REQUESTED":
                failures.append({"code": "FAIL_META_BASELINE_SOURCE_NOT_APPROVED", "index": idx, "label": label, "source": b.get("source_family") or b.get("source_name") or b.get("source_url_or_name")})
        if label == "LOCAL_FALLBACK_AFTER_SEARCH":
            if not _has_no_result_attempt(meta_payload, pokemon, field):
                failures.append({"code": "FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT", "index": idx, "pokemon": pokemon, "field": field, "detail": "LOCAL_FALLBACK_AFTER_SEARCH requires a matching no-results/unavailable search_attempt."})
        if _baseline_value(b) in (None, "", []):
            failures.append({"code": "FAIL_META_BASELINE_VALUE_MISSING", "index": idx, "pokemon": pokemon, "field": field})

    for idx, o in enumerate(overrides):
        if not isinstance(o, dict):
            failures.append({"code": "FAIL_LOCAL_BENCHMARK_OVERRIDE_INVALID", "index": idx})
            continue
        label = _label(o) or str(o.get("override_status") or "").strip().upper()
        if label != "LOCAL_BENCHMARK_OVERRIDE":
            warnings.append({"code": "WARN_OVERRIDE_LABEL_NOT_LOCAL_BENCHMARK_OVERRIDE", "index": idx, "label": label})
        if not (o.get("pokemon") or o.get("species")) or _canonical_field(o.get("field") or o.get("slot")) not in FIELDS:
            failures.append({"code": "FAIL_META_BASELINE_SLOT_MISSING", "index": idx, "detail": "Override entries require pokemon and field."})
        if "final_value" not in o or "baseline_value" not in o:
            failures.append({"code": "FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF", "index": idx, "detail": "Override requires final_value and baseline_value."})
        if not (o.get("diff") or o.get("benchmark_diff") or o.get("benchmark_receipts") or o.get("benchmark_receipt")):
            failures.append({"code": "FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF", "index": idx, "detail": "Override requires an explicit diff/benchmark receipt summary."})

    return {
        "mode": "meta_baseline_lint",
        "engine_version": META_BASELINE_ENGINE_VERSION,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "warnings": warnings,
        "search_attempt_count": len(attempts),
        "slot_baseline_count": len(baselines),
        "override_count": len(overrides),
        "rule": "Actionable recommendations require approved source baselines, LOCAL_FALLBACK_AFTER_SEARCH with matching search attempt, or LOCAL_BENCHMARK_OVERRIDE with explicit diff.",
    }


def _field_status(meta_payload: dict, pokemon: str, field: str, final_value: Any) -> dict:
    # Direct/source/user/fallback entries.
    for b in _slot_baselines(meta_payload, pokemon, field):
        label = _label(b)
        value = _baseline_value(b)
        if label in BASELINE_DIRECT_LABELS and _value_matches(final_value, value, field):
            return {"status": "pass", "evidence_label": label, "evidence": b, "rule": "final value matches approved/player baseline"}
        if label == "LOCAL_FALLBACK_AFTER_SEARCH" and _value_matches(final_value, value, field) and _has_no_result_attempt(meta_payload, pokemon, field):
            return {"status": "pass", "evidence_label": label, "evidence": b, "rule": "final value is a local fallback only after approved search found no slot baseline"}
        if label in DISALLOWED_FINAL_LABELS:
            code = "FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE" if label == "ITEMTHREATFIT" else "FAIL_LOCAL_TEAM_FIT_USED_AS_FINAL_RECOMMENDATION"
            return {"status": "fail", "code": code, "evidence_label": label, "evidence": b}
    # Benchmark overrides.
    for o in _slot_overrides(meta_payload, pokemon, field):
        label = _label(o) or str(o.get("override_status") or "").strip().upper()
        if label == "LOCAL_BENCHMARK_OVERRIDE" and _value_matches(final_value, o.get("final_value"), field):
            has_diff = bool(o.get("diff") or o.get("benchmark_diff") or o.get("benchmark_receipts") or o.get("benchmark_receipt"))
            has_base = "baseline_value" in o
            if has_diff and has_base:
                return {"status": "pass", "evidence_label": label, "evidence": o, "rule": "local override includes explicit diff from meta baseline"}
            return {"status": "fail", "code": "FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF", "evidence_label": label, "evidence": o}
    code_by_field = {
        "item": "FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE",
        "moves": "FAIL_ACTIONABLE_MOVE_RECOMMENDATION_WITHOUT_META_BASELINE",
        "spread": "FAIL_ACTIONABLE_SPREAD_RECOMMENDATION_WITHOUT_META_BASELINE",
        "nature": "FAIL_ACTIONABLE_NATURE_RECOMMENDATION_WITHOUT_META_BASELINE",
        "ability": "FAIL_ACTIONABLE_ABILITY_RECOMMENDATION_WITHOUT_META_BASELINE",
    }
    return {"status": "fail", "code": code_by_field.get(field, "FAIL_META_BASELINE_SLOT_MISSING"), "detail": "No matching meta/search fallback/benchmark override evidence for final slot value."}


def meta_baseline_gate(team_payload: Any, meta_payload: dict, fields: Iterable[str] | None = None) -> dict:
    team_slots = _team_slots(team_payload)
    fields = tuple(_canonical_field(f) for f in (fields or FIELDS))
    lint = meta_baseline_lint(meta_payload or {})
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    slot_results = []

    if lint.get("status") == "fail":
        failures.extend({"code": f.get("code"), "source": "meta_baseline_lint", **f} for f in lint.get("failures", []))

    if not team_slots:
        failures.append({"code": "FAIL_META_BASELINE_TEAM_MISSING", "detail": "team.json must contain team/sets/list slots."})

    for idx, slot in enumerate(team_slots, start=1):
        pokemon = _slot_species(slot)
        values = _slot_values(slot)
        slot_result = {"slot": idx, "pokemon": pokemon, "fields": {}}
        if not pokemon:
            failures.append({"code": "FAIL_META_BASELINE_SLOT_MISSING", "slot": idx, "detail": "Team slot missing pokemon/species."})
            slot_results.append(slot_result)
            continue
        for field in fields:
            final_value = values.get(field)
            # Skip empty optional field rather than inventing a claim.
            if final_value in (None, "", [], {}):
                continue
            fs = _field_status(meta_payload or {}, pokemon, field, final_value)
            fs.update({"final_value": final_value})
            slot_result["fields"][field] = fs
            if fs.get("status") != "pass":
                failures.append({"code": fs.get("code", "FAIL_META_BASELINE_SLOT_MISSING"), "pokemon": pokemon, "field": field, "final_value": final_value, "detail": fs.get("detail", "Final slot lacks eligible baseline evidence.")})
        slot_results.append(slot_result)

    return {
        "mode": "meta_baseline_gate",
        "engine_version": META_BASELINE_ENGINE_VERSION,
        "status": "pass" if not failures else "fail",
        "public_recommendation_allowed": not failures,
        "slots": slot_results,
        "lint": lint,
        "failures": failures,
        "warnings": warnings,
        "rule": "Final actionable item/move/spread/nature/ability recommendations require per-slot meta baseline, searched local fallback, user request, or benchmark override.",
    }
