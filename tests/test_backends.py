"""Backend parity, independent hash vectors, and public extension regressions."""

import importlib.util
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tracemalloc
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bloomfilter import (
    BitArray,
    BloomFilter,
    BYTE_ARRAY_FUNNEL,
    INTEGER_FUNNEL,
    LONG_FUNNEL,
    UTF8_STRING_FUNNEL,
    LEGACY_FUNNEL,
    StringFunnel,
)
from bloomfilter._bitarray import CHUNK_BYTES, _native_modules
from bloomfilter._murmur3 import hash64
from bloomfilter.bloomfilter_strategy import MURMUR128_MITZ_32, MURMUR128_MITZ_64

HAS_NATIVE = all(
    importlib.util.find_spec(name) is not None for name in ("bitarray", "mmh3")
)
BACKENDS = ("python", "native") if HAS_NATIVE else ("python",)


class HashTest(unittest.TestCase):
    def test_reference_vectors(self):
        vectors = json.loads(
            (Path(__file__).parent / "data/murmur3-vectors.json").read_text()
        )
        for vector in vectors:
            n = vector["length"]
            data = bytes((i * 37 + n) % 256 for i in range(n))
            with self.subTest(length=n):
                self.assertEqual(hash64(data), tuple(vector["hash"]))

    @unittest.skipUnless(HAS_NATIVE, "optional reference packages not installed")
    def test_random_hashes_against_mmh3(self):
        import mmh3

        rng = random.Random(40791)
        for _ in range(1000):
            data = bytes(rng.getrandbits(8) for _ in range(rng.randrange(2049)))
            self.assertEqual(hash64(data), mmh3.hash64(data))

    def test_bytes_only(self):
        for value in ("hello", 1, None, bytearray(b"hello")):
            with self.assertRaises(TypeError):
                hash64(value)


