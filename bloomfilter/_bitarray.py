"""Packed bit storage shared by both explicitly selected backends.

This is a small, documented bit sequence, not the third-party bitarray API.
Logical bit zero is the high bit of byte zero. Guava reverses each 64-bit word.
Serialization, counting and merging use chunks of at most 64 KiB.
"""

from array import array
from functools import lru_cache
import importlib
import operator
from typing import Any, Callable, Iterable, Iterator, Tuple, Union, overload, cast

from bloomfilter._murmur3 import hash64

CHUNK_BYTES = 65536
_REVERSE = bytes(int(format(i, "08b")[::-1], 2) for i in range(256))
_POPCOUNT = bytes(bin(i).count("1") for i in range(256))
Hash64 = Callable[[bytes], Tuple[int, int]]


def validate_backend(backend: str) -> str:
    """Reject unknown names instead of silently changing execution mode."""
    if backend not in ("python", "native"):
        raise ValueError("backend must be 'python' or 'native'")
    if backend == "native":
        _native_modules()
    return backend


@lru_cache(maxsize=1)
def _native_modules() -> Tuple[Any, Hash64]:
    try:
        bits = importlib.import_module("bitarray").bitarray
        native_hash = importlib.import_module("mmh3").hash64
    except ImportError as exc:
        raise ImportError(
            "The native backend requires the optional dependencies; "
            "install 'bloomfilter-py[native]' or use backend='python'"
        ) from exc
    return bits, cast(Hash64, native_hash)


def _reverse_words(data: bytes) -> bytes:
    """Reverse all bits inside each word; the transform is its own inverse."""
    words = array("Q")
    words.frombytes(data.translate(_REVERSE))
    words.byteswap()
    return words.tobytes()


