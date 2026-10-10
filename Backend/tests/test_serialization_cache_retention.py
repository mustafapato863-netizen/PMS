"""Bounded retention for the performance serializer cache.

Digest identity stays ``ser:{id}:{year}:{sha256}``. These tests cover
supersession, year isolation, the finite cap, amortised expiry, index
consistency, legacy keys, and concurrent revisions.
"""
import threading

import pytest

from api import dependencies
from api.dependencies import (
    _serialize_cache,
    clear_serialization_cache,
    serialization_cache_key,
    serialize_performance_record,
)
from models.schemas import EvaluationData, PerformanceRecord


@pytest.fixture(autouse=True)
def _empty_serialization_cache():
    clear_serialization_cache()
    yield
    clear_serialization_cache()


def _record(*, row_id: str, score: float, year: int | None = 2026, notes: str = "keep the human note"):
    return PerformanceRecord(
        id=row_id,
        employee_id=f"E-{row_id}",
        employee_name="Cache retention",
        team="Outbound",
        month="August",
        year=year,
        status="Meets",
        evaluation=EvaluationData(score=score, grade="C", manager_notes=notes),
        raw_data={"marker": row_id, "T.Attend%": 0.65},
    )


def _revise(record, **changes):
    evaluation_changes = {}
    record_changes = {}
    for name, value in changes.items():
        if name in {"score", "notes"}:
            evaluation_changes["score" if name == "score" else "manager_notes"] = value
        else:
            record_changes[name] = value
    if evaluation_changes:
        record_changes["evaluation"] = record.evaluation.model_copy(update=evaluation_changes)
    return record.model_copy(update=record_changes)


class _Clock:
    def __init__(self, now: float):
        self.now = now

    def time(self) -> float:
        return self.now


def _assert_indexes_match():
    cache_keys = set(_serialize_cache)
    reverse = dependencies._serialize_key_identity
    generation = dependencies._serialize_generation
    assert set(dependencies._serialize_expiry) == cache_keys
    assert set(reverse) <= cache_keys
    assert len(reverse) == len(generation)
    for key, identity in reverse.items():
        assert generation.get(identity) == key
        assert key.startswith(f"ser:{identity[0]}:{identity[1]}:")
    for identity, key in generation.items():
        assert reverse.get(key) == identity
        assert key in _serialize_cache


def test_many_revisions_of_one_row_keep_a_single_entry():
    base = _record(row_id="rev-1", score=79.82)
    last = None
    for score in (79.82, 79.93, 80, 81, 82, 83, 84, 85, 86, 87):
        revised = _revise(base, score=score)
        last = serialize_performance_record(revised)
        assert last["evaluation"]["score"] == pytest.approx(score)
        assert last["evaluation"]["manager_notes"] == "keep the human note"
        assert last["raw_data"]["T.Attend%"] == pytest.approx(0.65)
        assert len(_serialize_cache) == 1
    assert last is not None
    assert list(_serialize_cache) == [serialization_cache_key(_revise(base, score=87))]
    _assert_indexes_match()


def test_same_id_in_different_years_stays_isolated():
    current = _record(row_id="same-record", year=2026, score=79.82)
    previous = _record(row_id="same-record", year=2025, score=11)
    first = serialize_performance_record(current)
    other = serialize_performance_record(previous)
    assert first["year"] == 2026
    assert other["year"] == 2025
    assert first["evaluation"]["score"] == pytest.approx(79.82)
    assert other["evaluation"]["score"] == 11
    assert serialize_performance_record(current) is first
    assert serialize_performance_record(previous) is other
    assert len(_serialize_cache) == 2
    _assert_indexes_match()