class BitArrayTest(unittest.TestCase):
    def test_sequence_operations_against_list(self):
        rng = random.Random(171)
        for backend in BACKENDS:
            for size in (0, 1, 7, 8, 9, 63, 64, 65, 257):
                bits, expected = BitArray(size, backend=backend), [0] * size
                for _ in range(size * 2):
                    index, value = rng.randrange(-size, size), rng.randrange(2)
                    bits[index] = value
                    expected[index] = value
                self.assertEqual(list(bits), expected)
                self.assertEqual(bits.count(), sum(expected))
                self.assertEqual(bits.count(0), size - sum(expected))
                for sl in (
                    slice(None),
                    slice(None, None, -1),
                    slice(1, None, 3),
                    slice(12, 4),
                    slice(None, 0, -2),
                ):
                    self.assertEqual(list(bits[sl]), expected[sl])
                bits[::2] = 1
                expected[::2] = [1] * len(expected[::2])
                bits[1::2] = [0] * len(expected[1::2])
                expected[1::2] = [0] * len(expected[1::2])
                self.assertEqual(list(bits), expected)
                for value in (0, 1):
                    bits.setall(value)
                    self.assertEqual(bits.count(), size * value)
                    if size % 8:
                        self.assertEqual(
                            bits.tobytes()[-1] & ((1 << (8 - size % 8)) - 1), 0
                        )

    def test_append_and_copy_at_unaligned_lengths(self):
        for backend in BACKENDS:
            for size in range(17):
                bits = BitArray(size, backend=backend)
                bits.setall(1)
                bits.frombytes(b"\x81\xff\x00")
                expected = [1] * size + [int(v) for v in "100000011111111100000000"]
                self.assertEqual(list(bits), expected)
                tail = BitArray(3, backend=backend)
                tail[1] = 1
                bits += tail
                expected += [0, 1, 0]
                self.assertEqual(list(bits), expected)
                bits += bits
                self.assertEqual(list(bits), expected + expected)
                copy = bits.copy()
                copy[0] = not copy[0]
                self.assertNotEqual(copy, bits)
                self.assertEqual(copy.backend, backend)

    def test_index_and_assignment_failures_are_atomic(self):
        for backend in BACKENDS:
            bits = BitArray(9, backend=backend)
            for i in (-10, 9):
                with self.assertRaises(IndexError):
                    bits[i] = 1
                with self.assertRaises(IndexError):
                    _ = bits[i]
            for value in (-1, 2):
                with self.assertRaises(ValueError):
                    bits[:] = value
                with self.assertRaises(ValueError):
                    bits.setall(value)
            for values in ([1], [1] * 8 + [2]):
                with self.assertRaises(ValueError):
                    bits[:] = values
                self.assertEqual(bits.count(), 0)
            with self.assertRaises(TypeError):
                bits[0] = 1.0
            with self.assertRaises(TypeError):
                bits.frombytes("bytes")
            with self.assertRaises(ValueError):
                _ = bits[::0]
            with self.assertRaises(ValueError):
                BitArray(-1, backend=backend)

    def test_cross_backend_merge_and_guava_chunks(self):
        for left_backend in BACKENDS:
            for right_backend in BACKENDS:
                for size in (65, 64, CHUNK_BYTES * 8 + 64):
                    left = BitArray(size, backend=left_backend)
                    right = BitArray(size, backend=right_backend)
                    left[0] = 1
                    right[-1] = 1
                    snapshot = right.copy()
                    left |= right
                    self.assertEqual(left.count(), 2)
                    self.assertEqual(right, snapshot)
                    copied = BitArray(size, backend=right_backend)
                    copied[0] = copied[-1] = 1
                    self.assertEqual(left, copied)
                    if size % 64 == 0:
                        loaded = BitArray(size, backend=right_backend)
                        offset = 0
                        for chunk in left.iter_guava_chunks():
                            self.assertLessEqual(len(chunk), CHUNK_BYTES)
                            loaded.set_guava_chunk(offset, chunk)
                            offset += len(chunk)
                        self.assertEqual(left, loaded)
        with self.assertRaises(ValueError):
            left = BitArray(64)
            left |= BitArray(128)
        with self.assertRaises(ValueError):
            list(BitArray(1).iter_guava_chunks())
        for offset, data in ((-8, bytes(8)), (1, bytes(8)), (0, b"a"), (8, bytes(8))):
            with self.assertRaises(ValueError):
                BitArray(64).set_guava_chunk(offset, data)
        self.assertNotEqual(BitArray(1), object())

    def test_unsupported_operators_preserve_data(self):
        for backend in BACKENDS:
            for operation in ("append", "union"):
                bits = BitArray(9, backend=backend)
                bits[0] = bits[-1] = 1
                before = bits.copy()
                with self.assertRaises(TypeError):
                    if operation == "append":
                        bits += [1, 0]
                    else:
                        bits |= [1, 0]
                self.assertEqual(bits, before)

    def test_cross_backend_equality_detects_different_contents(self):
        for left_backend in BACKENDS:
            for right_backend in BACKENDS:
                left = BitArray(65, backend=left_backend)
                right = BitArray(65, backend=right_backend)
                right[-1] = 1
                self.assertNotEqual(left, right)
                self.assertNotEqual(right, left)

    def test_count_without_int_bit_count(self):
        # Exercise the Python 3.8/3.9 capability fallback on newer CI runtimes.
        for size in (0, 1, 9, CHUNK_BYTES * 8 + 9):
            bits = BitArray(size)
            bits[::3] = 1
            expected = sum(bits)
            with patch("bloomfilter._bitarray.getattr", return_value=None, create=True):
                self.assertEqual(bits.count(), expected)
                self.assertEqual(bits.count(0), size - expected)

    def test_bulk_temporaries_are_bounded(self):
        for backend in BACKENDS:
            bits = BitArray(8 * 1024 * 1024, backend=backend)
            other = bits.copy()
            other[123] = 1
            tracemalloc.start()
            bits |= other
            self.assertEqual(bits.count(), 1)
            self.assertEqual(sum(map(len, bits.iter_guava_chunks())), 1024 * 1024)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertLess(peak, 1024 * 1024)


