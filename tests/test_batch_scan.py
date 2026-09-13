from copygraph.batch import analyze_histories
from tests.batch_data import put, rows


def test_batch_scan(tmp_path):
    put(tmp_path / "one.json", rows("one") + rows("two", delay=20))
    put(tmp_path / "three.json", rows("three", symbol="USDJPY", delay=20000))
    report = analyze_histories([tmp_path])
    assert len(report["accounts"]) == 3
    assert len(report["pairs"]) == 3
    assert report["graph"]["nodes"] == ["one", "three", "two"]
    assert len(report["graph"]["edges"]) == 1
    assert report["clusters"] == [["one", "two"], ["three"]]
