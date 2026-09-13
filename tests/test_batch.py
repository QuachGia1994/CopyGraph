from pathlib import Path

import pytest

from copygraph.batch import analyze_histories, discover_history_files


def test_discover_history_files_recurses_sorts_and_deduplicates(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    a = tmp_path / "a.csv"
    b = nested / "b.json"
    ignored = tmp_path / "notes.txt"
    a.write_text("x", encoding="utf-8")
    b.write_text("[]", encoding="utf-8")
    ignored.write_text("x", encoding="utf-8")
    found = discover_history_files([tmp_path, a])
    assert found == sorted([a.resolve(), b.resolve()], key=lambda path: str(path).lower())


def test_analyze_histories_rejects_inputs_without_supported_history_files(tmp_path):
    (tmp_path / "notes.txt").write_text("none", encoding="utf-8")
    with pytest.raises(ValueError, match="No CSV or JSON history files"):
        analyze_histories([tmp_path])