class BitArray:
    """Mutable packed bits with stable semantics across backends.

    Supports integer indexing, slice copies, scalar/equal-length iterable slice
    assignment, setall, count(0/1), copy, equality, |=, += and frombytes/tobytes.
    Slice assignment never resizes. frombytes and += append bits. No buffer
    protocol or other third-party bitarray methods are promised.
    """

    __slots__ = ("_size", "_storage", "_backend", "_hash64")

    def __init__(self, size: int = 0, *, backend: str = "python") -> None:
        size = operator.index(size)
        if size < 0:
            raise ValueError("Negative bit count")
        self._backend = validate_backend(backend)
        self._size = size
        self._storage: Any
        self._hash64: Hash64
        if backend == "native":
            factory, self._hash64 = _native_modules()
            self._storage = factory(size, endian="big")
            self._storage.setall(0)
        else:
            self._storage = bytearray((size + 7) // 8)
            self._hash64 = hash64

    @property
    def backend(self) -> str:
        return self._backend

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[int]:
        for i in range(self._size):
            yield self[i]

    def _index(self, index: int) -> int:
        index = operator.index(index)
        if index < 0:
            index += self._size
        if not 0 <= index < self._size:
            raise IndexError("bit index out of range")
        return index

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> "BitArray": ...

    def __getitem__(self, index: Union[int, slice]) -> Union[int, "BitArray"]:
        if isinstance(index, slice):
            start, stop, step = index.indices(self._size)
            indices = range(start, stop, step)
            result = type(self)(len(indices), backend=self.backend)
            if self.backend == "native":
                result._storage = self._storage[index]
            elif step == 1 and start % 8 == stop % 8 == 0:
                result._storage[:] = self._storage[start // 8 : max(start, stop) // 8]
            elif (
                step == -1
                and start == self._size - 1
                and stop == -1
                and self._size % 8 == 0
            ):
                result._storage[:] = self._storage[::-1].translate(_REVERSE)
            else:
                for dest, source in enumerate(indices):
                    result[dest] = self[source]
            return result
        index = self._index(index)
        if self.backend == "native":
            return int(self._storage[index])
        return int((self._storage[index >> 3] >> (7 - (index & 7))) & 1)

    def __setitem__(
        self, index: Union[int, slice], value: Union[int, Iterable[int]]
    ) -> None:
        if isinstance(index, slice):
            indices = range(*index.indices(self._size))
            if isinstance(value, int):
                bit = self._bit(value)
                for dest in indices:
                    self[dest] = bit
            else:
                # Validate fully before mutation, including a length mismatch.
                values = [self._bit(v) for v in value]
                if len(indices) != len(values):
                    raise ValueError("Slice assignment must preserve bit length")
                for dest, bit in zip(indices, values):
                    self[dest] = bit
            return
        index = self._index(index)
        bit = self._bit(value)
        if self.backend == "native":
            self._storage[index] = bit
        else:
            mask = 1 << (7 - (index & 7))
            if bit:
                self._storage[index >> 3] |= mask
            else:
                self._storage[index >> 3] &= ~mask

    @staticmethod
    def _bit(value: Any) -> int:
        bit = operator.index(value)
        if bit not in (0, 1):
            raise ValueError("Expected 0 or 1")
        return bit

    def setall(self, value: int) -> None:
        bit = self._bit(value)
        if self.backend == "native":
            self._storage.setall(bit)
            return
        block = bytes([255 if bit else 0]) * min(CHUNK_BYTES, len(self._storage))
        for start in range(0, len(self._storage), CHUNK_BYTES):
            size = min(CHUNK_BYTES, len(self._storage) - start)
            self._storage[start : start + size] = block[:size]
        if bit and self._size % 8:
            self._storage[-1] &= (255 << (8 - self._size % 8)) & 255

    def frombytes(self, data: bytes) -> None:
        """Append bits from bytes, starting with each byte's most significant bit."""
        if not isinstance(data, bytes):
            raise TypeError("frombytes expects bytes")
        if self.backend == "native":
            self._storage.frombytes(data)
        elif self._size % 8:
            shift = self._size % 8
            for byte in data:
                self._storage[-1] |= byte >> shift
                self._storage.append((byte << (8 - shift)) & 255)
        else:
            self._storage.extend(data)
        self._size += len(data) * 8

    def tobytes(self) -> bytes:
        """Return packed bytes, with unused low bits of the last byte clear."""
        if self.backend == "native":
            return cast(bytes, self._storage.tobytes())
        return bytes(self._storage)

    def __iadd__(self, other: "BitArray") -> "BitArray":
        if not isinstance(other, BitArray):
            return NotImplemented
        # Snapshot self-concatenation before changing length.
        if other is self:
            other = other.copy()
        full_bytes = len(other) // 8
        for start in range(0, full_bytes, CHUNK_BYTES):
            self.frombytes(
                other._byte_slice(start, min(start + CHUNK_BYTES, full_bytes))
            )
        for i in range(full_bytes * 8, len(other)):
            self._append_bit(other[i])
        return self

    def _append_bit(self, bit: int) -> None:
        if self.backend == "native":
            self._storage.append(bit)
            self._size += 1
        else:
            if self._size % 8 == 0:
                self._storage.append(0)
            self._size += 1
            self[self._size - 1] = bit

    def copy(self) -> "BitArray":
        result = type(self)(backend=self.backend)
        result._size = self._size
        result._storage = self._storage.copy()
        return result

    def count(self, value: int = 1) -> int:
        bit = self._bit(value)
        if self.backend == "native":
            return int(self._storage.count(bit))
        total = 0
        bit_count = getattr(int, "bit_count", None)
        for start in range(0, len(self._storage), CHUNK_BYTES):
            block = self._storage[start : start + CHUNK_BYTES]
            if bit_count is not None:
                total += bit_count(int.from_bytes(block, "little"))
            else:  # Python 3.8/3.9
                total += sum(block.translate(_POPCOUNT))
        return total if bit else self._size - total

    def __ior__(self, other: "BitArray") -> "BitArray":
        if not isinstance(other, BitArray):
            return NotImplemented
        if len(self) != len(other):
            raise ValueError("Bit lengths must match")
        if self.backend == other.backend == "native":
            self._storage |= other._storage
            return self
        byte_length = (self._size + 7) // 8
        for start in range(0, byte_length, CHUNK_BYTES):
            stop = min(start + CHUNK_BYTES, byte_length)
            value = int.from_bytes(self._byte_slice(start, stop), "little")
            value |= int.from_bytes(other._byte_slice(start, stop), "little")
            self._set_bytes(start, value.to_bytes(stop - start, "little"))
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BitArray):
            return NotImplemented
        if self._size != other._size:
            return False
        if self.backend == other.backend:
            return bool(self._storage == other._storage)
        for start in range(0, (self._size + 7) // 8, CHUNK_BYTES):
            if self._byte_slice(start, start + CHUNK_BYTES) != other._byte_slice(
                start, start + CHUNK_BYTES
            ):
                return False
        return True

    def _byte_slice(self, start: int, stop: int) -> bytes:
        if self.backend == "native":
            return cast(bytes, self._storage[start * 8 : stop * 8].tobytes())
        return bytes(self._storage[start:stop])

    def _set_bytes(self, start: int, data: bytes) -> None:
        if self.backend == "native":
            factory, _ = _native_modules()
            bits = factory(endian="big")
            bits.frombytes(data)
            count = min(len(bits), self._size - start * 8)
            self._storage[start * 8 : start * 8 + count] = bits[:count]
        else:
            self._storage[start : start + len(data)] = data

    def iter_guava_chunks(self) -> Iterator[bytes]:
        """Yield bounded chunks in Guava word order, without per-word objects."""
        if self._size % 64:
            raise ValueError("Guava data must contain complete 64-bit words")
        for start in range(0, self._size // 8, CHUNK_BYTES):
            yield _reverse_words(self._byte_slice(start, start + CHUNK_BYTES))

    def set_guava_chunk(self, byte_offset: int, data: bytes) -> None:
        """Fill an already allocated region from complete Guava data words."""
        if byte_offset < 0 or byte_offset % 8 or len(data) % 8:
            raise ValueError("Guava chunks must be word aligned")
        if byte_offset + len(data) > self._size // 8:
            raise ValueError("Guava chunk exceeds bit storage")
        self._set_bytes(byte_offset, _reverse_words(data))
