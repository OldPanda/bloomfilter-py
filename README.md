# bloomfilter-py
![](https://img.shields.io/pypi/v/bloomfilter-py.svg)
![](https://img.shields.io/pypi/pyversions/bloomfilter-py.svg)
[![codecov](https://codecov.io/gh/OldPanda/bloomfilter-py/branch/master/graph/badge.svg?token=RBX1JK7P7O)](https://codecov.io/gh/OldPanda/bloomfilter-py)
[![Downloads](https://pepy.tech/badge/bloomfilter-py)](https://pepy.tech/project/bloomfilter-py)

## Overview
Yet another Bloomfilter implementation in Python, compatible with Java's Guava library.

I was looking for a Python library which is capable of reading what Bloomfilter of Java's Guava library serializes and is also able to output byte array which is recognizable by Java. But unfortunately failed. Hence I developed this library by borrowing how Guava implements Bloomfilter serialization/deserialization a lot to deal with Bloomfilters on both Python and Java sides.

As for Bloomfilter usage in Java world, please refer to [this post](https://www.baeldung.com/guava-bloom-filter).

Here's a brief [introduction](https://en.wikipedia.org/wiki/Bloom_filter) to Bloomfilter.

## Requirements
* Python 3.8+

## Install
```
pip install bloomfilter-py
```

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
| `Funnels.byteArrayFunnel()` | `BYTE_ARRAY_FUNNEL` |

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
python -m black --check bloomfilter tests
python -m mypy bloomfilter --strict
python -m bandit -r bloomfilter
```

On Windows PowerShell, activate the virtual environment with
`.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`.