def test_non_int_year_uses_the_same_normalisation_as_the_cache_key():
    kept = _record(row_id="year-norm", year=2026, score=1)
    serialize_performance_record(kept)
    boolean_year = _record(row_id="year-norm", year=2026, score=2)
    object.__setattr__(boolean_year, "year", True)
    text_year = _record(row_id="year-norm", year=2026, score=3)
    object.__setattr__(text_year, "year", "2026")
    assert serialize_performance_record(boolean_year)["evaluation"]["score"] == 2
    assert serialize_performance_record(text_year)["evaluation"]["score"] == 3
    assert serialize_performance_record(kept)["evaluation"]["score"] == 1
    colon_id = _record(row_id="a:b:c", year=2024, score=4)
    assert serialize_performance_record(colon_id)["evaluation"]["score"] == 4
    assert serialize_performance_record(_revise(colon_id, score=5))["evaluation"]["score"] == 5
    assert [key for key in _serialize_cache if key.startswith("ser:a:b:c:")] == [
        serialization_cache_key(_revise(colon_id, score=5))
    ]
    assert len([key for key in _serialize_cache if key.startswith("ser:year-norm:")]) == 2
    assert serialization_cache_key(kept) in _serialize_cache
    _assert_indexes_match()


def test_unchanged_warm_read_returns_the_identical_object():
    row = _record(row_id="warm", score=79.82)
    first = serialize_performance_record(row)
    assert serialize_performance_record(row) is first
    assert first["evaluation"]["manager_notes"] == "keep the human note"


def test_alternating_snapshots_return_their_own_evidence():
    old = _record(row_id="flip", score=10, notes="old-note")
    new = _revise(old, score=20, notes="new-note")
    for _ in range(4):
        got_old = serialize_performance_record(old)
        got_new = serialize_performance_record(new)
        assert got_old is not got_new
        assert got_old["evaluation"]["score"] == 10
        assert got_old["evaluation"]["manager_notes"] == "old-note"
        assert got_old["raw_data"]["marker"] == "flip"
        assert got_new["evaluation"]["score"] == 20
        assert got_new["evaluation"]["manager_notes"] == "new-note"
    assert len(_serialize_cache) == 1
    assert serialization_cache_key(new) in _serialize_cache
    _assert_indexes_match()


def test_cap_pressure_keeps_the_most_recent_rows(monkeypatch):
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_CAPACITY", 5)
    rows = [_record(row_id=f"cap-{index}", score=index) for index in range(12)]
    for row in rows:
        serialize_performance_record(row)
        assert len(_serialize_cache) <= 5
    assert len(_serialize_cache) == 5
    for row in rows[:7]:
        assert serialization_cache_key(row) not in _serialize_cache
    for row in rows[7:]:
        assert serialization_cache_key(row) in _serialize_cache
        again = serialize_performance_record(row)
        assert again["id"] == row.id
        assert again["evaluation"]["score"] == row.evaluation.score
    rebuilt = serialize_performance_record(rows[0])
    assert rebuilt["evaluation"]["score"] == 0
    assert rebuilt["id"] == "cap-0"
    assert len(_serialize_cache) <= 5
    assert serialization_cache_key(rows[0]) in _serialize_cache
    _assert_indexes_match()


def test_expiry_cleanup_is_amortised(monkeypatch):
    clock = _Clock(1_700_000_000.0)
    monkeypatch.setattr(dependencies, "time", clock)
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_EXPIRY_BUDGET", 2)
    rows = [_record(row_id=f"exp-{index}", score=index) for index in range(10)]
    for row in rows:
        serialize_performance_record(row)
    assert len(_serialize_cache) == 10
    clock.now += 299
    assert serialize_performance_record(rows[0]) is serialize_performance_record(rows[0])
    clock.now += 1
    fresh = _record(row_id="exp-new", score=99)
    serialize_performance_record(fresh)
    removed = sum(1 for row in rows if serialization_cache_key(row) not in _serialize_cache)
    assert 1 <= removed <= 4
    assert serialization_cache_key(fresh) in _serialize_cache
    for _ in range(10):
        got = serialize_performance_record(fresh)
        assert got["evaluation"]["score"] == 99
    for row in rows:
        assert serialization_cache_key(row) not in _serialize_cache
    assert serialization_cache_key(fresh) in _serialize_cache
    assert len(_serialize_cache) == 1
    _assert_indexes_match()


