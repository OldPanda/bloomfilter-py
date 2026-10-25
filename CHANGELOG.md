# Changelog

## 2.0.0

- Retain master security checks that bound hexadecimal and Base64 decoding
  before allocating the complete serialized payload.
- Remove all mandatory runtime dependencies; ship packed bit storage and a
  seed-zero MurmurHash3 x64_128 implementation supporting Python 3.8+.
- Add explicit `backend="python"` (default) and `backend="native"` modes.
  Native acceleration is available through the `native` installation extra.
- Preserve both hashing strategies, existing funnels and the Guava compact
  serialization format. Support cross-backend comparison and merging.
- Replace per-word serialization objects with bounded chunk transformations;
  chunk large counts and merges as well.
- Export a stable `BitArray` facade. `setup` copies external third-party
  bitarray inputs; third-party-only data methods and aliasing need migration.
- Reject non-finite error rates, nonintegral sizing and misbehaving streams.
- Add fixed and random hash differential tests, packed-bit/backend tests,
  memory checks, packaging validation, benchmarks and a dual-backend CI matrix.

Public bit storage and external-array aliasing changes require a major version.
The version is prepared locally; publishing requires a separate release action.
