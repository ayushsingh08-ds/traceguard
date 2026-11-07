import pytest
from app.ingestion.deduplicator import AlertDeduplicator, InMemorySlidingWindowCache


@pytest.mark.asyncio
async def test_in_memory_deduplicator_single_alert():
    dedup = AlertDeduplicator(redis_client=None, window_seconds=60)
    fingerprint = "a" * 64

    res = await dedup.evaluate_and_record(fingerprint)
    assert res.is_duplicate is False
    assert res.occurrence_count == 1
    assert res.fingerprint == fingerprint


@pytest.mark.asyncio
async def test_deduplicator_spike_1000_duplicates():
    dedup = AlertDeduplicator(redis_client=None, window_seconds=60)
    fingerprint = "b" * 64

    first = await dedup.evaluate_and_record(fingerprint)
    assert first.is_duplicate is False
    assert first.occurrence_count == 1

    for _ in range(999):
        res = await dedup.evaluate_and_record(fingerprint)
        assert res.is_duplicate is True

    assert res.occurrence_count == 1000


@pytest.mark.asyncio
async def test_deduplicator_isolates_independent_services():
    dedup = AlertDeduplicator(redis_client=None, window_seconds=60)
    fp1 = "1" * 64
    fp2 = "2" * 64

    res1 = await dedup.evaluate_and_record(fp1)
    res2 = await dedup.evaluate_and_record(fp2)

    assert res1.is_duplicate is False
    assert res2.is_duplicate is False
    assert res1.occurrence_count == 1
    assert res2.occurrence_count == 1

