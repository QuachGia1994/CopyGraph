from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone

from .calibration import CalibrationModel
from .explain import explain_pair
from .matching import PairAnalysis
from .models import PositionLifecycle


def _iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timeline(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
) -> list[dict[str, object]]:
    by_a = {position.position_id: position for position in account_a}
    by_b = {position.position_id: position for position in account_b}
    rows: list[dict[str, object]] = []
    for match in analysis.matches:
        left = by_a.get(match.a_position_id)
        right = by_b.get(match.b_position_id)
        if left is None or right is None:
            raise ValueError("matched lifecycle not found")
        close_delay_s = None
        close_delay_residual_s = None
        if left.close_time is not None and right.close_time is not None:
            close_delay_s = (right.close_time - left.close_time).total_seconds()
            close_delay_residual_s = close_delay_s - match.delay_s
        lot_ratio = right.volume / left.volume if left.volume > 0 else None
        rows.append({
            "a_position_id": match.a_position_id,
            "b_position_id": match.b_position_id,
            "symbol": left.symbol,
            "a_side": left.side,
            "b_side": right.side,
            "a_open_time": _iso_z(left.open_time),
            "b_open_time": _iso_z(right.open_time),
            "a_close_time": _iso_z(left.close_time),
            "b_close_time": _iso_z(right.close_time),
            "delay_s": match.delay_s,
            "close_delay_s": close_delay_s,
            "close_delay_residual_s": close_delay_residual_s,
            "lot_ratio": lot_ratio,
            "score": match.score,
            "components": {
                "time": match.time_similarity,
                "lifecycle": match.lifecycle_similarity,
                "risk": match.risk_similarity,
                "volume": match.volume_similarity,
            },
        })
    rows.sort(key=lambda row: (
        str(row["a_open_time"]),
        str(row["b_open_time"]),
        str(row["a_position_id"]),
        str(row["b_position_id"]),
    ))
    return rows


def _delay_summary(timeline: Sequence[dict[str, object]]) -> dict[str, object]:
    delays = [float(row["delay_s"]) for row in timeline]
    if not delays:
        return {"min_s": None, "max_s": None, "median_s": None, "buckets": []}
    counts = Counter(math.floor(delay / 60.0) * 60.0 for delay in delays)
    buckets = [
        {"lower_s": lower, "upper_s": lower + 60.0, "count": counts[lower]}
        for lower in sorted(counts)
    ]
    return {
        "min_s": min(delays),
        "max_s": max(delays),
        "median_s": float(statistics.median(delays)),
        "buckets": buckets,
    }


def _close_delay_consistency(timeline: Sequence[dict[str, object]]) -> dict[str, object]:
    residuals = [
        float(row["close_delay_residual_s"])
        for row in timeline
        if row["close_delay_residual_s"] is not None
    ]
    covered = len(residuals)
    total = len(timeline)
    absolute = [abs(value) for value in residuals]
    return {
        "covered_matches": covered,
        "coverage": covered / total if total else 0.0,
        "median_abs_residual_s": float(statistics.median(absolute)) if absolute else None,
        "max_abs_residual_s": max(absolute) if absolute else None,
    }


def _lot_ratio_summary(timeline: Sequence[dict[str, object]]) -> dict[str, object]:
    series = [
        {
            "a_open_time": row["a_open_time"],
            "a_position_id": row["a_position_id"],
            "b_position_id": row["b_position_id"],
            "ratio": float(row["lot_ratio"]),
        }
        for row in timeline
        if row["lot_ratio"] is not None and float(row["lot_ratio"]) > 0
    ]
    series.sort(key=lambda row: (str(row["a_open_time"]), str(row["a_position_id"]), str(row["b_position_id"])))
    ratios = [float(row["ratio"]) for row in series]
    return {
        "median": float(statistics.median(ratios)) if ratios else None,
        "drift_factor": max(ratios) / min(ratios) if ratios and min(ratios) > 0 else None,
        "series": series,
    }


def _risk_evidence(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
) -> dict[str, object]:
    by_a = {position.position_id: position for position in account_a}
    by_b = {position.position_id: position for position in account_b}
    covered = 0
    for match in analysis.matches:
        left = by_a.get(match.a_position_id)
        right = by_b.get(match.b_position_id)
        if left is not None and right is not None and left.sl is not None and right.sl is not None:
            covered += 1
    total = len(analysis.matches)
    return {"covered_matches": covered, "total_matches": total, "coverage": covered / total if total else 0.0}


