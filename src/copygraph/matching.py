from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field

from .dna import trade_dna
from .models import PositionLifecycle


@dataclass(frozen=True, slots=True)
class MatchingConfig:
    time_tolerance_s: float = 90.0
    close_tolerance_s: float = 180.0
    min_matches: int = 3
    hard_time_factor: float = 4.0


@dataclass(frozen=True, slots=True)
class MatchedTrade:
    a_position_id: str
    b_position_id: str
    delay_s: float
    time_similarity: float
    lifecycle_similarity: float
    risk_similarity: float
    volume_similarity: float
    rarity_weight: float
    score: float


@dataclass(slots=True)
class PairAnalysis:
    account_a: str | None = None
    account_b: str | None = None
    orientation: str = "normal"
    score: float = 0.0
    confidence: float = 0.0
    matches: list[MatchedTrade] = field(default_factory=list)
    volume_similarity: float = 0.0
    lead_account: str | None = None
    median_delay_s: float = 0.0
    total_a: int = 0
    total_b: int = 0
    overlap_factor: float = 0.0
    sample_factor: float = 0.0
    matching_window_s: float = 0.0


def rarity_weight(frequency: int) -> float:
    frequency = max(1, int(frequency))
    return 1.0 / (1.0 + 0.35 * math.log1p(frequency - 1))


def _ratio_similarity(left: float, right: float) -> float:
    left = abs(left)
    right = abs(right)
    if left == 0 and right == 0:
        return 1.0
    if left == 0 or right == 0:
        return 0.0
    return min(left, right) / max(left, right)


def _lifecycle_similarity(a: PositionLifecycle, b: PositionLifecycle, delay_s: float, close_tolerance_s: float) -> float:
    if a.duration_s is None and b.duration_s is None:
        return 1.0
    if a.duration_s is None or b.duration_s is None:
        return 0.5
    duration_similarity = _ratio_similarity(a.duration_s, b.duration_s)
    close_delay_s = (b.close_time - a.close_time).total_seconds()
    delay_consistency = max(0.0, 1.0 - abs(close_delay_s - delay_s) / max(1.0, close_tolerance_s))
    return (duration_similarity + delay_consistency) / 2.0


def _risk_similarity(a: PositionLifecycle, b: PositionLifecycle) -> float:
    if a.sl is None or b.sl is None:
        return 0.0
    return _ratio_similarity(trade_dna(a).risk_distance, trade_dna(b).risk_distance)


def _orientation_match(a: PositionLifecycle, b: PositionLifecycle, orientation: str) -> bool:
    dna_a = trade_dna(a)
    dna_b = trade_dna(b)
    if dna_a.symbol != dna_b.symbol:
        return False
    if orientation == "normal":
        return dna_a.side == dna_b.side
    return dna_a.side != dna_b.side


def _analyze_orientation(account_a: list[PositionLifecycle], account_b: list[PositionLifecycle], orientation: str, config: MatchingConfig) -> PairAnalysis:
    account_a_name = account_a[0].account_id if account_a else None
    account_b_name = account_b[0].account_id if account_b else None
    hard_window = max(config.time_tolerance_s, config.time_tolerance_s * config.hard_time_factor)
    symbol_frequency = Counter(trade_dna(position).symbol for position in account_a + account_b)
    candidates: list[tuple[float, float, PositionLifecycle, PositionLifecycle, float, float, float]] = []
    for a in account_a:
        for b in account_b:
            if not _orientation_match(a, b, orientation):
                continue
            delay_s = (b.open_time - a.open_time).total_seconds()
            if abs(delay_s) > hard_window:
                continue
            time_similarity = max(0.0, 1.0 - abs(delay_s) / hard_window)
            lifecycle_similarity = _lifecycle_similarity(a, b, delay_s, config.close_tolerance_s)
            risk_similarity = _risk_similarity(a, b)
            candidate_score = 0.47 * time_similarity + 0.29 * lifecycle_similarity + 0.24 * risk_similarity
            candidates.append((candidate_score, abs(delay_s), a, b, delay_s, time_similarity, lifecycle_similarity))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2].open_time, item[3].open_time))
    used_a: set[str] = set()
    used_b: set[str] = set()
    selected: list[tuple[PositionLifecycle, PositionLifecycle, float, float, float]] = []
    for _, _, a, b, delay_s, time_similarity, lifecycle_similarity in candidates:
        if a.position_id in used_a or b.position_id in used_b:
            continue
        used_a.add(a.position_id)
        used_b.add(b.position_id)
        selected.append((a, b, delay_s, time_similarity, lifecycle_similarity))

    ratios = [b.volume / a.volume for a, b, *_ in selected if a.volume > 0 and b.volume > 0]
    median_ratio = statistics.median(ratios) if ratios else 1.0
    matches: list[MatchedTrade] = []
    for a, b, delay_s, time_similarity, lifecycle_similarity in selected:
        ratio = b.volume / a.volume if a.volume > 0 and b.volume > 0 else 0.0
        volume_similarity = _ratio_similarity(ratio, median_ratio)
        risk_similarity = _risk_similarity(a, b)
        weight = rarity_weight(symbol_frequency[trade_dna(a).symbol])
        score = 0.40 * time_similarity + 0.25 * lifecycle_similarity + 0.20 * risk_similarity + 0.15 * volume_similarity
        matches.append(MatchedTrade(
            a_position_id=a.position_id,
            b_position_id=b.position_id,
            delay_s=delay_s,
            time_similarity=time_similarity,
            lifecycle_similarity=lifecycle_similarity,
            risk_similarity=risk_similarity,
            volume_similarity=volume_similarity,
            rarity_weight=weight,
            score=score,
        ))

    if matches:
        total_weight = sum(match.rarity_weight for match in matches)
        score = sum(match.score * match.rarity_weight for match in matches) / total_weight
        volume_similarity = statistics.fmean(match.volume_similarity for match in matches)
        median_delay_s = float(statistics.median(match.delay_s for match in matches))
        overlap = len(matches) / max(1, len(account_a), len(account_b))
        sample_factor = min(1.0, len(matches) / max(1, config.min_matches))
        confidence = score * overlap * sample_factor
        if median_delay_s > 2:
            lead_account = account_a_name
        elif median_delay_s < -2:
            lead_account = account_b_name
        else:
            lead_account = None
    else:
        score = 0.0
        volume_similarity = 0.0
        median_delay_s = 0.0
        confidence = 0.0
        lead_account = None
        overlap = 0.0
        sample_factor = 0.0

    return PairAnalysis(
        account_a=account_a_name,
        account_b=account_b_name,
        orientation=orientation,
        score=score,
        confidence=confidence,
        matches=matches,
        volume_similarity=volume_similarity,
        lead_account=lead_account,
        median_delay_s=median_delay_s,
        total_a=len(account_a),
        total_b=len(account_b),
        overlap_factor=overlap,
        sample_factor=sample_factor,
        matching_window_s=hard_window,
    )


def analyze_pair(account_a, account_b, config: MatchingConfig | None = None) -> PairAnalysis:
    resolved_config = config or MatchingConfig()
    left = list(account_a)
    right = list(account_b)
    normal = _analyze_orientation(left, right, "normal", resolved_config)
    reverse = _analyze_orientation(left, right, "reverse", resolved_config)
    if reverse.confidence > normal.confidence:
        return reverse
    return normal
