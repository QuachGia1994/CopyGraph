from __future__ import annotations

import random
from datetime import datetime, timezone
from itertools import permutations
from types import SimpleNamespace

import pytest

from copygraph.matching import _max_weight_assignment, _select_optimal_matches


def _brute_force_best(weights: list[list[float]]) -> float:
    n_rows = len(weights)
    n_cols = len(weights[0]) if n_rows else 0
    size = max(n_rows, n_cols)
    padded = [
        [weights[i][j] if i < n_rows and j < n_cols else 0.0 for j in range(size)]
        for i in range(size)
    ]
    return max(sum(padded[i][perm[i]] for i in range(size)) for perm in permutations(range(size)))


def _assignment_weight(weights: list[list[float]], assignment: list[int]) -> float:
    return sum(weights[i][j] for i, j in enumerate(assignment) if j >= 0)


def test_max_weight_assignment_matches_brute_force():
    rng = random.Random(20260915)
    for _ in range(200):
        n_rows = rng.randint(1, 5)
        n_cols = rng.randint(1, 5)
        weights = [[rng.uniform(0.0, 1.0) for _ in range(n_cols)] for _ in range(n_rows)]
        assignment = _max_weight_assignment(weights)
        assigned_cols = [j for j in assignment if j >= 0]
        assert len(assigned_cols) == len(set(assigned_cols))
        assert _assignment_weight(weights, assignment) == pytest.approx(_brute_force_best(weights))


def _candidate(score: float, a_id: str, b_id: str, moment: datetime) -> tuple:
    a = SimpleNamespace(position_id=a_id, open_time=moment)
    b = SimpleNamespace(position_id=b_id, open_time=moment)
    return (score, 0.0, a, b, 0.0, score, 0.0)


def test_select_optimal_matches_beats_greedy_blocking():
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = [
        _candidate(0.9, "a1", "b1", moment),
        _candidate(0.5, "a1", "b2", moment),
        _candidate(0.5, "a2", "b1", moment),
    ]
    selected = _select_optimal_matches(candidates)
    pairs = {(a.position_id, b.position_id) for a, b, *_ in selected}
    assert pairs == {("a1", "b2"), ("a2", "b1")}


def test_select_optimal_matches_keeps_single_dominant_pair():
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = [
        _candidate(0.9, "a1", "b1", moment),
        _candidate(0.4, "a2", "b2", moment),
    ]
    selected = _select_optimal_matches(candidates)
    pairs = {(a.position_id, b.position_id) for a, b, *_ in selected}
    assert pairs == {("a1", "b1"), ("a2", "b2")}


def test_select_optimal_matches_empty():
    assert _select_optimal_matches([]) == []
