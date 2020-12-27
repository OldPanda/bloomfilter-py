# bloomfilter-py
Yet another Bloomfilter implementation in Python, compatible with Java's Guava library.

I was looking for a Python library which is capable of reading what Bloomfilter of Java's Guava library serializes and is also able to output byte array which is recognizable by Java. But unfortunately failed. Hence I developed this library by borrowing how Guava implements Bloomfilter a lot to deal with Bloomfilters on both Python and Java sides.

For Bloomfilter usage in Java world, please refer to [this post](https://www.baeldung.com/guava-bloom-filter).

## Install
```
pip install bloomfilter-py
```

## Usage Examples

### Basic Usage
```Python
>>> from bloomfilter import BloomFilter
>>> bloom_filter = BloomFilter(500, 0.01)
>>> for i in range(100):
...     bloom_filter.put(i)
...
>>> 1 in bloom_filter
True
>>> 100 in bloom_filter
False
>>>
```

### Serialize Bloomfilter
```Python
>>> dumps = bloom_filter.dumps()
>>> with open("dumps.out", "wb") as f:
...     f.write(dumps)
...
>>>
```

### Deserialize Bloomfilter
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
