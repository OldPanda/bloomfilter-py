"""Seed-zero MurmurHash3 x64_128, returning two signed 64-bit integers.

Implements Austin Appleby's public-domain reference algorithm:
https://github.com/aappleby/smhasher/blob/master/src/MurmurHash3.cpp
Little-endian block reads and explicit wrapping match Guava on all hosts.
"""

from struct import Struct
from typing import Tuple

_MASK = (1 << 64) - 1
_C1 = 0x87C37B91114253D5
_C2 = 0x4CF5AD432745937F
_BLOCK = Struct("<QQ")


def _fmix(value: int) -> int:
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & _MASK
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & _MASK
    return value ^ (value >> 33)


def hash64(data: bytes) -> Tuple[int, int]:
    """Hash bytes only; input is neither modified nor retained. Seed is zero."""
    if not isinstance(data, bytes):
        raise TypeError("MurmurHash3 input must be bytes")
    h1 = h2 = 0
    mask, c1, c2 = _MASK, _C1, _C2
    stop = len(data) & ~15
    for offset in range(0, stop, 16):
        k1, k2 = _BLOCK.unpack_from(data, offset)
        k1 = (k1 * c1) & mask
        k1 = ((k1 << 31) | (k1 >> 33)) & mask
        h1 ^= (k1 * c2) & mask
        h1 = ((h1 << 27) | (h1 >> 37)) & mask
        h1 = ((h1 + h2) * 5 + 0x52DCE729) & mask
        k2 = (k2 * c2) & mask
        k2 = ((k2 << 33) | (k2 >> 31)) & mask
        h2 ^= (k2 * c1) & mask
        h2 = ((h2 << 31) | (h2 >> 33)) & mask
        h2 = ((h2 + h1) * 5 + 0x38495AB5) & mask
    tail = data[stop:]
    if len(tail) > 8:
        k2 = (int.from_bytes(tail[8:], "little") * c2) & mask
        k2 = ((k2 << 33) | (k2 >> 31)) & mask
        h2 ^= (k2 * c1) & mask
    if tail:
        k1 = (int.from_bytes(tail[:8], "little") * c1) & mask
        k1 = ((k1 << 31) | (k1 >> 33)) & mask
        h1 ^= (k1 * c2) & mask
    h1 ^= len(data)
    h2 ^= len(data)
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    h1, h2 = _fmix(h1), _fmix(h2)
    h1 = (h1 + h2) & mask
    h2 = (h2 + h1) & mask
    return (
        h1 if h1 < 1 << 63 else h1 - (1 << 64),
        h2 if h2 < 1 << 63 else h2 - (1 << 64),
    )
