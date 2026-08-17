import retrain_state as rs


def test_compute_delta_positive():
    assert rs.compute_delta(current_count=15, baseline_count=5) == 10


def test_compute_delta_zero_when_equal():
    assert rs.compute_delta(current_count=5, baseline_count=5) == 0


def test_compute_delta_never_negative():
    assert rs.compute_delta(current_count=3, baseline_count=10) == 0


def test_read_baseline_defaults_to_zero_when_file_missing(tmp_path):
    state_path = tmp_path / "state.json"
    assert rs.read_baseline(state_path) == 0


def test_write_then_read_baseline_round_trips(tmp_path):
    state_path = tmp_path / "state.json"
    rs.write_baseline(42, state_path)
    assert rs.read_baseline(state_path) == 42


def test_write_baseline_creates_parent_dirs(tmp_path):
    state_path = tmp_path / "nested" / "dir" / "state.json"
    rs.write_baseline(7, state_path)
    assert state_path.exists()
    assert rs.read_baseline(state_path) == 7
