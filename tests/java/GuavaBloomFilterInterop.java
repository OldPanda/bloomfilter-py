import com.google.common.hash.BloomFilter;
import com.google.common.hash.Funnels;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Test helper that reads and writes bloomfilter-py data with the real Guava API. */
public final class GuavaBloomFilterInterop {
  private static final int EXPECTED_INSERTIONS = 100;
  private static final double FPP = 0.01;

  private static final int[] INTEGERS = {
    Integer.MIN_VALUE, -1, 0, 1, Integer.MAX_VALUE
  };
  private static final long[] LONGS = {
    Long.MIN_VALUE, -2147483649L, 0L, 2147483648L, Long.MAX_VALUE
  };
  private static final String[] STRINGS = {"", "hello", "雪", "emoji 😀"};
  private static final byte[][] BYTE_ARRAYS = {
    new byte[0], new byte[] {0, 1, -1}, "雪".getBytes(StandardCharsets.UTF_8)
  };

  private GuavaBloomFilterInterop() {}

  public static void main(String[] args) throws Exception {
    if (args.length != 3) {
      throw new IllegalArgumentException("usage: <write|read|probe> <funnel> <path>");
    }

    String operation = args[0];
    String funnel = args[1];
    Path path = Path.of(args[2]);
    if (operation.equals("write")) {
      write(funnel, path);
    } else if (operation.equals("read")) {
      readAndVerify(funnel, path);
    } else if (operation.equals("probe")) {
      System.out.println(probe(funnel, path));
    } else {
      throw new IllegalArgumentException("unknown operation: " + operation);
    }
  }

  private static void write(String funnel, Path path) throws IOException {
    switch (funnel) {
      case "integer":
        BloomFilter<Integer> integerFilter =
            BloomFilter.create(Funnels.integerFunnel(), EXPECTED_INSERTIONS, FPP);
        for (int value : INTEGERS) {
          integerFilter.put(value);
        }
        writeTo(integerFilter, path);
        return;
      case "long":
        BloomFilter<Long> longFilter =
            BloomFilter.create(Funnels.longFunnel(), EXPECTED_INSERTIONS, FPP);
        for (long value : LONGS) {
          longFilter.put(value);
        }
        writeTo(longFilter, path);
        return;
      case "string":
        BloomFilter<CharSequence> stringFilter =
            BloomFilter.create(
                Funnels.stringFunnel(StandardCharsets.UTF_8), EXPECTED_INSERTIONS, FPP);
        for (String value : STRINGS) {
          stringFilter.put(value);
        }
        writeTo(stringFilter, path);
        return;
      case "string-utf16":
        BloomFilter<CharSequence> utf16Filter =
            BloomFilter.create(
                Funnels.stringFunnel(StandardCharsets.UTF_16), EXPECTED_INSERTIONS, FPP);
        for (String value : STRINGS) {
          utf16Filter.put(value);
        }
        writeTo(utf16Filter, path);
        return;
      case "bytes":
        BloomFilter<byte[]> byteFilter =
            BloomFilter.create(Funnels.byteArrayFunnel(), EXPECTED_INSERTIONS, FPP);
        for (byte[] value : BYTE_ARRAYS) {
          byteFilter.put(value);
        }
        writeTo(byteFilter, path);
        return;
      default:
        throw new IllegalArgumentException("unknown funnel: " + funnel);
    }
  }

