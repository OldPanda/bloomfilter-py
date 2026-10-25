# bloomfilter-py
![](https://img.shields.io/pypi/v/bloomfilter-py.svg)
![](https://img.shields.io/pypi/pyversions/bloomfilter-py.svg)
[![codecov](https://codecov.io/gh/OldPanda/bloomfilter-py/branch/master/graph/badge.svg?token=RBX1JK7P7O)](https://codecov.io/gh/OldPanda/bloomfilter-py)
[![Downloads](https://pepy.tech/badge/bloomfilter-py)](https://pepy.tech/project/bloomfilter-py)

## Overview
Yet another Bloomfilter implementation in Python, compatible with Java's Guava library.

Compatibility targets Guava's compact `BloomFilter.writeTo` / `readFrom` format.
Java `ObjectOutputStream` / `ObjectInputStream` serialization is a different
format and is not supported. The compact format does not include the funnel;
callers must provide the matching encoder when loading a filter.

I was looking for a Python library which is capable of reading what Bloomfilter of Java's Guava library serializes and is also able to output byte array which is recognizable by Java. But unfortunately failed. Hence I developed this library by borrowing how Guava implements Bloomfilter serialization/deserialization a lot to deal with Bloomfilters on both Python and Java sides.

As for Bloomfilter usage in Java world, please refer to [this post](https://www.baeldung.com/guava-bloom-filter).

Here's a brief [introduction](https://en.wikipedia.org/wiki/Bloom_filter) to Bloomfilter.

## Requirements
* Python 3.8+

## Install
```
pip install bloomfilter-py
```

## Backends and migration from 1.3

Version 2.0 runs on the Python standard library alone. `bitarray` and `mmh3`
are no longer required to install or import this package. The default is always
`backend="python"`, even if those packages are already installed. For explicit
native acceleration:

```bash
pip install 'bloomfilter-py[native]'
```

```python
from bloomfilter import BloomFilter

fast = BloomFilter(500, 0.01, backend="native")
fast.put("example")
loaded = BloomFilter.loads(fast.dumps(), backend="native")
assert "example" in loaded
assert loaded.backend == "native"
```

The constructor and all loading methods accept the keyword-only `backend`
argument (`"python"` or `"native"`). An invalid name raises `ValueError`;
requesting native mode without **both** optional packages raises `ImportError`
with installation instructions. There is no automatic fallback. `copy()`
preserves the backend. Filters using different backends can be compared and
merged when their strategies, funnels, sizes, and hash counts are compatible.
Backend choice is not serialized: all old dumps remain readable, and new dumps
use exactly the same Guava compact format.

Pure Python hashing is slower than the C extension, especially on long keys.
Native mode is available for throughput-sensitive workloads. Serialization,
counting, and merging process at most 64 KiB of payload per chunk; copies and
returned dumps necessarily allocate their complete result. `dumps()` and
`loads()` also retain full input/output bytes, so use stream methods for large
filters. Backing storage remains packed (roughly one byte per eight bits).

### Bit storage and custom strategies

`filter.data` is now a `bloomfilter.BitArray` facade with consistent semantics
on either backend. It supports `len`, iteration, negative/integer indexing,
slice copies, scalar or equal-length iterable slice assignment, `setall`,
`count(0/1)`, `copy`, equality, `|=`, `+=`, `frombytes`, and `tobytes`.
Slices preserve the backend; slice assignment cannot resize. Appending via
`frombytes` or `+=` works even at non-byte-aligned lengths. `tobytes()` uses
most-significant-bit-first bytes with zero padding at the end. The buffer
protocol and the complete third-party `bitarray` API are **not** provided.

Existing `setup(hash_count, data, strategy, funnel)` calls accept this facade.
For migration, a third-party `bitarray.bitarray` is also accepted when installed;
it is copied into Python-backed storage and normalized to logical bit order,
including little-endian inputs. It is no longer aliased to `filter.data`.
Callers relying on that alias or on third-party-only methods must update.
Passing a `BitArray` to `setup` retains it, as before, so external mutations
remain visible. `backend` reflects the current data object.

Custom strategies still receive the same positional `put` / `might_contain`
arguments, now with the facade as their data argument. Overrides of built-in
strategies' `hash_key` are honored on both backends. Strategies must not depend
on private storage fields or a specific third-party data type. Direct calls to built-in strategies with legacy third-party bit arrays remain
supported. Direct calls to `Strategy.hash_key` always use the standard-library MurmurHash3 implementation.

## Usage Examples

### Basic Usage
```Python
>>> from bloomfilter import BloomFilter
>>> bloom_filter = BloomFilter(expected_insertions=500, err_rate=0.01)
>>> for i in range(100):
...     bloom_filter.put(i)
...
>>> 1 in bloom_filter
True
>>> 100 in bloom_filter
False
>>>
```

### Guava Funnel Compatibility

Guava's compact BloomFilter format stores the hash strategy and bit array, but
does not store its `Funnel`. To query a filter produced by Guava, select the
same funnel that was used in Java:

```Python
from bloomfilter import BloomFilter, INTEGER_FUNNEL

with open("guava-filter.out", "rb") as f:
    bloom_filter = BloomFilter.loads(f.read(), funnel=INTEGER_FUNNEL)
```

The built-in mappings are:

| Java funnel | bloomfilter-py funnel |
| --- | --- |
| `Funnels.integerFunnel()` | `INTEGER_FUNNEL` |
| `Funnels.longFunnel()` | `LONG_FUNNEL` |
| `Funnels.stringFunnel(StandardCharsets.UTF_8)` | `UTF8_STRING_FUNNEL` |
| `Funnels.stringFunnel(StandardCharsets.UTF_16)` | `StringFunnel("UTF-16")` |
| `Funnels.stringFunnel(StandardCharsets.UTF_16BE)` | `StringFunnel("UTF-16BE")` |
| `Funnels.stringFunnel(StandardCharsets.UTF_16LE)` | `StringFunnel("UTF-16LE")` |
| `Funnels.byteArrayFunnel()` | `BYTE_ARRAY_FUNNEL` |

`StringFunnel` supports Java's six standard charsets: US-ASCII, ISO-8859-1,
UTF-8, UTF-16, UTF-16BE, and UTF-16LE. Custom Guava funnels are not encoded in
the serialized filter; use a matching custom Python `Funnel` implementation
when reading them.

Use the same funnel when creating a filter that Java will read:

```Python
from bloomfilter import BloomFilter, LONG_FUNNEL

bloom_filter = BloomFilter(500, 0.01, funnel=LONG_FUNNEL)
bloom_filter.put(1)  # Encoded as a Java long even though 1 fits in an int.
```

Calls that omit `funnel` retain the historical bloomfilter-py behavior, which
chooses integer width from each value and therefore is not suitable for all
Guava interoperability scenarios.

### Serialize Bloomfilter
You can easily serialize `BloomFilter` instance to a byte array
```Python
>>> dumps = bloom_filter.dumps()
>>> with open("dumps.out", "wb") as f:
...     f.write(dumps)
...
>>>
```

or to a hex string
```Python
>>> hex_str = bloom_filter.dumps_to_hex()
```

or to a base64 encoded bytes
```Python
base64_bytes = bloom_filter.dumps_to_base64()
```

### Deserialize Bloomfilter
And you can easily initialize a `BloomFilter` instance from a byte array
```Python
>>> with open("dumps.out", "rb") as f:
...     bf = BloomFilter.loads(f.read())
...
>>> 1 in bf
True
>>> 100 in bf
False
>>>
```

or from a hex string
```Python
>>> bf = BloomFilter.loads_from_hex(hex_str)
>>> 1 in bf
True
>>> 100 in bf
False
```

or from a base64 encoded bytes
```Python
>>> bf = BloomFilter.loads_from_base64(base64_bytes)
>>> 100 in bf
False
>>> 200 in bf
False
>>> 1 in bf
True
>>> 99 in bf
True
```

Deserialization limits the backing bit array to 2³⁰ bits by default. For a
trusted larger Guava filter, pass an explicit limit to any loading method:

```Python
bf = BloomFilter.loads(dumps, funnel=INTEGER_FUNNEL, max_num_bits=2**31)
```

### Stream I/O

Read and write compact Guava data directly with binary streams:

```Python
with open("guava-filter.out", "rb") as stream:
    bf = BloomFilter.read_from(stream, funnel=INTEGER_FUNNEL)

with open("python-filter.out", "wb") as stream:
    bf.write_to(stream)

byte_count = bf.serialized_size()
```

`read_from` reads exactly one filter, leaving any following stream data unread.
It accepts the same `max_num_bits` limit as `loads`, and validates the header
before reading the payload. `loads` requires exactly one filter with no trailing
bytes. Neither stream method closes the caller's stream. Both handle partial
reads or writes on blocking binary streams.

### Copies, Merging, and Statistics

```Python
snapshot = bf.copy()
other = BloomFilter(500, 0.01, funnel=INTEGER_FUNNEL)
other.put(123)

if bf.is_compatible(other):
    bf.put_all(other)

false_positive_probability = bf.expected_fpp()
estimated_distinct_elements = bf.approximate_element_count()
```

`copy` duplicates the backing bit array and preserves the loading limit. It
shares the funnel and stateless strategy, as Guava does; custom funnels should
be immutable. `put_all` performs an in-place union without modifying the source.
Compatibility requires distinct instances with the same bit-array size, number
of hashes, strategy, and equal funnels. Custom funnels must define equality
when separate instances represent the same encoding.

Statistics use the current bit occupancy, so they also work on loaded and merged
filters. A fully saturated filter has an expected FPP of `1.0`; its element count
cannot be estimated and raises `OverflowError`, corresponding to Guava's
`ArithmeticException`. Filter equality compares configuration, funnel, and bit
contents. Mutable filters are unhashable in Python.

Unlike Guava's atomic implementation, this library does not guarantee safe
concurrent mutations. Use an external lock around mutations, queries, copies,
statistics, and serialization when sharing a filter between threads. Java's
deprecated predicate aliases and stream collectors are language-specific APIs;
use `might_contain` (or `in`) and a loop calling `put` in Python.

## Development and Testing

From the repository root, create an isolated virtual environment and install the
project in editable mode with pytest:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e . pytest
```

Run the complete test suite:

```bash
python -m pytest -v
```

The bidirectional Java integration test requires a JDK and a Guava JAR. Point
`GUAVA_JAR` at the JAR to compile the included Java helper and verify both
Guava-to-Python and Python-to-Guava serialization:

```bash
GUAVA_JAR=/path/to/guava-33.7.2-jre.jar \
  python -m pytest -v tests/test_guava_interop.py
```

The test is skipped when those prerequisites are unavailable. CI downloads the
pinned Guava release, verifies its SHA-256 checksum, and runs the test as a
required separate job.

To run the same formatting, type, and security checks used during development,
install the additional tools and execute:

```bash
python -m pip install black mypy bandit
python -m black --check bloomfilter tests benchmarks scripts
python -m mypy bloomfilter --strict
python -m bandit -r bloomfilter
```

On Windows PowerShell, activate the virtual environment with
`.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.

### Reproducible backend benchmarks

```bash
python benchmarks/benchmark_backends.py --backend python --output python.json
python benchmarks/benchmark_backends.py --backend native --output native.json
# Against a separate checkout of 1.3.0, with its dependencies installed:
python benchmarks/benchmark_backends.py --backend baseline \
  --package-path /path/to/1.3.0 --output baseline.json
```

The script reports median timings, raw repeats, workload sizes, and interpreter
metadata. It covers fresh and repeated insertions, hits and misses, short and
long byte keys, serialization, statistics, and merging. Results describe the
specified workload rather than a universal throughput guarantee.

For the zero-dependency source suite run `python -S -m unittest discover`.
Install `.[native]` to enable optional differential tests against the C packages.
The checked-in hash vectors were generated with mmh3 5.3.1 and cover every
length from 0 through 512 plus larger block boundaries.
Run Java integration tests for both backends with `BLOOMFILTER_TEST_BACKEND`
set to `python` and `native` respectively. CI covers Python 3.8 through 3.14.

Build and verify release artifacts with `python -m build` followed by
`python scripts/verify_distribution.py dist`. The latter installs the wheel
offline into a clean temporary environment and verifies it outside the source
path, including the absence of mandatory runtime dependencies.
