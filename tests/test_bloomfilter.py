import random
import unittest

from bloomfilter import BloomFilter
from bloomfilter.bloomfilter_strategy import MURMUR128_MITZ_32
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

    def test_guava_compatibility(self) -> None:
        bloom_filter = BloomFilter.loads(read_data("500_0_01_0_to_99_test.out"))
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

        bloom_filter = BloomFilter.loads(read_data("100_0_001_0_to_49_test.out"))
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
