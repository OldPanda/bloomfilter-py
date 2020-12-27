from abc import ABC, abstractmethod

import mmh3


class Strategy(ABC):
    LONG_MAX = 0x7FFFFFFFFFFFFFFF
    LONG_MIN = -0x7FFFFFFFFFFFFFFF
    INT_MAX = 0x7FFFFFFF
    INT_MIN = -0x7FFFFFFF

    @abstractmethod
    def put(self, key, num_hash_functions, array):
        pass

    @abstractmethod
    def might_contain(self, key, num_hash_functions, array):
        pass

    @abstractmethod
    def ordinal(self):
        pass


class MURMUR128_MITZ_32(Strategy):
    @classmethod
    def put(self, key, num_hash_functions, array):
        bit_size = len(array)
        if isinstance(key, int) and self.INT_MIN <= key <= self.INT_MAX:
            hash_value, _ = mmh3.hash64(key.to_bytes(4, byteorder="little"))
        elif isinstance(key, int) and self.LONG_MIN <= key <= self.LONG_MAX:
            hash_value, _ = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash_value, _ = mmh3.hash64(key)
        hash1 = hash_value & self.INT_MAX
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        bits_changed = False
        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash > self.INT_MAX or combined_hash < 0:
                combined_hash = (~combined_hash) & self.INT_MAX
            index = combined_hash % bit_size
            if array[index] == 0:
                bits_changed = True
            array[index] = 1
        return bits_changed

    @classmethod
    def might_contain(self, key, num_hash_functions, array):
        bit_size = len(array)
        if isinstance(key, int) and self.INT_MIN <= key <= self.INT_MAX:
            hash_value, _ = mmh3.hash64(key.to_bytes(4, byteorder="little"))
        elif isinstance(key, int) and self.LONG_MIN <= key <= self.LONG_MAX:
            hash_value, _ = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash_value, _ = mmh3.hash64(key)
        hash1 = hash_value & self.INT_MAX
        hash2 = (hash_value >> 32) & 0xFFFFFFFF

        for i in range(1, num_hash_functions + 1):
            combined_hash = hash1 + (i * hash2)
            combined_hash &= 0xFFFFFFFF
            if combined_hash > self.INT_MAX or combined_hash < 0:
                combined_hash = (~combined_hash) & self.INT_MAX
            index = combined_hash % bit_size
            if array[index] == 0:
                return False
        return True

    @classmethod
    def ordinal(self):
        return 0


class MURMUR128_MITZ_64(Strategy):
    @classmethod
    def put(self, key, num_hash_functions, array):
        bit_size = len(array)
        if isinstance(key, int) and self.INT_MIN <= key <= self.INT_MAX:
            hash1, hash2 = mmh3.hash64(key.to_bytes(4, byteorder="little"))
        elif isinstance(key, int) and self.LONG_MIN <= key <= self.LONG_MAX:
            hash1, hash2 = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash1, hash2 = mmh3.hash64(key)

        bits_changed = False
        combined_hash = hash1
        for _ in range(num_hash_functions):
            index = (combined_hash & self.LONG_MAX) % bit_size
            if array[index] == 0:
                bits_changed = True
            array[index] = 1
            combined_hash += hash2
        return bits_changed

    @classmethod
    def might_contain(self, key, num_hash_functions, array):
        bit_size = len(array)
        if isinstance(key, int) and self.INT_MIN <= key <= self.INT_MAX:
            hash1, hash2 = mmh3.hash64(key.to_bytes(4, byteorder="little"))
        elif isinstance(key, int) and self.LONG_MIN <= key <= self.LONG_MAX:
            hash1, hash2 = mmh3.hash64(key.to_bytes(8, byteorder="little"))
        else:
            hash1, hash2 = mmh3.hash64(key)

        combined_hash = hash1
        for _ in range(num_hash_functions):
            index = (combined_hash & self.LONG_MAX) % bit_size
            if not array[index]:
                return False
            combined_hash += hash2
        return True

    @classmethod
    def ordinal(self):
        return 1
