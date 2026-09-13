from datetime import datetime, timedelta, timezone

import pytest

from copygraph.dna import trade_dna
from copygraph.matching import MatchingConfig, analyze_pair, rarity_weight
from copygraph.models import PositionLifecycle


BASE = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)


def pos(account, pid, symbol="EURUSD", side="BUY", open_s=0, duration_s=300, volume=1.0, sl=1.09, tp=1.12):
    opened = BASE + timedelta(seconds=open_s)
    closed = None if duration_s is None else opened + timedelta(seconds=duration_s)
    return PositionLifecycle(
        account_id=account,
        position_id=str(pid),
        symbol=symbol,
        side=side,
        open_time=opened,
        close_time=closed,
        open_price=1.10,
        close_price=None if closed is None else 1.11,
        volume=volume,
        sl=sl,
        tp=tp,
        profit=10.0,
        tickets=(str(pid),),
    )


def copied_pair(delay=20, reverse=False, volume_scale=1.0):
    master = [pos("master", i, open_s=i * 600, volume=0.1 * (i + 1)) for i in range(4)]
    slave = [
        pos("slave", i, side="SELL" if reverse else "BUY", open_s=i * 600 + delay, volume=0.1 * (i + 1) * volume_scale)
        for i in range(4)
    ]
    return master, slave


def test_trade_dna_is_stable_and_canonicalizes_symbol():
    position = pos("a", 1, symbol="EURUSD.pro")
    first = trade_dna(position)
    assert first is not None
    assert first == trade_dna(position)
    assert first.symbol == "EURUSD"


def test_trade_dna_preserves_direction():
    assert trade_dna(pos("a", 1, side="BUY")).side != trade_dna(pos("a", 1, side="SELL")).side


def test_trade_dna_captures_risk_reward_distances():
    dna = trade_dna(pos("a", 1, sl=1.08, tp=1.15))
    assert dna.risk_distance == pytest.approx(0.02)
    assert dna.reward_distance == pytest.approx(0.05)


def test_missing_stops_do_not_create_false_risk_similarity():
    master, slave = copied_pair()
    master = [pos("master", i, open_s=i * 600, sl=None) for i in range(4)]
    slave = [pos("slave", i, open_s=i * 600 + 20, sl=None) for i in range(4)]
    analysis = analyze_pair(master, slave)
    assert all(match.risk_similarity == 0.0 for match in analysis.matches)


def test_normal_copy_scores_high():
    master, slave = copied_pair()
    analysis = analyze_pair(master, slave)
    assert analysis.orientation == "normal"
    assert analysis.confidence >= 0.75
    assert len(analysis.matches) == 4


def test_reverse_copy_is_detected():
    master, slave = copied_pair(reverse=True)
    analysis = analyze_pair(master, slave)
    assert analysis.orientation == "reverse"
    assert analysis.confidence >= 0.75


def test_unrelated_accounts_score_low():
    master, _ = copied_pair()
    unrelated = [pos("other", i, symbol="USDJPY", open_s=20_000 + i * 900) for i in range(4)]
    analysis = analyze_pair(master, unrelated)
    assert analysis.total_a == 4 and analysis.total_b == 4
    assert analysis.confidence < 0.25


def test_delay_within_sixty_seconds_remains_high_confidence():
    master, slave = copied_pair(delay=60)
    assert analyze_pair(master, slave).confidence >= 0.70


def test_large_delay_is_penalized():
    master, slave = copied_pair(delay=300)
    analysis = analyze_pair(master, slave)
    assert len(analysis.matches) == 4
    assert analysis.confidence < 0.70


def test_consistent_lot_scaling_is_treated_as_copy_pattern():
    master, slave = copied_pair(volume_scale=3.0)
    analysis = analyze_pair(master, slave)
    assert analysis.volume_similarity >= 0.95
    assert analysis.confidence >= 0.75


def test_lead_lag_infers_master_account():
    master, slave = copied_pair(delay=15)
    analysis = analyze_pair(master, slave)
    assert analysis.lead_account == "master"
    assert analysis.median_delay_s == pytest.approx(15)


def test_rarity_weight_decreases_for_common_patterns():
    assert rarity_weight(1) > rarity_weight(5) > rarity_weight(20)


def test_small_sample_is_confidence_penalized():
    analysis = analyze_pair([pos("a", 1)], [pos("b", 1, open_s=10)])
    assert analysis.score > 0.8
    assert analysis.confidence < 0.5


def test_matching_is_one_to_one_and_does_not_reuse_trade():
    account_a = [pos("a", 1, open_s=0), pos("a", 2, open_s=5)]
    account_b = [pos("b", 9, open_s=3)]
    analysis = analyze_pair(account_a, account_b, MatchingConfig(min_matches=1))
    assert len(analysis.matches) == 1
