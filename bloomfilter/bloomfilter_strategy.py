from abc import ABC, abstractmethod
from bloomfilter._bitarray import BitArray
from bloomfilter.funnel import Funnel, LEGACY_FUNNEL

from bloomfilter._murmur3 import hash64
import typing


class Strategy(ABC):
    LONG_MAX = 0x7FFFFFFFFFFFFFFF
    LONG_MIN = -0x8000000000000000
    INT_MAX = 0x7FFFFFFF
    INT_MIN = -0x80000000

    @classmethod
    def hash_key(
        cls, key: typing.Any, funnel: Funnel = LEGACY_FUNNEL
    ) -> typing.Tuple[int, int]:
        return hash64(funnel.encode(key))

    @classmethod
    def _hash_for_array(
        cls, key: typing.Any, funnel: Funnel, array: BitArray
    ) -> typing.Tuple[int, int]:
        # Honor user overrides of hash_key; only the built-in hash is accelerated.
        method = cls.hash_key
        if (
            isinstance(array, BitArray)
            and getattr(method, "__func__", method) is _BUILTIN_HASH_KEY
        ):
            return array._hash64(funnel.encode(key))
        return method(key, funnel)

    @classmethod
    @abstractmethod
    def put(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    @abstractmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    @abstractmethod
    def ordinal(cls) -> int:
        raise NotImplementedError  # pragma: no cover


_BUILTIN_HASH_KEY = getattr(Strategy.hash_key, "__func__")


class MURMUR128_MITZ_32(Strategy):
    @classmethod
    def put(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash_value, _ = cls._hash_for_array(key, funnel, array)
        hash1 = hash_value & 0xFFFFFFFF
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        storage = array._storage if isinstance(array, BitArray) else array
        pure = isinstance(array, BitArray) and array.backend == "python"
        bits_changed = False
        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash & 0x80000000:
                combined_hash = (~combined_hash) & 0xFFFFFFFF
            index = combined_hash % bit_size
            if pure:
                byte, mask = index >> 3, 1 << (7 - (index & 7))
                if not storage[byte] & mask:
                    bits_changed = True
                    storage[byte] |= mask
            elif not storage[index]:
                bits_changed = True
                storage[index] = 1
        return bits_changed

    @classmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash_value, _ = cls._hash_for_array(key, funnel, array)
        hash1 = hash_value & 0xFFFFFFFF
        hash2 = (hash_value >> 32) & 0xFFFFFFFF
        storage = array._storage if isinstance(array, BitArray) else array
        pure = isinstance(array, BitArray) and array.backend == "python"

        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash & 0x80000000:
                combined_hash = (~combined_hash) & 0xFFFFFFFF
            index = combined_hash % bit_size
            if pure:
                if not storage[index >> 3] & (1 << (7 - (index & 7))):
                    return False
            elif not storage[index]:
                return False
        return True

    @classmethod
    def ordinal(cls) -> int:
        return 0


class MURMUR128_MITZ_64(Strategy):
    @classmethod
    def put(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash1, hash2 = cls._hash_for_array(key, funnel, array)

        storage = array._storage if isinstance(array, BitArray) else array
        pure = isinstance(array, BitArray) and array.backend == "python"
        bits_changed = False
        combined_hash = hash1
        for _ in range(num_hash_functions):
            index = (combined_hash & cls.LONG_MAX) % bit_size
            if pure:
                byte, mask = index >> 3, 1 << (7 - (index & 7))
                if not storage[byte] & mask:
                    bits_changed = True
                    storage[byte] |= mask
            elif not storage[index]:
                bits_changed = True
                storage[index] = 1
            combined_hash += hash2
        return bits_changed

    @classmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: BitArray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash1, hash2 = cls._hash_for_array(key, funnel, array)

        combined_hash = hash1
        storage = array._storage if isinstance(array, BitArray) else array
        pure = isinstance(array, BitArray) and array.backend == "python"
        for _ in range(num_hash_functions):
            index = (combined_hash & cls.LONG_MAX) % bit_size
            if pure:
                if not storage[index >> 3] & (1 << (7 - (index & 7))):
                    return False
            elif not storage[index]:
                return False
            combined_hash += hash2
        return True

    @classmethod
    def ordinal(cls) -> int:
        return 1
