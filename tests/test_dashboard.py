from copygraph.dashboard import render_dashboard, write_dashboard


def sample_report():
    return {
        "schema_version": "2.0",
        "generated_at": "2026-09-13T09:00:00Z",
        "min_confidence": 0.7,
        "accounts": [
            {"account_id": "alpha", "position_count": 4, "sources": ["a.json"]},
            {"account_id": "beta", "position_count": 4, "sources": ["b.json"]},
        ],
        "pairs": [
            {
                "schema_version": "1.0",
                "accounts": ["alpha", "beta"],
                "orientation": "normal",
                "score": 0.95,
                "confidence": 0.92,
                "lead_account": "alpha",
                "median_delay_s": 12.0,
                "volume_similarity": 1.0,
                "totals": {"a": 4, "b": 4, "matched": 4},
                "matches": [],
            }
        ],
        "graph": {
            "nodes": ["alpha", "beta"],
            "edges": [
                {
                    "account_a": "alpha",
                    "account_b": "beta",
                    "confidence": 0.92,
                    "score": 0.95,
                    "orientation": "normal",
                    "lead_account": "alpha",
                }
            ],
        },
        "clusters": [["alpha", "beta"]],
    }


def test_dashboard_is_self_contained_and_contains_required_sections():
    html = render_dashboard(sample_report())
    assert "<!doctype html>" in html.lower()
    assert "CopyGraph" in html
    assert 'id="summary"' in html
    assert 'id="relationships"' in html
    assert 'id="clusters"' in html
    assert 'id="network"' in html
    assert "http://" not in html and "https://" not in html


def test_dashboard_embeds_report_data_for_client_rendering():
    html = render_dashboard(sample_report())
    assert '"schema_version":"2.0"' in html
    assert '"account_id":"alpha"' in html
    assert '"confidence":0.92' in html


def test_dashboard_escapes_script_close_sequence():
    report = sample_report()
    report["accounts"][0]["account_id"] = "</script><script>alert(1)</script>"
    html = render_dashboard(report)
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script>" in html


def test_dashboard_is_deterministic():
    report = sample_report()
    assert render_dashboard(report) == render_dashboard(report)


def test_write_dashboard_creates_utf8_file(tmp_path):
    output = tmp_path / "dashboard.html"
    result = write_dashboard(sample_report(), output)
    assert result == output
    assert output.read_text(encoding="utf-8") == render_dashboard(sample_report())
