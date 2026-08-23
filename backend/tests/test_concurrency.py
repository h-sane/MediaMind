"""hash_timeout_for's size-scaling and its safety cap."""

from mediamind.core.concurrency import (
    MAX_FILE_TIMEOUT_SECONDS,
    MIN_HASH_THROUGHPUT_BYTES_PER_SEC,
    hash_timeout_for,
)


def test_small_file_gets_the_floor():
    assert hash_timeout_for(0, floor=30) == 30
    assert hash_timeout_for(1024, floor=30) == 30


def test_medium_file_scales_with_size():
    # 100 MB at the 5 MB/s floor throughput = 20s, above the 30s floor once
    # it's big enough, below the cap.
    size = 300 * 1024 * 1024
    expected = size / MIN_HASH_THROUGHPUT_BYTES_PER_SEC
    assert 30 < expected < MAX_FILE_TIMEOUT_SECONDS
    assert hash_timeout_for(size, floor=30) == expected


def test_huge_file_is_capped_not_unbounded():
    # A ~6 GB stalled cloud placeholder would otherwise get a ~1200s budget and
    # freeze the whole scan — the regression this cap fixes.
    assert hash_timeout_for(6 * 1024**3, floor=30) == MAX_FILE_TIMEOUT_SECONDS
    assert hash_timeout_for(10 * 1024**3, floor=30) == MAX_FILE_TIMEOUT_SECONDS
