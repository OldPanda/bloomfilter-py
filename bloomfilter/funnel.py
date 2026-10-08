from abc import ABC, abstractmethod
import codecs
import typing


class Funnel(ABC):
    """Encode values exactly as a Guava ``Funnel`` does before hashing."""

    @abstractmethod
    def encode(self, value: typing.Any) -> bytes:
        raise NotImplementedError  # pragma: no cover


class IntegerFunnel(Funnel):
    """Equivalent to Guava's ``Funnels.integerFunnel()``."""

    def encode(self, value: typing.Any) -> bytes:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("IntegerFunnel values must be integers")
        if not -(2**31) <= value <= 2**31 - 1:
            raise ValueError("IntegerFunnel values must fit in a signed 32-bit value")
        return value.to_bytes(4, byteorder="little", signed=True)


class LongFunnel(Funnel):
    """Equivalent to Guava's ``Funnels.longFunnel()``."""

    def encode(self, value: typing.Any) -> bytes:
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("LongFunnel values must be integers")
        if not -(2**63) <= value <= 2**63 - 1:
            raise ValueError("LongFunnel values must fit in a signed 64-bit value")
        return value.to_bytes(8, byteorder="little", signed=True)


class ByteArrayFunnel(Funnel):
    """Equivalent to Guava's ``Funnels.byteArrayFunnel()``."""

    def encode(self, value: typing.Any) -> bytes:
        if not isinstance(value, bytes):
            raise TypeError("ByteArrayFunnel values must be bytes")
        return value


class StringFunnel(Funnel):
    """Equivalent to Guava's ``Funnels.stringFunnel(charset)``."""

    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = codecs.lookup(encoding).name

    def encode(self, value: typing.Any) -> bytes:
        if not isinstance(value, str):
            raise TypeError("StringFunnel values must be strings")
        return value.encode(self.encoding)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StringFunnel) and self.encoding == other.encoding

    def __hash__(self) -> int:
        return hash((StringFunnel, self.encoding))


class LegacyFunnel(Funnel):
    """Preserve bloomfilter-py's historical type-dependent encoding.

    Unlike Guava funnels, this encoder chooses the integer width separately for
    each value. New interoperability code should select an explicit funnel.
    """

    def encode(self, value: typing.Any) -> bytes:
        if isinstance(value, bool):
            return INTEGER_FUNNEL.encode(int(value))
        if isinstance(value, int):
            if -(2**31) <= value <= 2**31 - 1:
                return INTEGER_FUNNEL.encode(value)
            return LONG_FUNNEL.encode(value)
        if isinstance(value, str):
            return UTF8_STRING_FUNNEL.encode(value)
        raise TypeError("BloomFilter keys must be integers or strings")


INTEGER_FUNNEL = IntegerFunnel()
LONG_FUNNEL = LongFunnel()
BYTE_ARRAY_FUNNEL = ByteArrayFunnel()
UTF8_STRING_FUNNEL = StringFunnel("utf-8")
LEGACY_FUNNEL = LegacyFunnel()
