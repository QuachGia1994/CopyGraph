from copygraph.batch import analyze_histories
from tests.batch_data import put, rows


def test_batch_merges_same_account_across_sources(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    left = rows("same")[:4]
    right = rows("same", delay=1200)[:4]
    for row in right:
        row["position_id"] += 100
        row["ticket"] += 100
    put(first, left)
    put(second, right)
    account = analyze_histories([first, second])["accounts"][0]
    assert account["account_id"] == "same"
    assert account["position_count"] == 4
    assert account["source_count"] == 2
    assert "sources" not in account