class BackendFilterTest(unittest.TestCase):
    def test_defaults_are_deterministic_and_native_is_explicit(self):
        self.assertEqual(BloomFilter(1, 0.01).backend, "python")
        for bad in ("auto", "", None, 1):
            with self.assertRaises(ValueError):
                BloomFilter(1, 0.01, backend=bad)
        _native_modules.cache_clear()
        with patch(
            "bloomfilter._bitarray.importlib.import_module",
            side_effect=ImportError("missing"),
        ):
            with self.assertRaisesRegex(ImportError, "bloomfilter-py\\[native\\]"):
                BloomFilter(1, 0.01, backend="native")
            self.assertEqual(BloomFilter(1, 0.01).backend, "python")
            stream = io.BytesIO(BloomFilter(1, 0.01).dumps())
            with self.assertRaises(ImportError):
                BloomFilter.read_from(stream, backend="native")
            self.assertEqual(stream.tell(), 0)
        _native_modules.cache_clear()

    def test_all_funnels_and_strategies_match_across_backends(self):
        rng = random.Random(45)
        cases = (
            (
                INTEGER_FUNNEL,
                [-(2**31), 2**31 - 1]
                + [rng.randrange(-100000, 100000) for _ in range(200)],
            ),
            (
                LONG_FUNNEL,
                [-(2**63), 2**63 - 1]
                + [rng.randrange(-(2**63), 2**63) for _ in range(200)],
            ),
            (
                UTF8_STRING_FUNNEL,
                ["", "雪", "emoji 😀", "\ud800", "\ud83d\ude00"]
                + [f"key-{i}" for i in range(200)],
            ),
            (StringFunnel("utf-16"), ["", "雪", "emoji 😀", "\ud800", "\ud83d\ude00"]),
            (BYTE_ARRAY_FUNNEL, [bytes(range(n)) for n in range(128)]),
            (LEGACY_FUNNEL, [True, False, -(2**40), "雪", "hello"]),
        )
        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            for funnel, values in cases:
                reference = BloomFilter(1000, 0.01, strategy, funnel)
                changed = [reference.put(value) for value in values]
                for backend in BACKENDS:
                    bf = BloomFilter(1000, 0.01, strategy, funnel, backend=backend)
                    self.assertEqual([bf.put(value) for value in values], changed)
                    self.assertTrue(all(value in bf for value in values))
                    self.assertEqual(reference, bf)
                    self.assertEqual(bf.dumps(), reference.dumps())
                    self.assertEqual(bf.expected_fpp(), reference.expected_fpp())
                    for loader, arg in (
                        (BloomFilter.loads, bf.dumps()),
                        (BloomFilter.loads_from_hex, bf.dumps_to_hex()),
                        (BloomFilter.loads_from_base64, bf.dumps_to_base64()),
                    ):
                        loaded = loader(arg, funnel, backend=backend)
                        self.assertEqual(loaded.backend, backend)
                        self.assertEqual(loaded, bf)
                    clone = bf.copy()
                    self.assertEqual(clone.backend, backend)
                    self.assertEqual(clone, bf)

    def test_absent_queries_match_across_backends(self):
        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            reference = BloomFilter(1000, 0.01, strategy, INTEGER_FUNNEL)
            for key in range(100):
                reference.put(key)
            queries = list(range(100)) + list(range(1000, 2000))
            expected = [key in reference for key in queries]
            self.assertTrue(all(expected[:100]))
            self.assertFalse(any(expected[100:]))
            for backend in BACKENDS:
                loaded = BloomFilter.loads(
                    reference.dumps(), INTEGER_FUNNEL, backend=backend
                )
                self.assertEqual([key in loaded for key in queries], expected)

    def test_setup_without_optional_bitarray_is_atomic(self):
        bf = BloomFilter(10, 0.01)
        bf.put("retained")
        before = bf.dumps()
        with patch("importlib.import_module", side_effect=ImportError("missing")):
            with self.assertRaisesRegex(TypeError, "data must be"):
                bf.setup(1, [0] * 64, MURMUR128_MITZ_64)
        self.assertEqual(bf.dumps(), before)
        self.assertIn("retained", bf)

    def test_cross_backend_merge_preserves_source(self):
        for left_backend in BACKENDS:
            for right_backend in BACKENDS:
                left = BloomFilter(100, 0.01, backend=left_backend)
                right = BloomFilter(100, 0.01, backend=right_backend)
                left.put("left")
                right.put("right")
                before = right.dumps()
                self.assertTrue(left.is_compatible(right))
                left.put_all(right)
                self.assertIn("left", left)
                self.assertIn("right", left)
                self.assertEqual(right.dumps(), before)

    def test_custom_hash_override_is_preserved(self):
        class Custom(MURMUR128_MITZ_64):
            @classmethod
            def hash_key(cls, key, funnel=LEGACY_FUNNEL):
                return (1, 2)

        for backend in BACKENDS:
            bf = BloomFilter(100, 0.01, Custom, backend=backend)
            bf.put("one")
            self.assertIn("different", bf)
            self.assertTrue(bf.data[1])
            with patch.object(Custom, "hash_key", side_effect=RuntimeError("custom")):
                with self.assertRaisesRegex(RuntimeError, "custom"):
                    bf.put("one")

    @unittest.skipUnless(HAS_NATIVE, "optional packages not installed")
    def test_legacy_setup_normalizes_external_bitarray(self):
        from bitarray import bitarray

        for endian in ("big", "little"):
            raw = bitarray(64, endian=endian)
            raw.setall(0)
            raw[5] = 1
            bf = BloomFilter(1, 0.01)
            bf.setup(1, raw, MURMUR128_MITZ_64)
            self.assertEqual(bf.backend, "python")
            self.assertEqual(bf.data.count(), 1)
            self.assertEqual(bf.data[5], 1)
            raw[6] = 1
            self.assertFalse(bf.data[6])
        with self.assertRaises(TypeError):
            bf.setup(1, [0] * 64, MURMUR128_MITZ_64)

    @unittest.skipUnless(HAS_NATIVE, "optional packages not installed")
    def test_setup_accepts_callable_legacy_endian(self):
        from bitarray import bitarray

        # Older bitarray versions exposed endian() rather than a property.
        class LegacyBitarray(bitarray):
            def endian(self):
                return super().endian

        for endian in ("big", "little"):
            raw = LegacyBitarray(64, endian=endian)
            raw.setall(0)
            raw[5] = raw[63] = 1
            bf = BloomFilter(1, 0.01)
            with patch(
                "importlib.import_module",
                return_value=SimpleNamespace(bitarray=LegacyBitarray),
            ):
                bf.setup(1, raw, MURMUR128_MITZ_64)
            self.assertEqual(list(bf.data), list(raw))
            raw[5] = 0
            self.assertTrue(bf.data[5])

    @unittest.skipUnless(HAS_NATIVE, "optional reference packages not installed")
    def test_direct_strategy_calls_with_legacy_bitarray(self):
        from bitarray import bitarray

        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            raw = bitarray(128)
            raw.setall(0)
            facade = BitArray(128)
            self.assertEqual(strategy.put(42, 7, raw), strategy.put(42, 7, facade))
            self.assertEqual(raw.tobytes(), facade.tobytes())
            self.assertTrue(strategy.might_contain(42, 7, raw))
            self.assertFalse(strategy.might_contain(-999, 7, raw))

    def test_nonfinite_and_oversized_sizing(self):
        for rate in (float("nan"), float("inf"), -float("inf")):
            with self.assertRaises(ValueError):
                BloomFilter(10, rate)
        with self.assertRaises(TypeError):
            BloomFilter(1.5, 0.01)
        with self.assertRaises(ValueError):
            BloomFilter(10**1000, 0.01)
        # Fits in a float, but sizing arithmetic overflows to infinity.
        with self.assertRaisesRegex(ValueError, "sizing exceeds supported range"):
            BloomFilter(10**308, 0.01)
        with self.assertRaises(TypeError):
            BloomFilter.loads(BloomFilter(1, 0.01).dumps(), max_num_bits=64.5)

    def test_misbehaving_streams_are_rejected(self):
        bf = BloomFilter(1, 0.01)

        class OverRead(io.BytesIO):
            def read(self, size=-1):
                return b"x" * (size + 1)

        with self.assertRaises(OSError):
            BloomFilter.read_from(OverRead())
        for returned in (1000000, 0, None, 1.5, "1"):
            stream = io.BytesIO()
            with patch.object(stream, "write", return_value=returned):
                with self.assertRaises(OSError):
                    bf.write_to(stream)

    def test_large_short_stream_roundtrip_and_trailer(self):
        class ShortStream(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 3))

            def write(self, data):
                return super().write(data[:3])

        for backend in BACKENDS:
            bf = BloomFilter(60000, 0.01, backend=backend)
            bf.put("large-stream")
            output = ShortStream()
            bf.write_to(output)
            source = ShortStream(output.getvalue() + b"trailer")
            loaded = BloomFilter.read_from(source, backend=backend)
            self.assertEqual(bf, loaded)
            self.assertEqual(source.tell(), bf.serialized_size())
            self.assertEqual(source.getvalue()[source.tell() :], b"trailer")

    def test_import_never_imports_native_packages(self):
        script = """
import builtins
original=builtins.__import__
def guarded(name,*args,**kwargs):
    if name.split('.')[0] in ('bitarray','mmh3'):
        raise AssertionError('native import: '+name)
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from bloomfilter import BloomFilter
bf=BloomFilter(100,.01);bf.put('hello')
assert 'hello' in BloomFilter.loads(bf.dumps())
"""
        subprocess.run([sys.executable, "-S", "-c", script], check=True)
