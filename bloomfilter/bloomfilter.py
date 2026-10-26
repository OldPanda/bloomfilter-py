import base64
import binascii
import io
import math
import operator
import typing

from bloomfilter._bitarray import BitArray, CHUNK_BYTES, validate_backend, _REVERSE
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
        *,
        backend: str = "python",
    ) -> None:
        backend = validate_backend(backend)
        expected_insertions = operator.index(expected_insertions)
        if not math.isfinite(err_rate):
            raise ValueError("Error rate must be finite")
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
            ((num_bits + self._BITS_PER_DATA_WORD - 1) // self._BITS_PER_DATA_WORD)
            * self._BITS_PER_DATA_WORD,
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
        data = BitArray(allocated_bits, backend=backend)
        self.setup(num_hash_functions, data, strategy, funnel)

    @property
    def backend(self) -> str:
        """Selected backend; never inferred from installed packages."""
        return self.data.backend

    def setup(
        self,
        num_hash_functions: int,
        data: BitArray,
        strategy: typing.Type[Strategy],
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> None:
        num_hash_functions = operator.index(num_hash_functions)
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
        if not isinstance(data, BitArray):
            # Legacy setup accepted bitarray.bitarray. Import it only for this
            # explicit compatibility path; normalize endian and take ownership.
            try:
                from importlib import import_module

                factory = import_module("bitarray").bitarray
            except ImportError as exc:
                raise TypeError("data must be a bloomfilter.BitArray") from exc
            if not isinstance(data, factory):
                raise TypeError("data must be a BitArray or bitarray.bitarray")
            normalized = BitArray(len(data))
            endian = data.endian
            if callable(endian):
                endian = endian()
            for start in range(0, len(data), CHUNK_BYTES * 8):
                block = data[start : start + CHUNK_BYTES * 8].tobytes()
                if endian == "little":
                    block = block.translate(_REVERSE)
                normalized._set_bytes(start // 8, block)
            data = normalized
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
        *,
        backend: str = "python",
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
        _, _, expected_length, _ = cls._parse_header(
            array[: cls._SERIALIZED_HEADER_SIZE], max_num_bits
        )
        if len(array) != expected_length:
            raise ValueError(
                f"Invalid serialized BloomFilter length: expected "
                f"{expected_length} bytes, got {len(array)}"
            )
        return cls.read_from(io.BytesIO(array), funnel, max_num_bits, backend=backend)

    @classmethod
    def _parse_header(
        cls, array: bytes, max_num_bits: typing.Optional[int]
    ) -> typing.Tuple[typing.Type[Strategy], int, int, int]:
        if max_num_bits is None:
            max_num_bits = cls.MAX_NUM_BITS
        max_num_bits = operator.index(max_num_bits)
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

        data_word_count = int.from_bytes(array[2:6], byteorder="big", signed=True)
        if data_word_count <= 0:
            raise ValueError("Serialized BloomFilter word count must be positive")
        bit_length = data_word_count * cls._BITS_PER_DATA_WORD
        if bit_length > max_num_bits:
            raise ValueError(
                f"Serialized BloomFilter contains {bit_length} bits; "
                f"maximum is {max_num_bits}"
            )

        expected_length = (
            cls._SERIALIZED_HEADER_SIZE + data_word_count * cls._BYTES_PER_DATA_WORD
        )
        return strategy, num_hash_functions, expected_length, max_num_bits

    @staticmethod
    def _read_exact(stream: typing.BinaryIO, size: int) -> bytes:
        result = bytearray()
        while len(result) < size:
            chunk = stream.read(size - len(result))
            if not chunk:
                raise ValueError("Truncated serialized BloomFilter stream")
            if len(chunk) > size - len(result):
                raise OSError("BloomFilter stream read exceeded requested size")
            result.extend(chunk)
        return bytes(result)

    @classmethod
    def read_from(
        cls,
        stream: typing.BinaryIO,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
        *,
        backend: str = "python",
    ) -> "BloomFilter":
        """Read one Guava compact filter, leaving trailing stream data unread.

        Validate the header and allocation limit before reading the payload.
        The caller retains ownership of the stream.
        """
        backend = validate_backend(backend)
        header = cls._read_exact(stream, cls._SERIALIZED_HEADER_SIZE)
        strategy, num_hash_functions, expected_length, limit = cls._parse_header(
            header, max_num_bits
        )

        payload_size = expected_length - cls._SERIALIZED_HEADER_SIZE
        data = BitArray(payload_size * 8, backend=backend)
        for offset in range(0, payload_size, CHUNK_BYTES):
            block = cls._read_exact(stream, min(CHUNK_BYTES, payload_size - offset))
            data.set_guava_chunk(offset, block)
        instance = cls.__new__(cls)
        instance.max_num_bits = limit
        instance.setup(num_hash_functions, data, strategy, funnel)
        return instance

    @classmethod
    def loads_from_hex(
        cls,
        hex_str: str,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
        *,
        backend: str = "python",
    ) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from hex string.

        :param hex_str: BloomFilter dumped hex string.
        :type hex_str: str
        """
        # fromhex() reserves space from the raw input length, including
        # whitespace. Decode bounded chunks so padding cannot bypass the cap.
        data = bytearray()
        pending = ""
        expected_length = None
        whitespace = " \t\n\r\v\f"
        for offset in range(0, len(hex_str), 8192):
            chunk = pending + hex_str[offset : offset + 8192]
            pending = ""
            digits = len(chunk) - sum(chunk.count(char) for char in whitespace)
            if digits % 2:
                # A chunk may split a byte, but whitespace between its two
                # hex digits is invalid, just as with bytes.fromhex().
                if chunk[-1] in whitespace:
                    raise ValueError("Whitespace inside a hexadecimal byte")
                pending, chunk = chunk[-1], chunk[:-1]
            decoded = bytes.fromhex(chunk)
            if (
                expected_length is None
                and len(data) + len(decoded) >= cls._SERIALIZED_HEADER_SIZE
            ):
                header = bytes(data) + decoded[: cls._SERIALIZED_HEADER_SIZE]
                _, _, expected_length, _ = cls._parse_header(
                    header[: cls._SERIALIZED_HEADER_SIZE], max_num_bits
                )
            if (
                expected_length is not None
                and len(data) + len(decoded) > expected_length
            ):
                raise ValueError("Serialized BloomFilter contains excess data")
            data.extend(decoded)
        if pending:
            raise ValueError("Incomplete hexadecimal byte")
        return cls.loads(
            bytes(data), funnel=funnel, max_num_bits=max_num_bits, backend=backend
        )

    @classmethod
    def loads_from_base64(
        cls,
        base64_encoded_bytes: bytes,
        funnel: Funnel = LEGACY_FUNNEL,
        max_num_bits: typing.Optional[int] = None,
        *,
        backend: str = "python",
    ) -> "BloomFilter":
        """
        Initialize Bloomfilter instance from base64 encoded bytes.

        :param base64_encoded_bytes: BloomFilter dumped bytes encoded in base64.
        :type base64_encoded_bytes: bytes
        """
        try:
            limit = cls.MAX_NUM_BITS if max_num_bits is None else max_num_bits
            if limit < 0:
                raise ValueError("Maximum number of bits must be >= 0")
            encoded: typing.Union[str, bytes, bytearray, memoryview]
            if isinstance(base64_encoded_bytes, (str, bytes, bytearray)):
                encoded = base64_encoded_bytes
            else:
                # The Base64 decoder also accepts other buffer-protocol types.
                # Inspect their byte length without materializing the buffer.
                encoded = memoryview(base64_encoded_bytes)
            encoded_length = (
                encoded.nbytes if isinstance(encoded, memoryview) else len(encoded)
            )
            max_length = (
                cls._SERIALIZED_HEADER_SIZE
                + (limit // cls._BITS_PER_DATA_WORD) * cls._BYTES_PER_DATA_WORD
            )
            if encoded_length > 4 * ((max_length + 2) // 3):
                raise ValueError("Encoded BloomFilter exceeds the allocation limit")
            # Slice buffer inputs by bytes, not dimensions or element size.
            # A non-contiguous view can only be copied after the byte-size cap.
            if isinstance(encoded, memoryview):
                if encoded.c_contiguous:
                    encoded = encoded.cast("B")
                else:
                    encoded = encoded.tobytes()
            # Eight encoded characters hold the six-byte header. Validate its
            # size before allowing the decoder to allocate the full payload.
            header = base64.b64decode(encoded[:8], validate=True)
            _, _, expected_length, _ = cls._parse_header(header, max_num_bits)
            if encoded_length > 4 * ((expected_length + 2) // 3):
                raise ValueError("Serialized BloomFilter contains excess data")
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid Base64-encoded BloomFilter") from exc
        return cls.loads(
            decoded, funnel=funnel, max_num_bits=max_num_bits, backend=backend
        )

    def dumps(self) -> bytes:
        """
        Serialize BloomFilter instance to bytes.
        """
        stream = io.BytesIO()
        self.write_to(stream)
        return stream.getvalue()

    def write_to(self, stream: typing.BinaryIO) -> None:
        """Write Guava's compact format without closing the caller's stream."""
        self.setup(self.num_hash_functions, self.data, self.strategy, self.funnel)
        result = bytearray()
        result.extend(self.strategy.ordinal().to_bytes(1, byteorder="little"))
        result.extend(self.num_hash_functions.to_bytes(1, byteorder="little"))
        result.extend(
            (len(self.data) // self._BITS_PER_DATA_WORD).to_bytes(4, byteorder="big")
        )
        self._write_exact(stream, bytes(result))
        for chunk in self.data.iter_guava_chunks():
            self._write_exact(stream, chunk)

    @staticmethod
    def _write_exact(stream: typing.BinaryIO, data: bytes) -> None:
        offset = 0
        view = memoryview(data)
        while offset < len(view):
            written = stream.write(view[offset:])
            try:
                count = operator.index(written)
            except TypeError as exc:
                raise OSError(
                    "BloomFilter stream write returned an invalid count"
                ) from exc
            if count <= 0 or count > len(view) - offset:
                raise OSError("BloomFilter stream write made no valid progress")
            offset += count

    def serialized_size(self) -> int:
        """Return the compact serialized byte size without allocating a dump."""
        return self._SERIALIZED_HEADER_SIZE + len(self.data) // 8

    def copy(self) -> "BloomFilter":
        """Copy the bit array; the funnel and stateless strategy are shared."""
        instance = type(self).__new__(type(self))
        instance.max_num_bits = getattr(self, "max_num_bits", self.MAX_NUM_BITS)
        instance.setup(
            self.num_hash_functions, self.data.copy(), self.strategy, self.funnel
        )
        return instance

    def expected_fpp(self) -> float:
        """Estimate false-positive probability from the current bit occupancy."""
        return float((self.data.count() / len(self.data)) ** self.num_hash_functions)

    def approximate_element_count(self) -> int:
        """Estimate distinct insertions, using Guava's HALF_UP rounding.

        Raise OverflowError when saturated or outside Java's signed-long range,
        corresponding to Guava's ArithmeticException.
        """
        fraction = self.data.count() / len(self.data)
        if fraction == 1.0:
            raise OverflowError("Cannot estimate element count for a saturated filter")
        estimate = -math.log1p(-fraction) * len(self.data) / self.num_hash_functions
        if estimate >= 2**63:
            raise OverflowError("Element count exceeds the Java signed-long range")
        integer = math.floor(estimate)
        return integer + int(estimate - integer >= 0.5)

    def is_compatible(self, other: "BloomFilter") -> bool:
        """Check merge compatibility, excluding the same instance as Guava does."""
        if not isinstance(other, BloomFilter):
            raise TypeError("Expected a BloomFilter")
        return (
            self is not other
            and self.num_hash_functions == other.num_hash_functions
            and len(self.data) == len(other.data)
            and self.strategy == other.strategy
            and self.funnel == other.funnel
        )

    def put_all(self, other: "BloomFilter") -> None:
        """Merge a compatible filter into this one, preserving the source."""
        if not self.is_compatible(other):
            raise ValueError("Cannot combine incompatible BloomFilters")
        self.data |= other.data

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BloomFilter):
            return NotImplemented
        return (
            self.num_hash_functions == other.num_hash_functions
            and self.strategy == other.strategy
            and self.funnel == other.funnel
            and self.data == other.data
        )

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
        try:
            result = (
                -expected_insertions * math.log(err_rate) / (math.log(2) * math.log(2))
            )
        except OverflowError as exc:
            raise ValueError("BloomFilter sizing exceeds supported range") from exc
        if not math.isfinite(result):
            raise ValueError("BloomFilter sizing exceeds supported range")
        return int(result)

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
        Return ``True`` if the element might be present, or ``False`` if absent.
        """
        return self.strategy.might_contain(
            key, self.num_hash_functions, self.data, self.funnel
        )

    def __contains__(self, key: typing.Any) -> bool:
        return self.might_contain(key)
