from abc import ABC, abstractmethod
from bitarray import bitarray

import mmh3
import typing


class Strategy(ABC):
    LONG_MAX = 0x7FFFFFFFFFFFFFFF
    LONG_MIN = -0x7FFFFFFFFFFFFFFF
    INT_MAX = 0x7FFFFFFF
    INT_MIN = -0x7FFFFFFF

    @classmethod
    @abstractmethod
    def put(
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        pass

    @classmethod
    @abstractmethod
    def might_contain(
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        pass

    @classmethod
    @abstractmethod
    def ordinal(cls) -> int:
        pass


class MURMUR128_MITZ_32(Strategy):
    @classmethod
    def put(
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        bit_size = len(array)
        if isinstance(key, int):
            if cls.INT_MIN <= key <= cls.INT_MAX:
                hash_value, _ = mmh3.hash64(key.to_bytes(4, byteorder="little"))
            elif cls.LONG_MIN <= key <= cls.LONG_MAX:
                hash_value, _ = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash_value, _ = mmh3.hash64(key)
        hash1 = hash_value & cls.INT_MAX
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        bits_changed = False
        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash > cls.INT_MAX or combined_hash < 0:
                combined_hash = (~combined_hash) & cls.INT_MAX
            index = combined_hash % bit_size
            if array[index] == 0:
                bits_changed = True
            array[index] = 1
        return bits_changed

    @classmethod
    def might_contain(
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        bit_size = len(array)
        if isinstance(key, int):
            if cls.INT_MIN <= key <= cls.INT_MAX:
                hash_value, _ = mmh3.hash64(key.to_bytes(4, byteorder="little"))
            elif cls.LONG_MIN <= key <= cls.LONG_MAX:
                hash_value, _ = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash_value, _ = mmh3.hash64(key)
        hash1 = hash_value & cls.INT_MAX
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash > cls.INT_MAX or combined_hash < 0:
                combined_hash = (~combined_hash) & cls.INT_MAX
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
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        bit_size = len(array)
        if isinstance(key, int):
            if cls.INT_MIN <= key <= cls.INT_MAX:
                hash1, hash2 = mmh3.hash64(key.to_bytes(4, byteorder="little"))
            elif cls.LONG_MIN <= key <= cls.LONG_MAX:
                hash1, hash2 = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash1, hash2 = mmh3.hash64(key)

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
        cls, key: typing.Union[int, str], num_hash_functions: int, array: bitarray
    ) -> bool:
        bit_size = len(array)
        if isinstance(key, int):
            if cls.INT_MIN <= key <= cls.INT_MAX:
                hash1, hash2 = mmh3.hash64(key.to_bytes(4, byteorder="little"))
            elif cls.LONG_MIN <= key <= cls.LONG_MAX:
                hash1, hash2 = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash1, hash2 = mmh3.hash64(key)

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
