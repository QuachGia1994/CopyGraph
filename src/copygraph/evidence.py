from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict

from .matching import MatchedTrade, PairAnalysis


def analysis_to_evidence(analysis: PairAnalysis) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "accounts": [analysis.account_a, analysis.account_b],
        "orientation": analysis.orientation,
        "score": analysis.score,
        "confidence": analysis.confidence,
        "confidence_factors": {
            "overlap": analysis.overlap_factor,
            "sample": analysis.sample_factor,
        },
        "matching_window_s": analysis.matching_window_s,
        "lead_account": analysis.lead_account,
        "median_delay_s": analysis.median_delay_s,
        "volume_similarity": analysis.volume_similarity,
        "totals": {"a": analysis.total_a, "b": analysis.total_b, "matched": len(analysis.matches)},
        "matches": [asdict(match) for match in analysis.matches],
    }


def analysis_from_evidence(payload: Mapping[str, object]) -> PairAnalysis:
    if payload.get("schema_version") != "1.0":
        raise ValueError("evidence schema_version must be 1.0")
    accounts = payload.get("accounts")
    totals = payload.get("totals")
    raw_matches = payload.get("matches")
    if not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("evidence accounts must contain two entries")
    if not isinstance(totals, Mapping) or not isinstance(raw_matches, list):
        raise ValueError("invalid evidence payload")
    factors = payload.get("confidence_factors")
    if isinstance(factors, Mapping):
        overlap = float(factors.get("overlap", 0.0))
        sample = float(factors.get("sample", 0.0))
    else:
        overlap = 0.0
        sample = 0.0
    matches: list[MatchedTrade] = []
    for item in raw_matches:
        if not isinstance(item, Mapping):
            raise ValueError("invalid matched trade payload")
        matches.append(MatchedTrade(
            a_position_id=str(item["a_position_id"]),
            b_position_id=str(item["b_position_id"]),
            delay_s=float(item["delay_s"]),
            time_similarity=float(item["time_similarity"]),
            lifecycle_similarity=float(item["lifecycle_similarity"]),
            risk_similarity=float(item["risk_similarity"]),
            volume_similarity=float(item["volume_similarity"]),
            rarity_weight=float(item["rarity_weight"]),
            score=float(item["score"]),
        ))
    return PairAnalysis(
        account_a=None if accounts[0] is None else str(accounts[0]),
        account_b=None if accounts[1] is None else str(accounts[1]),
        orientation=str(payload.get("orientation", "normal")),
        score=float(payload.get("score", 0.0)),
        confidence=float(payload.get("confidence", 0.0)),
        matches=matches,
        volume_similarity=float(payload.get("volume_similarity", 0.0)),
        lead_account=None if payload.get("lead_account") is None else str(payload["lead_account"]),
        median_delay_s=float(payload.get("median_delay_s", 0.0)),
        total_a=int(totals.get("a", 0)),
        total_b=int(totals.get("b", 0)),
        overlap_factor=overlap,
        sample_factor=sample,
        matching_window_s=float(payload.get("matching_window_s", 0.0)),
    )
