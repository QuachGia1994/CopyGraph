from copygraph.forensic_dashboard import render_forensic_dashboard, write_forensic_dashboard


def sample_report(account_a="a"):
    return {
        "schema_version": "1.0",
        "accounts": [account_a, "b"],
        "orientation": "normal",
        "raw_confidence": 0.8,
        "calibrated_confidence": None,
        "warnings": [],
        "timeline": [],
        "delay_summary": {"buckets": []},
        "lot_ratio": {"series": []},
        "symbol_breakdown": [],
        "supporting_matches": [],
        "contradictory_matches": [],
        "contradictory_evidence": [],
    }


def test_forensic_dashboard_is_self_contained_and_escapes_script_close():
    html = render_forensic_dashboard(sample_report("</script><img src=x onerror=alert(1)>"))
    assert "https://" not in html
    assert "http://" not in html
    assert "</script><img" not in html
    assert "\\u003c/script>" in html
    for section_id in (
        "forensic-summary",
        "forensic-warnings",
        "forensic-timeline",
        "delay-histogram",
        "lot-ratio-drift",
        "symbol-breakdown",
        "supporting-evidence",
        "contradictory-evidence",
        "forensic-network",
    ):
        assert f'id="{section_id}"' in html
    assert "innerHTML" not in html


def test_forensic_dashboard_is_deterministic():
    report = sample_report()
    assert render_forensic_dashboard(report) == render_forensic_dashboard(report)


def test_write_forensic_dashboard_creates_utf8_file(tmp_path):
    output = tmp_path / "nested" / "forensic.html"
    written = write_forensic_dashboard(sample_report(), output)
    assert written == output
    assert output.read_text(encoding="utf-8") == render_forensic_dashboard(sample_report())
