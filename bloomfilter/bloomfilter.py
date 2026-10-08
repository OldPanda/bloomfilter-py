import base64
import binascii
import math
import typing

from bitarray import bitarray
from bloomfilter.funnel import Funnel, LEGACY_FUNNEL
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
    :param funnel: Encoder matching the Guava Funnel used by the other side.
    :type funnel: :class:`~bloomfilter.Funnel`
    """

    # Keep allocations bounded when sizing parameters or serialized filters come
    # from an untrusted source. 2**30 bits is 128 MiB of filter data.
    MAX_NUM_BITS = 1 << 30
    MAX_NUM_HASH_FUNCTIONS = 255
    _SERIALIZED_HEADER_SIZE = 6
    _BITS_PER_DATA_WORD = 64
    _BYTES_PER_DATA_WORD = 8

    def __init__(
        self,
        expected_insertions: int,
        err_rate: float,
        strategy: typing.Type[Strategy] = MURMUR128_MITZ_64,
        funnel: Funnel = LEGACY_FUNNEL,
    ):
        if err_rate <= 0:
            raise ValueError("Error rate must be > 0.0")
        if err_rate >= 1:
            raise ValueError("Error rate must be < 1.0")
        if expected_insertions < 0:
            raise ValueError("Expected insertions must be >= 0")
        if expected_insertions == 0:
            expected_insertions = 1

        self.max_num_bits = self.MAX_NUM_BITS
        num_bits = self.num_of_bits(expected_insertions, err_rate)
        num_hash_functions = self.num_of_hash_functions_for_error_rate(err_rate)
        allocated_bits = max(
            self._BITS_PER_DATA_WORD,
            math.ceil(num_bits / self._BITS_PER_DATA_WORD) * self._BITS_PER_DATA_WORD,
        )
        if allocated_bits > self.MAX_NUM_BITS:
            raise ValueError(
                f"BloomFilter requires {allocated_bits} bits; "
                f"maximum is {self.MAX_NUM_BITS}"
            )
        if num_hash_functions > self.MAX_NUM_HASH_FUNCTIONS:
            raise ValueError(
                f"BloomFilter requires {num_hash_functions} hash functions; "
                f"maximum is {self.MAX_NUM_HASH_FUNCTIONS}"
            )
        data = bitarray(allocated_bits)
        data.setall(0)
        self.setup(num_hash_functions, data, strategy, funnel)

    def setup(
        self,
        num_hash_functions: int,
        data: bitarray,
        strategy: typing.Type[Strategy],
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> None:
        if not 1 <= num_hash_functions <= self.MAX_NUM_HASH_FUNCTIONS:
            raise ValueError(
                "Number of hash functions must be between 1 and "
                f"{self.MAX_NUM_HASH_FUNCTIONS}"
            )
        if len(data) == 0:
            raise ValueError("BloomFilter data must not be empty")
        if len(data) % self._BITS_PER_DATA_WORD != 0:
            raise ValueError(
                f"BloomFilter data length must be a multiple of "
                f"{self._BITS_PER_DATA_WORD} bits"
            )
        max_num_bits = getattr(self, "max_num_bits", self.MAX_NUM_BITS)
        if len(data) > max_num_bits:
            raise ValueError(
                f"BloomFilter data contains {len(data)} bits; "
                f"maximum is {max_num_bits}"
            )
        self.num_hash_functions = num_hash_functions
        self.data = data
        self.strategy = strategy
        self.funnel = funnel

    @classmethod
    def loads(
        cls,
        array: bytes,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
    ) -> "BloomFilter":
        """
        Initialize Bloomfilter instance given dump bytes.

        :param array: BloomFilter dumped bytes.
        :type array: bytes
        :param funnel: Encoder matching the Funnel used to populate the filter.
        :type funnel: :class:`~bloomfilter.Funnel`
        :param max_num_bits: Maximum serialized bit-array size to allocate. Uses
            :attr:`MAX_NUM_BITS` by default.
        :type max_num_bits: int or None
        """
        if max_num_bits is None:
            max_num_bits = cls.MAX_NUM_BITS
        if max_num_bits < 0:
            raise ValueError("Maximum number of bits must be >= 0")
        if len(array) < cls._SERIALIZED_HEADER_SIZE:
            raise ValueError("Serialized BloomFilter is shorter than its header")

        strategy_ordinal = array[0]
        if strategy_ordinal >= len(STRATEGIES):
            raise ValueError(f"Invalid strategy ordinal: {strategy_ordinal}")

        strategy = STRATEGIES[strategy_ordinal]
        num_hash_functions = array[1]
        if not 1 <= num_hash_functions <= cls.MAX_NUM_HASH_FUNCTIONS:
            raise ValueError(
                "Number of hash functions must be between 1 and "
                f"{cls.MAX_NUM_HASH_FUNCTIONS}"
            )

        data_word_count = int.from_bytes(array[2:6], byteorder="big")
        if data_word_count == 0:
            raise ValueError("Serialized BloomFilter data must not be empty")
        bit_length = data_word_count * cls._BITS_PER_DATA_WORD
        if bit_length > max_num_bits:
            raise ValueError(
                f"Serialized BloomFilter contains {bit_length} bits; "
                f"maximum is {max_num_bits}"
            )

        expected_length = (
            cls._SERIALIZED_HEADER_SIZE + data_word_count * cls._BYTES_PER_DATA_WORD
        )
        if len(array) != expected_length:
            raise ValueError(
                f"Invalid serialized BloomFilter length: expected "
                f"{expected_length} bytes, got {len(array)}"
            )

        data = bitarray()
        for i in range(
            cls._SERIALIZED_HEADER_SIZE,
            expected_length,
            cls._BYTES_PER_DATA_WORD,
        ):
            entry = bitarray()
            entry.frombytes(array[i : i + cls._BYTES_PER_DATA_WORD])
            data += entry[::-1]
        instance = cls(0, 0.01, strategy=strategy, funnel=funnel)
        instance.max_num_bits = max_num_bits
        instance.setup(num_hash_functions, data, strategy, funnel)
        return instance

    @classmethod
    def loads_from_hex(
        cls,
        hex_str: str,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
    ) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from hex string.

        :param hex_str: BloomFilter dumped hex string.
        :type hex_str: str
        """
        return cls.loads(
            bytes.fromhex(hex_str), funnel=funnel, max_num_bits=max_num_bits
        )

    @classmethod
    def loads_from_base64(
        cls,
        base64_encoded_bytes: bytes,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
    ) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from base64 encoded bytes.

        :param base64_encoded_bytes: BloomFilter dumped bytes encoded in base64.
        :type base64_encoded_bytes: bytes
        """
        try:
            decoded = base64.b64decode(base64_encoded_bytes, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid Base64-encoded BloomFilter") from exc
        return cls.loads(decoded, funnel=funnel, max_num_bits=max_num_bits)

    def dumps(self) -> bytes:
        """
        Serialize BloomFilter instance to bytes.
        """
        self.setup(self.num_hash_functions, self.data, self.strategy, self.funnel)
        result = bytearray()
        result.extend(self.strategy.ordinal().to_bytes(1, byteorder="little"))
        result.extend(self.num_hash_functions.to_bytes(1, byteorder="little"))
        result.extend(
            (len(self.data) // self._BITS_PER_DATA_WORD).to_bytes(4, byteorder="big")
        )
        for i in range(0, len(self.data), self._BITS_PER_DATA_WORD):
            result.extend(self.data[i : i + self._BITS_PER_DATA_WORD][::-1].tobytes())
        return bytes(result)

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
        java_rounded = math.floor(num_bits / expected_insertions * math.log(2) + 0.5)
        return max(1, java_rounded)

    @classmethod
    def num_of_hash_functions_for_error_rate(cls, err_rate: float) -> int:
        """Compute Guava's hash-function count directly from the requested FPP."""
        java_rounded = math.floor(-math.log(err_rate) / math.log(2) + 0.5)
        return max(1, java_rounded)

    def put(self, key: typing.Any) -> bool:
        """
        Put an element into the Bloomfilter.
        """
        return self.strategy.put(key, self.num_hash_functions, self.data, self.funnel)

    def might_contain(self, key: typing.Any) -> bool:
        """
        Return ``True`` if given element exists in Bloomfilter. Otherwise return ``False``.
        """
        return self.strategy.might_contain(
            key, self.num_hash_functions, self.data, self.funnel
        )

    def __contains__(self, key: typing.Any) -> bool:
        return self.might_contain(key)
