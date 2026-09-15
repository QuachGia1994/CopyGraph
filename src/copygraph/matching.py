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


def _max_weight_assignment(weights: list[list[float]]) -> list[int]:
    """Return, for each row, the column it is paired with in a maximum-weight 1-to-1 assignment (-1 if unmatched).

    Hungarian (Kuhn-Munkres) O(n^3) method on a square-padded cost matrix, so
    the result is a provable global optimum rather than a greedy heuristic.
    weights[i][j] is the gain of pairing row i with column j; padded cells and
    surplus rows carry zero gain and drop out as unmatched.
    """
    n_rows = len(weights)
    if n_rows == 0:
        return []
    n_cols = len(weights[0])
    size = max(n_rows, n_cols)
    inf = float("inf")
    cost = [[0.0] * (size + 1) for _ in range(size + 1)]
    for i in range(1, size + 1):
        for j in range(1, size + 1):
            if i <= n_rows and j <= n_cols:
                cost[i][j] = -weights[i - 1][j - 1]
    potential_row = [0.0] * (size + 1)
    potential_col = [0.0] * (size + 1)
    col_match = [0] * (size + 1)
    parent = [0] * (size + 1)
    for row in range(1, size + 1):
        col_match[0] = row
        current = 0
        min_slack = [inf] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[current] = True
            matched_row = col_match[current]
            delta = inf
            next_col = 0
            for col in range(1, size + 1):
                if used[col]:
                    continue
                slack = cost[matched_row][col] - potential_row[matched_row] - potential_col[col]
                if slack < min_slack[col]:
                    min_slack[col] = slack
                    parent[col] = current
                if min_slack[col] < delta:
                    delta = min_slack[col]
                    next_col = col
            for col in range(size + 1):
                if used[col]:
                    potential_row[col_match[col]] += delta
                    potential_col[col] -= delta
                else:
                    min_slack[col] -= delta
            current = next_col
            if col_match[current] == 0:
                break
        while current:
            previous = parent[current]
            col_match[current] = col_match[previous]
            current = previous
    result = [-1] * n_rows
    for col in range(1, size + 1):
        row = col_match[col]
        if 1 <= row <= n_rows and 1 <= col <= n_cols:
            result[row - 1] = col - 1
    return result


def _select_optimal_matches(
    candidates: list[tuple[float, float, PositionLifecycle, PositionLifecycle, float, float, float]],
) -> list[tuple[PositionLifecycle, PositionLifecycle, float, float, float]]:
    if not candidates:
        return []
    row_index: dict[str, int] = {}
    col_index: dict[str, int] = {}
    for _score, _abs_delay, a, b, *_rest in candidates:
        row_index.setdefault(a.position_id, len(row_index))
        col_index.setdefault(b.position_id, len(col_index))
    cardinality_bonus = float(len(candidates) + 1)
    weights = [[0.0] * len(col_index) for _ in range(len(row_index))]
    edges: dict[tuple[int, int], tuple[float, float, PositionLifecycle, PositionLifecycle, float, float, float]] = {}
    for candidate in candidates:
        score, _abs_delay, a, b, *_rest = candidate
        i = row_index[a.position_id]
        j = col_index[b.position_id]
        weights[i][j] = cardinality_bonus + score
        edges[(i, j)] = candidate
    assignment = _max_weight_assignment(weights)
    chosen = [edges[(i, j)] for i, j in enumerate(assignment) if j >= 0 and (i, j) in edges]
    chosen.sort(key=lambda item: (-item[0], item[1], item[2].open_time, item[3].open_time))
    return [
        (a, b, delay_s, time_similarity, lifecycle_similarity)
        for _score, _abs_delay, a, b, delay_s, time_similarity, lifecycle_similarity in chosen
    ]


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
    selected = _select_optimal_matches(candidates)

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