def test_clear_and_direct_clear_leave_indexes_consistent(monkeypatch):
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_CAPACITY", 5)
    for index in range(3):
        serialize_performance_record(_record(row_id=f"clear-{index}", score=index))
    clear_serialization_cache()
    assert len(_serialize_cache) == 0
    _assert_indexes_match()

    for index in range(4):
        serialize_performance_record(_record(row_id=f"direct-{index}", score=index))
    _serialize_cache[f"ser:legacy-direct"] = ({"evaluation": {"score": 1}}, dependencies.time.time() + 300)
    assert len(_serialize_cache) == 5
    _serialize_cache.clear()
    assert len(_serialize_cache) == 0
    _assert_indexes_match()

    for index in range(3):
        got = serialize_performance_record(_record(row_id=f"after-{index}", score=index + 10))
        assert got["evaluation"]["score"] == index + 10
    assert len(_serialize_cache) == 3
    _assert_indexes_match()


def test_foreign_legacy_key_survives_supersession_and_its_own_expiry(monkeypatch):
    clock = _Clock(5_000_000.0)
    monkeypatch.setattr(dependencies, "time", clock)
    current = _record(row_id="same-record", year=2026, score=79.82)
    foreign = f"ser:{current.id}"
    _serialize_cache[foreign] = (
        {"evaluation": {"score": 1}, "raw_data": {}, "kpi_values": []},
        clock.now + 10_000,
    )
    _serialize_cache["ser:malformed"] = "nope"
    first = serialize_performance_record(current)
    assert first["evaluation"]["score"] == pytest.approx(79.82)
    latest = current
    for score in (79.93, 80, 81):
        latest = _revise(current, score=score)
        got = serialize_performance_record(latest)
        assert got["evaluation"]["score"] == pytest.approx(score)
        assert got["evaluation"]["manager_notes"] == "keep the human note"
    other_year = _record(row_id="same-record", year=2025, score=11)
    assert serialize_performance_record(other_year)["evaluation"]["score"] == 11
    assert serialize_performance_record(other_year)["year"] == 2025
    assert foreign in _serialize_cache
    assert "ser:malformed" in _serialize_cache
    assert len([key for key in _serialize_cache if key.startswith("ser:same-record:2026:")]) == 1
    _assert_indexes_match()

    clock.now += 300
    survivor = serialize_performance_record(_record(row_id="fresh-after-expiry", score=4))
    assert survivor["evaluation"]["score"] == 4
    assert foreign in _serialize_cache
    assert "ser:malformed" in _serialize_cache
    assert serialization_cache_key(latest) not in _serialize_cache
    assert serialization_cache_key(other_year) not in _serialize_cache
    _assert_indexes_match()

    clock.now += 10_000
    serialize_performance_record(_record(row_id="fresh-after-foreign-expiry", score=6))
    assert foreign not in _serialize_cache
    _assert_indexes_match()


def test_cap_pressure_may_evict_a_foreign_key_and_keeps_the_newest_row(monkeypatch):
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_CAPACITY", 3)
    for index in range(5):
        _serialize_cache[f"ser:foreign-{index}"] = ({"n": index}, dependencies.time.time() + 300)
    assert len(_serialize_cache) == 5
    newest = _record(row_id="newest", score=8)
    got = serialize_performance_record(newest)
    assert got["evaluation"]["score"] == 8
    assert len(_serialize_cache) <= 3
    assert serialization_cache_key(newest) in _serialize_cache
    _assert_indexes_match()


