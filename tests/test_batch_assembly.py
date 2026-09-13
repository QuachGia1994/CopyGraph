from collections import defaultdict

from copygraph.batch import analyze_histories, assemble_batch_report, build_pair_analyses, discover_history_files
from copygraph.ingest import load_events
from copygraph.lifecycle import reconstruct_positions
from tests.batch_data import put, rows


def load_test_positions_like_batch(root):
    grouped = defaultdict(list)
    sources = defaultdict(set)
    latest = None
    for path in discover_history_files([root]):
        for event in load_events(path):
            grouped[event.account_id].append(event)
            sources[event.account_id].add(str(path))
            if latest is None or event.timestamp > latest:
                latest = event.timestamp
    positions = {account_id: reconstruct_positions(events) for account_id, events in grouped.items()}
    source_counts = {account_id: len(paths) for account_id, paths in sources.items()}
    return positions, source_counts, latest


def test_assembled_report_equals_stateless_batch(tmp_path):
    put(tmp_path / "a.json", rows("a"))
    put(tmp_path / "b.json", rows("b", delay=20))
    expected = analyze_histories([tmp_path])
    positions, source_counts, generated_at = load_test_positions_like_batch(tmp_path)
    analyses = build_pair_analyses(positions)
    actual = assemble_batch_report(positions, analyses, source_counts, generated_at)
    assert actual == expected
