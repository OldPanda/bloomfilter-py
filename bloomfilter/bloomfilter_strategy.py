from abc import ABC, abstractmethod
from bitarray import bitarray
from bloomfilter.funnel import Funnel, LEGACY_FUNNEL

import mmh3
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
        return mmh3.hash64(funnel.encode(key))

    @classmethod
    @abstractmethod
    def put(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    @abstractmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        raise NotImplementedError  # pragma: no cover

    @classmethod
    @abstractmethod
    def ordinal(cls) -> int:
        raise NotImplementedError  # pragma: no cover


class MURMUR128_MITZ_32(Strategy):
    @classmethod
    def put(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash_value, _ = cls.hash_key(key, funnel)
        hash1 = hash_value & 0xFFFFFFFF
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        bits_changed = False
        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash & 0x80000000:
                combined_hash = (~combined_hash) & 0xFFFFFFFF
            index = combined_hash % bit_size
            if array[index] == 0:
                bits_changed = True
            array[index] = 1
        return bits_changed

    @classmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash_value, _ = cls.hash_key(key, funnel)
        hash1 = hash_value & 0xFFFFFFFF
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash & 0x80000000:
                combined_hash = (~combined_hash) & 0xFFFFFFFF
            index = combined_hash % bit_size
            if array[index] == 0:
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
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash1, hash2 = cls.hash_key(key, funnel)

        bits_changed = False
        combined_hash = hash1
        for _ in range(num_hash_functions):
            index = (combined_hash & cls.LONG_MAX) % bit_size
            if array[index] == 0:
                bits_changed = True
            array[index] = 1
            combined_hash += hash2
        return bits_changed

    @classmethod
    def might_contain(
        cls,
        key: typing.Any,
        num_hash_functions: int,
        array: bitarray,
        funnel: Funnel = LEGACY_FUNNEL,
    ) -> bool:
        bit_size = len(array)
        hash1, hash2 = cls.hash_key(key, funnel)

        combined_hash = hash1
        for _ in range(num_hash_functions):
            index = (combined_hash & cls.LONG_MAX) % bit_size
            if not array[index]:
                return False
            combined_hash += hash2
        return True

    @classmethod
    def ordinal(cls) -> int:
        return 1
