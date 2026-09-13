from __future__ import annotations

import math
import statistics
from collections import Counter
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


def build_forensic_report(
    analysis: PairAnalysis,
    account_a: Sequence[PositionLifecycle],
    account_b: Sequence[PositionLifecycle],
    calibration: CalibrationModel | None = None,
) -> dict[str, object]:
    explanation = explain_pair(analysis, account_a, account_b, calibration)
    timeline = _timeline(analysis, account_a, account_b)
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
    }
