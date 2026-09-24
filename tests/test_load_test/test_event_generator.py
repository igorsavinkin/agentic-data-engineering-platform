"""Tests for the load-test event generator (TASK-108)."""

from __future__ import annotations

from libs.load_test.event_generator import EventGenerator


def test_generator_produes_valid_events() -> None:
    gen = EventGenerator(source="test-source", seed=1)
    event = gen.next_event()

    assert event.source == "test-source"
    assert event.event_type == "product.observation"
    assert event.schema_version == 1
    assert event.payload.external_id == "lt-00000001"
    assert event.payload.name == "Load Test Product 1"
    assert event.payload.price is not None
    assert event.payload.price >= 0


def test_generator_is_deterministic_with_seed() -> None:
    gen1 = EventGenerator(source="test", seed=42)
    gen2 = EventGenerator(source="test", seed=42)

    events1 = gen1.generate_batch(10)
    events2 = gen2.generate_batch(10)

    for e1, e2 in zip(events1, events2):
        assert e1.payload.external_id == e2.payload.external_id
        assert e1.payload.price == e2.payload.price
        assert e1.payload.currency == e2.payload.currency
        assert e1.payload.availability == e2.payload.availability
        assert e1.payload.category == e2.payload.category


def test_generator_different_seeds_differ() -> None:
    gen1 = EventGenerator(source="test", seed=1)
    gen2 = EventGenerator(source="test", seed=2)

    events1 = gen1.generate_batch(5)
    events2 = gen2.generate_batch(5)

    prices1 = [e.payload.price for e in events1]
    prices2 = [e.payload.price for e in events2]
    assert prices1 != prices2


def test_generate_batch_returns_correct_count() -> None:
    gen = EventGenerator()
    batch = gen.generate_batch(25)
    assert len(batch) == 25


def test_event_ids_are_unique() -> None:
    gen = EventGenerator()
    events = gen.generate_batch(100)
    ids = [e.event_id for e in events]
    assert len(set(ids)) == 100


def test_external_ids_are_sequential() -> None:
    gen = EventGenerator()
    events = gen.generate_batch(5)
    expected = [f"lt-{i:08d}" for i in range(1, 6)]
    actual = [e.payload.external_id for e in events]
    assert actual == expected


def test_availability_values_are_valid() -> None:
    gen = EventGenerator(seed=99)
    events = gen.generate_batch(50)
    valid = {"in_stock", "out_of_stock", "preorder", "unknown"}
    for event in events:
        assert event.payload.availability.value in valid


def test_currency_is_three_uppercase_letters() -> None:
    gen = EventGenerator(seed=7)
    events = gen.generate_batch(50)
    for event in events:
        assert len(event.payload.currency) == 3
        assert event.payload.currency.isupper()
        assert event.payload.currency.isalpha()


def test_event_id_contains_worker_and_run_id() -> None:
    gen = EventGenerator(seed=1, worker_id=3, run_id="abc12345")
    event = gen.next_event()
    assert event.event_id == "abc12345-3-1"


def test_event_ids_unique_across_workers() -> None:
    gens = [EventGenerator(seed=42, worker_id=w, run_id="run1") for w in range(4)]
    all_ids: list[str] = []
    for gen in gens:
        all_ids.extend(e.event_id for e in gen.generate_batch(50))
    assert len(all_ids) == len(set(all_ids))