def test_threaded_revisions_return_their_own_scores(monkeypatch):
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_CAPACITY", 8)
    row_ids = [f"thread-row-{index}" for index in range(12)]
    errors = []
    barrier = threading.Barrier(4)

    def worker(index: int):
        try:
            barrier.wait(timeout=5)
            for revision in range(15):
                row_id = row_ids[(index + revision) % len(row_ids)]
                score = float(index * 100 + revision)
                notes = f"t{index}-r{revision}"
                got = serialize_performance_record(_record(row_id=row_id, score=score, notes=notes))
                if got["evaluation"]["score"] != score or got["evaluation"]["manager_notes"] != notes:
                    errors.append((index, revision, got["evaluation"]))
                if got["id"] != row_id:
                    errors.append((index, revision, got["id"]))
        except Exception as exc:
            errors.append(repr(exc))

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()
    assert errors == []
    assert len(_serialize_cache) <= 8
    _assert_indexes_match()


def test_foreign_expiry_cleanup_reaches_past_a_live_prefix(monkeypatch):
    clock = _Clock(1_000)
    monkeypatch.setattr(dependencies, "time", clock)
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_EXPIRY_BUDGET", 2)
    for index in range(6):
        _serialize_cache[f"legacy-live-{index}"] = ({"marker": index}, 10_000)
    _serialize_cache["legacy-expired"] = ({"marker": "expired"}, 999)
    row = _record(row_id="cleanup-cursor", score=7)
    result = serialize_performance_record(row)
    for _ in range(8):
        assert serialize_performance_record(row) is result
    assert "legacy-expired" not in _serialize_cache
    assert all(f"legacy-live-{index}" in _serialize_cache for index in range(6))
    _assert_indexes_match()


def test_owned_expiry_cleanup_handles_a_later_shorter_expiry(monkeypatch):
    clock = _Clock(1_000)
    monkeypatch.setattr(dependencies, "time", clock)
    monkeypatch.setattr(dependencies, "_SERIALIZE_CACHE_EXPIRY_BUDGET", 2)
    rows = [_record(row_id=f"live-prefix-{index}", score=index) for index in range(6)]
    for row in rows:
        serialize_performance_record(row)
    tail = _record(row_id="expired-tail", score=9)
    serialize_performance_record(tail)
    tail_key = serialization_cache_key(tail)
    # Exercise a non-FIFO expiry order (e.g. an earlier-started writer or a
    # wall-clock correction) without sleeps or fabricated serializer results.
    payload, _ = _serialize_cache[tail_key]
    _serialize_cache[tail_key] = (payload, 999)
    survivor = serialize_performance_record(rows[0])
    for _ in range(8):
        assert serialize_performance_record(rows[0]) is survivor
    assert tail_key not in _serialize_cache
    _assert_indexes_match()


def test_ttl_starts_when_the_completed_payload_is_stored(monkeypatch):
    class BuildClock:
        calls = 0

        def time(self):
            self.calls += 1
            return 0 if self.calls == 1 else 1_000

    clock = BuildClock()
    monkeypatch.setattr(dependencies, "time", clock)
    row = _record(row_id="slow-build", score=12)
    result = serialize_performance_record(row)
    payload, expires = _serialize_cache[serialization_cache_key(row)]
    assert payload is result
    assert expires == 1_000 + dependencies._SERIALIZE_CACHE_TTL
    assert serialize_performance_record(row) is result


def test_warm_reads_do_not_scan_before_any_expiry_is_due(monkeypatch):
    clock = _Clock(1_000)
    monkeypatch.setattr(dependencies, "time", clock)
    rows = [_record(row_id=f"warm-no-scan-{index}", score=index) for index in range(8)]
    results = [serialize_performance_record(row) for row in rows]
    order = list(dependencies._serialize_expiry)
    for _ in range(3):
        assert serialize_performance_record(rows[0]) is results[0]
        assert list(dependencies._serialize_expiry) == order
    assert dependencies._serialize_next_expiry == 1_300