  private static void readAndVerify(String funnel, Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
      switch (funnel) {
        case "integer":
          BloomFilter<Integer> integerFilter =
              BloomFilter.readFrom(input, Funnels.integerFunnel());
          for (int value : INTEGERS) {
            require(integerFilter.mightContain(value), funnel, value);
          }
          return;
        case "long":
          BloomFilter<Long> longFilter = BloomFilter.readFrom(input, Funnels.longFunnel());
          for (long value : LONGS) {
            require(longFilter.mightContain(value), funnel, value);
          }
          return;
        case "string":
          BloomFilter<CharSequence> stringFilter =
              BloomFilter.readFrom(input, Funnels.stringFunnel(StandardCharsets.UTF_8));
          for (String value : STRINGS) {
            require(stringFilter.mightContain(value), funnel, value);
          }
          return;
        case "string-utf16":
          BloomFilter<CharSequence> utf16Filter =
              BloomFilter.readFrom(input, Funnels.stringFunnel(StandardCharsets.UTF_16));
          for (String value : STRINGS) {
            require(utf16Filter.mightContain(value), funnel, value);
          }
          return;
        case "bytes":
          BloomFilter<byte[]> byteFilter =
              BloomFilter.readFrom(input, Funnels.byteArrayFunnel());
          for (byte[] value : BYTE_ARRAYS) {
            require(byteFilter.mightContain(value), funnel, toHex(value));
          }
          return;
        default:
          throw new IllegalArgumentException("unknown funnel: " + funnel);
      }
    }
  }

  private static String probe(String funnel, Path path) throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
      switch (funnel) {
        case "integer":
          BloomFilter<Integer> integerFilter =
              BloomFilter.readFrom(input, Funnels.integerFunnel());
          StringBuilder integerResults = new StringBuilder();
          for (int value : INTEGERS) {
            appendResult(integerResults, integerFilter.mightContain(value));
          }
          for (int value = -1000; value <= 1000; value++) {
            appendResult(integerResults, integerFilter.mightContain(value));
          }
          return integerResults.toString();
        case "long":
          BloomFilter<Long> longFilter = BloomFilter.readFrom(input, Funnels.longFunnel());
          StringBuilder longResults = new StringBuilder();
          for (long value : LONGS) {
            appendResult(longResults, longFilter.mightContain(value));
          }
          for (long value = -1000; value <= 1000; value++) {
            appendResult(longResults, longFilter.mightContain(value * 4294967311L));
          }
          return longResults.toString();
        case "string":
          BloomFilter<CharSequence> stringFilter =
              BloomFilter.readFrom(input, Funnels.stringFunnel(StandardCharsets.UTF_8));
          StringBuilder stringResults = new StringBuilder();
          for (String value : STRINGS) {
            appendResult(stringResults, stringFilter.mightContain(value));
          }
          for (int value = 0; value <= 500; value++) {
            appendResult(stringResults, stringFilter.mightContain("probe-" + value));
          }
          return stringResults.toString();
        case "string-utf16":
          BloomFilter<CharSequence> utf16Filter =
              BloomFilter.readFrom(input, Funnels.stringFunnel(StandardCharsets.UTF_16));
          StringBuilder utf16Results = new StringBuilder();
          for (String value : STRINGS) {
            appendResult(utf16Results, utf16Filter.mightContain(value));
          }
          for (int value = 0; value <= 500; value++) {
            appendResult(utf16Results, utf16Filter.mightContain("probe-" + value));
          }
          return utf16Results.toString();
        case "bytes":
          BloomFilter<byte[]> byteFilter =
              BloomFilter.readFrom(input, Funnels.byteArrayFunnel());
          StringBuilder byteResults = new StringBuilder();
          for (byte[] value : BYTE_ARRAYS) {
            appendResult(byteResults, byteFilter.mightContain(value));
          }
          for (int value = 0; value <= 500; value++) {
            byte[] probe = ("probe-" + value).getBytes(StandardCharsets.UTF_8);
            appendResult(byteResults, byteFilter.mightContain(probe));
          }
          return byteResults.toString();
        default:
          throw new IllegalArgumentException("unknown funnel: " + funnel);
      }
    }
  }

  private static void writeTo(BloomFilter<?> filter, Path path) throws IOException {
    try (OutputStream output = Files.newOutputStream(path)) {
      filter.writeTo(output);
    }
  }

  private static void require(boolean condition, String funnel, Object value) {
    if (!condition) {
      throw new AssertionError("missing " + funnel + " value: " + value);
    }
  }

  private static void appendResult(StringBuilder results, boolean result) {
    results.append(result ? '1' : '0');
  }

  private static String toHex(byte[] value) {
    StringBuilder result = new StringBuilder();
    for (byte item : value) {
      result.append(String.format("%02x", item & 0xff));
    }
    return result.toString();
  }
}
