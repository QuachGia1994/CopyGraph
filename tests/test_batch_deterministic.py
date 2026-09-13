from copygraph.batch import analyze_histories
from tests.batch_data import put, rows


def test_batch_report_is_deterministic_and_ranked(tmp_path):
    put(tmp_path / "a.json", rows("a"))
    put(tmp_path / "b.json", rows("b", delay=10))
    put(tmp_path / "c.json", rows("c", delay=55))
    first = analyze_histories([tmp_path])
    second = analyze_histories([tmp_path])
    assert first == second
    assert [pair["confidence"] for pair in first["pairs"]] == sorted((pair["confidence"] for pair in first["pairs"]), reverse=True)
    assert [edge["confidence"] for edge in first["graph"]["edges"]] == sorted((edge["confidence"] for edge in first["graph"]["edges"]), reverse=True)
    assert first["generated_at"] == "2026-09-10T10:35:55Z"
