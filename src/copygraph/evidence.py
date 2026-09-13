from __future__ import annotations

from dataclasses import asdict

from .matching import PairAnalysis


def analysis_to_evidence(analysis: PairAnalysis) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "accounts": [analysis.account_a, analysis.account_b],
        "orientation": analysis.orientation,
        "score": analysis.score,
        "confidence": analysis.confidence,
        "lead_account": analysis.lead_account,
        "median_delay_s": analysis.median_delay_s,
        "volume_similarity": analysis.volume_similarity,
        "totals": {"a": analysis.total_a, "b": analysis.total_b, "matched": len(analysis.matches)},
        "matches": [asdict(match) for match in analysis.matches],
    }
