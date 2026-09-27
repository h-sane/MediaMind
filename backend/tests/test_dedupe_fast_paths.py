"""The faster duplicate paths (s102) give exactly the old results."""

import random
import time

import numpy as np

from mediamind.core.dedupe import _phash_bits
from mediamind.core.hashing import hash_bytes, hash_file


def test_hash_bytes_matches_hash_file(tmp_path):
    p = tmp_path / "a.jpg"
    p.write_bytes(bytes(range(256)) * 5000)
    assert hash_bytes(p.read_bytes()) == hash_file(p)


def test_vectorised_near_pairs_match_pairwise():
    import imagehash

    rng = random.Random(7)
    hashes = [imagehash.hex_to_hash(f"{rng.getrandbits(64):016x}") for _ in range(300)]
    hashes += [imagehash.hex_to_hash(f"{int(str(h), 16) ^ (1 << rng.randrange(64)):016x}") for h in hashes[:50]]
    threshold = 5
    slow = {(a, b) for a in range(len(hashes)) for b in range(a + 1, len(hashes)) if hashes[a] - hashes[b] <= threshold}
    bits = np.array([_phash_bits(h) for h in hashes], dtype=np.uint64)
    fast = {(a, a + 1 + int(b)) for a in range(len(hashes) - 1)
            for b in np.nonzero(np.bitwise_count(bits[a + 1:] ^ bits[a]) <= threshold)[0]}
    assert fast == slow and len(slow) >= 50


def test_near_pairs_for_20000_pictures_take_seconds():
    rng = np.random.default_rng(1)
    bits = rng.integers(0, 2**63, size=20_000, dtype=np.uint64)
    start = time.perf_counter()
    for a in range(len(bits) - 1):
        np.nonzero(np.bitwise_count(bits[a + 1:] ^ bits[a]) <= 5)
    assert time.perf_counter() - start < 30