def _symbol_breakdown(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    timeline: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    matched_a = {match.a_position_id for match in analysis.matches}
    matched_b = {match.b_position_id for match in analysis.matches}
    by_symbol: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in timeline:
        by_symbol[str(row["symbol"])].append(row)
    symbols = {position.symbol for position in account_a} | {position.symbol for position in account_b}
    output: list[dict[str, object]] = []
    for symbol in symbols:
        rows = by_symbol.get(symbol, [])
        scores = [float(row["score"]) for row in rows]
        delays = [float(row["delay_s"]) for row in rows]
        output.append({
            "symbol": symbol,
            "matched_count": len(rows),
            "unmatched_a": sum(position.symbol == symbol and position.position_id not in matched_a for position in account_a),
            "unmatched_b": sum(position.symbol == symbol and position.position_id not in matched_b for position in account_b),
            "mean_match_score": statistics.fmean(scores) if scores else None,
            "median_delay_s": float(statistics.median(delays)) if delays else None,
        })
    output.sort(key=lambda item: (-int(item["matched_count"]), str(item["symbol"])))
    return output


def _orientation_candidate(left: PositionLifecycle, right: PositionLifecycle, orientation: str) -> bool:
    if left.symbol != right.symbol:
        return False
    if orientation == "normal":
        return left.side == right.side
    return left.side != right.side


def _unmatched_near_window(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
) -> list[dict[str, object]]:
    matched_a = {match.a_position_id for match in analysis.matches}
    matched_b = {match.b_position_id for match in analysis.matches}
    rows: list[dict[str, object]] = []

    for left in account_a:
        if left.position_id in matched_a:
            continue
        candidates: list[tuple[float, datetime, str, PositionLifecycle, float]] = []
        for right in account_b:
            if not _orientation_candidate(left, right, analysis.orientation):
                continue
            delay = (right.open_time - left.open_time).total_seconds()
            if abs(delay) <= analysis.matching_window_s:
                candidates.append((abs(delay), right.open_time, right.position_id, right, delay))
        if candidates:
            _, _, _, right, delay = min(candidates, key=lambda item: (item[0], item[1], item[2]))
            rows.append({
                "unmatched_account": "a",
                "unmatched_position_id": left.position_id,
                "nearest_other_position_id": right.position_id,
                "delay_s": delay,
                "nearest_other_was_matched": right.position_id in matched_b,
            })

    for right in account_b:
        if right.position_id in matched_b:
            continue
        candidates = []
        for left in account_a:
            if not _orientation_candidate(left, right, analysis.orientation):
                continue
            delay = (right.open_time - left.open_time).total_seconds()
            if abs(delay) <= analysis.matching_window_s:
                candidates.append((abs(delay), left.open_time, left.position_id, left, delay))
        if candidates:
            _, _, _, left, delay = min(candidates, key=lambda item: (item[0], item[1], item[2]))
            rows.append({
                "unmatched_account": "b",
                "unmatched_position_id": right.position_id,
                "nearest_other_position_id": left.position_id,
                "delay_s": delay,
                "nearest_other_was_matched": left.position_id in matched_a,
            })

    rows.sort(key=lambda row: (
        abs(float(row["delay_s"])),
        str(row["unmatched_account"]),
        str(row["unmatched_position_id"]),
        str(row["nearest_other_position_id"]),
    ))
    return rows


def build_forensic_report(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]:
    explanation = explain_pair(analysis, account_a, account_b, calibration)
    timeline = _timeline(analysis, account_a, account_b)
    unmatched_counts = dict(explanation["unmatched_counts"])
    near_window = _unmatched_near_window(analysis, account_a, account_b)
    supporting = sorted(
        timeline,
        key=lambda row: (-float(row["score"]), str(row["a_position_id"]), str(row["b_position_id"])),
    )[:5]
    contradictory = sorted(
        timeline,
        key=lambda row: (float(row["score"]), str(row["a_position_id"]), str(row["b_position_id"])),
    )[:5]
    contradictory_evidence: list[dict[str, object]] = []
    if not timeline:
        contradictory_evidence.append({"kind": "no_matched_trades", "count": 1})
    if unmatched_counts["a"] or unmatched_counts["b"]:
        contradictory_evidence.append({
            "kind": "unmatched_positions",
            "a": unmatched_counts["a"],
            "b": unmatched_counts["b"],
        })
    for row in near_window:
        contradictory_evidence.append({
            "kind": "near_window_collision",
            "unmatched_account": row["unmatched_account"],
            "unmatched_position_id": row["unmatched_position_id"],
            "nearest_other_position_id": row["nearest_other_position_id"],
            "delay_s": row["delay_s"],
            "nearest_other_was_matched": row["nearest_other_was_matched"],
        })

    return {
        "schema_version": "1.0",
        "accounts": [analysis.account_a, analysis.account_b],
        "orientation": analysis.orientation,
        "raw_score": analysis.score,
        "raw_confidence": analysis.confidence,
        "calibrated_confidence": explanation["calibrated_confidence"],
        "lead_account": analysis.lead_account,
        "median_delay_s": analysis.median_delay_s,
        "matching_window_s": analysis.matching_window_s,
        "warnings": explanation["warnings"],
        "explanation": explanation,
        "timeline": timeline,
        "delay_summary": _delay_summary(timeline),
        "close_delay_consistency": _close_delay_consistency(timeline),
        "lot_ratio": _lot_ratio_summary(timeline),
        "risk_evidence": _risk_evidence(analysis, account_a, account_b),
        "symbol_breakdown": _symbol_breakdown(analysis, account_a, account_b, timeline),
        "unmatched_counts": unmatched_counts,
        "unmatched_near_window": near_window,
        "supporting_matches": supporting,
        "contradictory_matches": contradictory,
        "contradictory_evidence": contradictory_evidence,
    }
