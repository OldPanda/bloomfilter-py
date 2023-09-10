import base64
import math
import typing

from bitarray import bitarray
from bloomfilter.bloomfilter_strategy import (
    Strategy,
    MURMUR128_MITZ_32,
    MURMUR128_MITZ_64,
)


STRATEGIES: typing.List[typing.Type[Strategy]] = [MURMUR128_MITZ_32, MURMUR128_MITZ_64]


class BloomFilter:
    """
    Bloomfilter class.

    :param expected_insertions: Number of elements expected to be inserted into Bloomfilter. Must be non-negative number.
    :type expected_insertions: int
    :param err_rate: Error rate of existance checking. Must be between 0.0 and 1.0, both exclusive.
    :type err_rate: float
    :param strategy: Hashing strategy.
    :type strategy: :class:`~bloomfilter.MURMUR128_MITZ_32` or :class:`~bloomfilter.MURMUR128_MITZ_64`. Will use :class:`~bloomfilter.MURMUR128_MITZ_64` by default.
    """

    def __init__(
        self,
        expected_insertions: int,
        err_rate: float,
        strategy: typing.Type[Strategy] = MURMUR128_MITZ_64,
    ):
        if err_rate <= 0:
            raise ValueError("Error rate must be > 0.0")
        if err_rate >= 1:
            raise ValueError("Error rate must be < 1.0")
        if expected_insertions < 0:
            raise ValueError("Expected insertions must be >= 0")
        if expected_insertions == 0:
            expected_insertions = 1

        num_bits = self.num_of_bits(expected_insertions, err_rate)
        num_hash_functions = self.num_of_hash_functions(expected_insertions, num_bits)
        data = bitarray("0") * math.ceil(num_bits / 64) * 64
        self.setup(num_hash_functions, data, strategy)

    def setup(
        self, num_hash_functions: int, data: bitarray, strategy: typing.Type[Strategy]
    ) -> None:
        self.num_hash_functions = num_hash_functions
        self.data = data
        self.strategy = strategy

    @classmethod
    def loads(cls, array: bytes) -> "BloomFilter":
        """
        Initialize Bloomfilter instance given dump bytes.

        :param array: BloomFilter dumped bytes.
        :type array: bytes
        """
        strategy_ordinal = array[0]
        if strategy_ordinal >= len(STRATEGIES):
            raise ValueError(f"Invalid strategy ordinal: {strategy_ordinal}")

        strategy = STRATEGIES[strategy_ordinal]
        num_hash_functions = array[1]
        bit_length = int.from_bytes(array[2:6], byteorder="big")
        data = bitarray()
        for i in range(0, len(array[6 : bit_length * 8 + 6]), 8):
            entry = bitarray()
            entry.frombytes(array[6 + i : 6 + i + 8])
            data += entry[::-1]
        instance = cls(0, 0.01, strategy=strategy)
        instance.setup(num_hash_functions, data, strategy)
        return instance

    @classmethod
    def loads_from_hex(cls, hex_str: str) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from hex string.

        :param hex_str: BloomFilter dumped hex string.
        :type hex_str: str
        """
        return cls.loads(bytes.fromhex(hex_str))

    @classmethod
    def loads_from_base64(cls, base64_encoded_bytes: bytes) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from base64 encoded bytes.

        :param base64_encoded_bytes: BloomFilter dumped bytes encoded in base64.
        :type base64_encoded_bytes: bytes
        """
        return cls.loads(base64.b64decode(base64_encoded_bytes))

    def dumps(self) -> bytes:
        """
        Serialize BloomFilter instance to bytes.
        """
        result = bytes()
        result += self.strategy.ordinal().to_bytes(1, byteorder="little")
        result += self.num_hash_functions.to_bytes(1, byteorder="little")
        result += math.ceil(len(self.data) / 64).to_bytes(4, byteorder="big")
        for i in range(0, len(self.data), 64):
            result += self.data[i : i + 64][::-1].tobytes()
        return result

    def dumps_to_hex(self) -> str:
        """
        Serialize BloomFilter instance to hex string.
        """
        return self.dumps().hex()

    def dumps_to_base64(self) -> bytes:
        """
        Serialize BloomFilter instance to base64 encoded bytes.
        """
        return base64.b64encode(self.dumps())

    @classmethod
    def num_of_bits(cls, expected_insertions: int, err_rate: float) -> int:
        """
        Compute the number of bits required for the Bloomfilter given expected insertions and error rate.

        See `Wikipedia <https://en.wikipedia.org/wiki/Bloom_filter#Probability_of_false_positives>`_ for the formula.

        :param expected_insertsions: Number of expected insertions into the Bloomfilter instance.
        :type expected_insertsions: int
        :param err_rate: Error rate of existance checking.
        :type err_rate: float
        """
        if err_rate == 0:
            err_rate = 2 ** (-1074)  # the same number of Double.MIN_VALUE in Java
        return int(
            -expected_insertions * math.log(err_rate) / (math.log(2) * math.log(2))
        )

    @classmethod
    def num_of_hash_functions(cls, expected_insertions: int, num_bits: int) -> int:
        """
        Compute the number of hash functions required per each element insertion.

        See `Wikipedia <https://en.wikipedia.org/wiki/Bloom_filter#Probability_of_false_positives>`_ for the formula.

        :param expected_insertsions: Number of expected insertions into the Bloomfilter instance.
        :type expected_insertsions: int
        :param num_bits: Number of bits in the Bloomfilter's bits array.
        :type num_bits: int
        """
        return max(1, round(num_bits / expected_insertions * math.log(2)))

    def put(self, key: typing.Union[int, str]) -> bool:
        """
        Put an element into the Bloomfilter.
        """
        return self.strategy.put(key, self.num_hash_functions, self.data)

    def might_contain(self, key: typing.Union[int, str]) -> bool:
        """
        Return ``True`` if given element exists in Bloomfilter. Otherwise return ``False``.
        """
        return self.strategy.might_contain(key, self.num_hash_functions, self.data)

    def __contains__(self, key: typing.Union[int, str]) -> bool:
        return self.might_contain(key)
