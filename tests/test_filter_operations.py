import io
import unittest
from unittest.mock import patch

from bloomfilter import BloomFilter, INTEGER_FUNNEL, LONG_FUNNEL, StringFunnel
from bloomfilter.bloomfilter_strategy import MURMUR128_MITZ_32, MURMUR128_MITZ_64


class ShortStream(io.BytesIO):
    def read(self, size=-1):
        return super().read(min(size, 3))

    def write(self, data):
        return super().write(data[:3])


class FilterOperationsTest(unittest.TestCase):
    def test_zero_expected_insertions_and_trusted_copy_limit(self):
        empty = BloomFilter(0, 0.01, funnel=INTEGER_FUNNEL)
        self.assertEqual(empty, BloomFilter(1, 0.01, funnel=INTEGER_FUNNEL))
        serialized = bytes([1, 7]) + (2).to_bytes(4, "big") + bytes(16)
        with patch.object(BloomFilter, "MAX_NUM_BITS", 64):
            loaded = BloomFilter.read_from(
                io.BytesIO(serialized), INTEGER_FUNNEL, max_num_bits=128
            )
            copied = loaded.copy()
            self.assertEqual(copied.max_num_bits, 128)
            self.assertEqual(copied.dumps(), serialized)
            copied.put(42)
            loaded.put_all(copied)
            self.assertIn(42, loaded)
            self.assertEqual(loaded.dumps(), copied.dumps())

    def test_copy_and_merge_loaded_filters(self):
        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            with self.subTest(strategy=strategy):
                original = BloomFilter(100, 0.01, strategy, INTEGER_FUNNEL)
                for key in range(20):
                    original.put(key)
                loaded = BloomFilter.loads(original.dumps(), INTEGER_FUNNEL)
                copied = loaded.copy()
                self.assertEqual(copied, loaded)
                self.assertIsNot(copied.data, loaded.data)
                self.assertIs(copied.funnel, loaded.funnel)
                snapshot = loaded.dumps()
                copied.put(1000)
                self.assertNotEqual(copied, loaded)
                self.assertEqual(loaded.dumps(), snapshot)
                self.assertTrue(loaded.is_compatible(copied))
                copied_snapshot = copied.dumps()
                loaded.put_all(copied)
                self.assertEqual(loaded.dumps(), copied_snapshot)
                self.assertEqual(copied.dumps(), copied_snapshot)
                for key in (*range(20), 1000):
                    self.assertIn(key, loaded)

    def test_incompatible_merges_are_atomic(self):
        base = BloomFilter(100, 0.01, funnel=INTEGER_FUNNEL)
        base.put(42)
        changed_hash_count = base.copy()
        changed_hash_count.num_hash_functions += 1
        cases = (
            base,
            changed_hash_count,
            BloomFilter(200, 0.01, funnel=INTEGER_FUNNEL),
            BloomFilter(100, 0.01, MURMUR128_MITZ_32, INTEGER_FUNNEL),
            BloomFilter(100, 0.01, funnel=LONG_FUNNEL),
        )
        snapshot = base.dumps()
        for other in cases:
            with self.subTest(other=other):
                self.assertFalse(base.is_compatible(other))
                with self.assertRaises(ValueError):
                    base.put_all(other)
                self.assertEqual(base.dumps(), snapshot)
                if other is not base:
                    self.assertNotEqual(base, other)
        for other in (None, object()):
            with self.assertRaises(TypeError):
                base.is_compatible(other)
            with self.assertRaises(TypeError):
                base.put_all(other)
            self.assertNotEqual(base, other)

    def test_equal_charset_funnels_are_compatible(self):
        left = BloomFilter(100, 0.01, funnel=StringFunnel("UTF8"))
        right = BloomFilter(100, 0.01, funnel=StringFunnel("utf-8"))
        self.assertEqual(left, right)
        self.assertTrue(left.is_compatible(right))
        right.put("雪")
        left.put_all(right)
        self.assertIn("雪", left)
        with self.assertRaises(TypeError):
            hash(left)  # Mutable filters must not be usable as dictionary keys.

    def test_statistics(self):
        bloom_filter = BloomFilter(1000, 0.01, funnel=INTEGER_FUNNEL)
        self.assertEqual(bloom_filter.expected_fpp(), 0.0)
        self.assertEqual(bloom_filter.approximate_element_count(), 0)
        for value in range(100):
            bloom_filter.put(value)
        self.assertLess(bloom_filter.expected_fpp(), 0.01)
        self.assertLessEqual(abs(bloom_filter.approximate_element_count() - 100), 5)
        loaded = BloomFilter.loads(bloom_filter.dumps(), INTEGER_FUNNEL)
        self.assertEqual(loaded.expected_fpp(), bloom_filter.expected_fpp())
        self.assertEqual(
            loaded.approximate_element_count(), bloom_filter.approximate_element_count()
        )
        with patch(
            "bloomfilter.bloomfilter.math.log1p", return_value=-2.5 / len(loaded.data)
        ):
            loaded.num_hash_functions = 1
            self.assertEqual(loaded.approximate_element_count(), 3)
        with patch("bloomfilter.bloomfilter.math.log1p", return_value=-float(2**63)):
            with self.assertRaises(OverflowError):
                loaded.approximate_element_count()
        loaded.data.setall(1)
        self.assertEqual(loaded.expected_fpp(), 1.0)
        with self.assertRaises(OverflowError):
            loaded.approximate_element_count()

    def test_streams_and_serialized_size(self):
        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            with self.subTest(strategy=strategy):
                bloom_filter = BloomFilter(100, 0.01, strategy, INTEGER_FUNNEL)
                bloom_filter.put(42)
                serialized = bloom_filter.dumps()
                self.assertEqual(bloom_filter.serialized_size(), len(serialized))
                output = ShortStream()
                bloom_filter.write_to(output)
                self.assertFalse(output.closed)
                self.assertEqual(output.getvalue(), serialized)
                stream = ShortStream(serialized + serialized + b"trailer")
                for _ in range(2):
                    loaded = BloomFilter.read_from(stream, INTEGER_FUNNEL)
                    self.assertEqual(loaded, bloom_filter)
                    self.assertIn(42, loaded)
                self.assertEqual(stream.tell(), 2 * len(serialized))
                self.assertFalse(stream.closed)
                with patch.object(bloom_filter, "dumps", side_effect=AssertionError):
                    self.assertEqual(bloom_filter.serialized_size(), len(serialized))

    def test_stream_failures_and_allocation_limit(self):
        serialized = BloomFilter(100, 0.01).dumps()
        negative_word_count = bytes([1, 7]) + bytes([255]) * 4
        stream = io.BytesIO(negative_word_count + b"unread")
        with self.assertRaisesRegex(ValueError, "word count must be positive"):
            BloomFilter.read_from(stream, max_num_bits=2**40)
        self.assertEqual(stream.tell(), 6)
        for size in (0, 5, 6, len(serialized) - 1):
            with self.subTest(size=size):
                with self.assertRaisesRegex(ValueError, "Truncated"):
                    BloomFilter.read_from(ShortStream(serialized[:size]))
        for limit in (-1, 64):
            stream = io.BytesIO(serialized)
            with self.assertRaises(ValueError):
                BloomFilter.read_from(stream, max_num_bits=limit)
            self.assertEqual(stream.tell(), 6)  # Reject before consuming payload.
        stream = io.BytesIO(serialized)
        loaded = BloomFilter.read_from(stream, max_num_bits=len(serialized) * 8)
        self.assertEqual(loaded.copy().max_num_bits, len(serialized) * 8)
        self.assertEqual(loaded.copy().dumps(), serialized)
        for result in (0, None):
            with patch.object(stream, "write", return_value=result):
                with self.assertRaises(OSError):
                    loaded.write_to(stream)
        with patch.object(stream, "write", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                loaded.write_to(stream)
        with patch.object(stream, "read", side_effect=OSError("read failure")):
            with self.assertRaisesRegex(OSError, "read failure"):
                BloomFilter.read_from(stream)
