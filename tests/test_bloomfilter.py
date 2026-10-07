import random
import unittest
from unittest.mock import patch

from bitarray import bitarray
from bloomfilter import (
    BYTE_ARRAY_FUNNEL,
    INTEGER_FUNNEL,
    LONG_FUNNEL,
    UTF8_STRING_FUNNEL,
    BloomFilter,
)
from bloomfilter.bloomfilter_strategy import MURMUR128_MITZ_32, MURMUR128_MITZ_64
from tests import read_data


class BloomFilterTest(unittest.TestCase):
    def test_num_of_bits(self) -> None:
        test_cases = [(500, 0.01, 4792), (500, 0.0, 774727), (10, 0.01, 95)]
        for case in test_cases:
            num_bits = BloomFilter.num_of_bits(case[0], case[1])
            self.assertEqual(
                num_bits, case[2], f"Expected {case[2]} bits, but got {num_bits}"
            )

    def test_num_of_hash_functions(self) -> None:
        test_cases = [(500, 4792, 7), (500, 774727, 1074)]
        for case in test_cases:
            num_hash_functions = BloomFilter.num_of_hash_functions(case[0], case[1])
            self.assertEqual(
                num_hash_functions,
                case[2],
                f"Expected {case[2]} hash functions, but got {num_hash_functions}",
            )

    def test_basic_functionality(self) -> None:
        bloom_filter = BloomFilter(10000000, 0.001)
        for i in range(200):
            bloom_filter.put(i)

        for i in range(200):
            self.assertTrue(
                bloom_filter.might_contain(i),
                f"Number {i} is expected to be in bloomfilter",
            )
        for i in range(200, 500):
            self.assertFalse(
                bloom_filter.might_contain(i),
                f"Number {i} is NOT expected to be in bloomfilter",
            )

        words = ["hello", "world", "bloom", "filter"]
        for word in words:
            bloom_filter.put(word)

        for word in words:
            self.assertTrue(
                word in bloom_filter, f"Word '{word}' is expected to be in bloomfilter"
            )
        self.assertFalse(
            "not_exist" in bloom_filter,
            "Word 'not_exist' is expected to be in bloomfilter",
        )

    def test_signed_integer_keys(self) -> None:
        keys = [-1, -(2**31), -(2**31) - 1, -(2**63)]
        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            with self.subTest(strategy=strategy):
                bloom_filter = BloomFilter(100, 0.01, strategy)
                for key in keys:
                    bloom_filter.put(key)
                    self.assertTrue(bloom_filter.might_contain(key))

    def test_rejects_invalid_keys(self) -> None:
        bloom_filter = BloomFilter(100, 0.01)
        for key in (-(2**63) - 1, 2**63):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "signed 64-bit"):
                    bloom_filter.put(key)
                with self.assertRaisesRegex(ValueError, "signed 64-bit"):
                    bloom_filter.might_contain(key)

        with self.assertRaisesRegex(TypeError, "integers or strings"):
            bloom_filter.put(1.5)  # type: ignore[arg-type]

    def test_dumps(self) -> None:
        bloom_filter = BloomFilter(300, 0.0001, MURMUR128_MITZ_32)
        for i in range(100):
            bloom_filter.put(i)
        byte_array = bloom_filter.dumps()
        new_filter = BloomFilter.loads(byte_array)

        self.assertEqual(
            new_filter.num_hash_functions,
            bloom_filter.num_hash_functions,
            "New filter's num of hash functions is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.strategy,
            bloom_filter.strategy,
            "New filter's strategy is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.data,
            bloom_filter.data,
            "New filter's data is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.dumps(),
            byte_array,
            "New filter's dump is expected to be the same as old filter's",
        )

    def test_loads_rejects_invalid_serialized_state(self) -> None:
        bloom_filter = BloomFilter(100, 0.01)
        serialized = bloom_filter.dumps()

        invalid_payloads = [
            b"",
            bytes([serialized[0], 0]) + serialized[2:],
            bytes([serialized[0], serialized[1]]) + bytes(4),
            serialized[:-1],
            serialized + b"unexpected",
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    BloomFilter.loads(payload)

    def test_rejects_oversized_filters(self) -> None:
        with self.assertRaisesRegex(ValueError, "maximum"):
            BloomFilter(1_000_000_000, 0.01)

        oversized_word_count = BloomFilter.MAX_NUM_BITS // 64 + 1
        oversized_dump = bytes([1, 1]) + oversized_word_count.to_bytes(
            4, byteorder="big"
        )
        with self.assertRaisesRegex(ValueError, "maximum"):
            BloomFilter.loads(oversized_dump)

    def test_rejects_unserializable_hash_function_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash functions"):
            BloomFilter(1, 5e-324)

    def test_setup_rejects_invalid_state(self) -> None:
        bloom_filter = BloomFilter(100, 0.01)

        with self.assertRaisesRegex(ValueError, "hash functions"):
            bloom_filter.setup(0, bitarray(64), MURMUR128_MITZ_64)
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            bloom_filter.setup(1, bitarray(), MURMUR128_MITZ_64)
        with self.assertRaisesRegex(ValueError, "multiple of 64"):
            bloom_filter.setup(1, bitarray(65), MURMUR128_MITZ_64)
        with patch.object(BloomFilter, "MAX_NUM_BITS", 64):
            with self.assertRaisesRegex(ValueError, "maximum"):
                bloom_filter.setup(1, bitarray(128), MURMUR128_MITZ_64)

    def test_guava_compatibility(self) -> None:
        bloom_filter = BloomFilter.loads(
            read_data("500_0_01_0_to_99_test.out"), funnel=INTEGER_FUNNEL
        )
        num_bits = BloomFilter.num_of_bits(500, 0.01)
        num_hash_functions = BloomFilter.num_of_hash_functions(500, num_bits)
        self.assertEqual(
            bloom_filter.num_hash_functions,
            num_hash_functions,
            f"Bloomfilter's num of hash functions is expected to equal to {num_hash_functions}",
        )
        for i in range(100):
            self.assertTrue(
                bloom_filter.might_contain(i),
                f"Number {i} is expected to be in bloomfilter",
            )

        bloom_filter = BloomFilter.loads(
            read_data("100_0_001_0_to_49_test.out"), funnel=INTEGER_FUNNEL
        )
        num_bits = BloomFilter.num_of_bits(100, 0.001)
        num_hash_functions = BloomFilter.num_of_hash_functions(100, num_bits)
        self.assertEqual(
            bloom_filter.num_hash_functions,
            num_hash_functions,
            f"Bloomfilter's num of hash functions is expected to equal to {num_hash_functions}",
        )
        for i in range(50):
            self.assertTrue(
                bloom_filter.might_contain(i),
                f"Number {i} is expected to be in bloomfilter",
            )

    def test_guava_murmur128_mitz_32_vector(self) -> None:
        """Exercise signed int overflow using a fixed Guava-compatible vector."""
        bloom_filter = BloomFilter(1, 0.01, MURMUR128_MITZ_32, funnel=INTEGER_FUNNEL)

        bloom_filter.put(0)

        self.assertEqual(bloom_filter.dumps().hex(), "0006000000010045004000280000")

    def test_guava_funnel_vectors(self) -> None:
        vectors = [
            (
                MURMUR128_MITZ_32,
                INTEGER_FUNNEL,
                0,
                "0006000000010045004000280000",
            ),
            (
                MURMUR128_MITZ_32,
                LONG_FUNNEL,
                0,
                "0006000000012201048200000000",
            ),
            (
                MURMUR128_MITZ_32,
                UTF8_STRING_FUNNEL,
                "雪",
                "0006000000010104000410004040",
            ),
            (
                MURMUR128_MITZ_32,
                BYTE_ARRAY_FUNNEL,
                b"abc\x00",
                "0006000000010001000100800181",
            ),
            (
                MURMUR128_MITZ_64,
                INTEGER_FUNNEL,
                0,
                "0106000000011002200040008001",
            ),
            (
                MURMUR128_MITZ_64,
                LONG_FUNNEL,
                0,
                "0106000000010000802020080802",
            ),
            (
                MURMUR128_MITZ_64,
                UTF8_STRING_FUNNEL,
                "雪",
                "0106000000018080808000808000",
            ),
            (
                MURMUR128_MITZ_64,
                BYTE_ARRAY_FUNNEL,
                b"abc\x00",
                "0106000000010100408020080004",
            ),
        ]

        for strategy, funnel, value, expected_hex in vectors:
            with self.subTest(strategy=strategy, funnel=funnel):
                bloom_filter = BloomFilter(1, 0.01, strategy, funnel=funnel)
                bloom_filter.put(value)
                self.assertEqual(bloom_filter.dumps().hex(), expected_hex)

                loaded = BloomFilter.loads(bytes.fromhex(expected_hex), funnel=funnel)
                self.assertTrue(loaded.might_contain(value))
                self.assertEqual(loaded.dumps().hex(), expected_hex)

    def test_integer_funnel_width_is_fixed(self) -> None:
        int_filter = BloomFilter(100, 0.01, funnel=INTEGER_FUNNEL)
        long_filter = BloomFilter(100, 0.01, funnel=LONG_FUNNEL)

        int_filter.put(1)
        long_filter.put(1)

        self.assertNotEqual(int_filter.data, long_filter.data)
        self.assertTrue(int_filter.might_contain(1))
        self.assertTrue(long_filter.might_contain(1))

    def test_explicit_integer_funnel_boundaries(self) -> None:
        cases = [
            (INTEGER_FUNNEL, [-(2**31), -1, 0, 2**31 - 1]),
            (LONG_FUNNEL, [-(2**63), -(2**31) - 1, -1, 0, 2**31, 2**63 - 1]),
        ]

        for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
            for funnel, values in cases:
                with self.subTest(strategy=strategy, funnel=funnel):
                    bloom_filter = BloomFilter(100, 0.01, strategy, funnel=funnel)
                    for value in values:
                        bloom_filter.put(value)
                    for value in values:
                        self.assertTrue(bloom_filter.might_contain(value))

    def test_funnel_type_and_range_validation(self) -> None:
        cases = [
            (INTEGER_FUNNEL, 2**31, ValueError),
            (INTEGER_FUNNEL, "1", TypeError),
            (LONG_FUNNEL, 2**63, ValueError),
            (LONG_FUNNEL, "1", TypeError),
            (UTF8_STRING_FUNNEL, b"text", TypeError),
            (BYTE_ARRAY_FUNNEL, "text", TypeError),
        ]

        for funnel, value, error in cases:
            with self.subTest(funnel=funnel, value=value):
                bloom_filter = BloomFilter(10, 0.01, funnel=funnel)
                with self.assertRaises(error):
                    bloom_filter.put(value)

    def test_dumps_to_hex(self) -> None:
        bloom_filter = BloomFilter(500, 0.0001, MURMUR128_MITZ_32)
        for _ in range(100):
            bloom_filter.put(random.randint(100000000, 10000000000))
        hex_string = bloom_filter.dumps_to_hex()
        new_filter = BloomFilter.loads_from_hex(hex_string)

        self.assertEqual(
            new_filter.num_hash_functions,
            bloom_filter.num_hash_functions,
            "New filter's num of hash functions is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.strategy,
            bloom_filter.strategy,
            "New filter's strategy is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.data,
            bloom_filter.data,
            "New filter's data is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.dumps_to_hex(),
            hex_string,
            "New filter's dump is expected to be the same as old filter's",
        )

    def test_dumps_to_base64(self) -> None:
        bloom_filter = BloomFilter(500, 0.0001, MURMUR128_MITZ_32)
        for _ in range(100):
            bloom_filter.put(random.randint(100000000, 10000000000))
        base64_encoded = bloom_filter.dumps_to_base64()
        new_filter = BloomFilter.loads_from_base64(base64_encoded)

        self.assertEqual(
            new_filter.num_hash_functions,
            bloom_filter.num_hash_functions,
            "New filter's num of hash functions is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.strategy,
            bloom_filter.strategy,
            "New filter's strategy is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.data,
            bloom_filter.data,
            "New filter's data is expected to be the same as old filter's",
        )
        self.assertEqual(
            new_filter.dumps_to_base64(),
            base64_encoded,
            "New filter's dump is expected to be the same as old filter's",
        )

    def test_loads_from_base64_rejects_invalid_encoding(self) -> None:
        bloom_filter = BloomFilter(100, 0.01)
        malformed_base64 = bloom_filter.dumps_to_base64() + b"!"

        with self.assertRaisesRegex(ValueError, "Invalid Base64"):
            BloomFilter.loads_from_base64(malformed_base64)
