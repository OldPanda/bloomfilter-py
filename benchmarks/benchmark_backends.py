"""Reproducible stdlib-only driver; baseline/native modes need their packages."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import timeit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=("python", "native", "baseline"), default="python"
    )
    parser.add_argument(
        "--package-path", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--number", type=int, default=3)
    args = parser.parse_args()
    if args.repeat < 1 or args.number < 1:
        parser.error("repeat and number must be positive")
    sys.path.insert(0, str(args.package_path.resolve()))
    from bloomfilter import BloomFilter, BYTE_ARRAY_FUNNEL

    def make(expected=5000):
        if args.backend == "baseline":
            return BloomFilter(expected, 0.01, funnel=BYTE_ARRAY_FUNNEL)
        return BloomFilter(
            expected, 0.01, funnel=BYTE_ARRAY_FUNNEL, backend=args.backend
        )

    measurements = {}
    fingerprints = {}
    for key_size in (16, 1024):
        keys = [
            i.to_bytes(4, "little") + bytes([i % 256]) * (key_size - 4)
            for i in range(500)
        ]
        misses = [
            (i + 500).to_bytes(4, "little") + bytes([(i + 500) % 256]) * (key_size - 4)
            for i in range(500)
        ]
        bf = make()
        for key in keys:
            bf.put(key)
        fingerprints[str(key_size)] = hashlib.sha256(bf.dumps()).hexdigest()

        def insert_new():
            fresh = make()
            for key in keys:
                fresh.put(key)

        tasks = {
            "insert_new": insert_new,
            "insert_repeat": lambda: [bf.put(key) for key in keys],
            "query_hit": lambda: [bf.might_contain(key) for key in keys],
            "query_miss": lambda: [bf.might_contain(key) for key in misses],
        }
        for name, task in tasks.items():
            raw = [
                value / args.number
                for value in timeit.repeat(task, number=args.number, repeat=args.repeat)
            ]
            measurements[f"{name}_{key_size}B_500keys"] = {
                "median_seconds": statistics.median(raw),
                "raw_seconds": raw,
            }

    # Approximately 1 MiB, enough to exercise bounded chunks repeatedly.
    large = make(875000)
    for i in range(500):
        large.put(i.to_bytes(4, "little"))
    serialized = large.dumps()
    second = large.copy()
    second.put(b"second-filter")
    if args.backend == "baseline":
        load = lambda: BloomFilter.loads(serialized, BYTE_ARRAY_FUNNEL)
    else:
        load = lambda: BloomFilter.loads(
            serialized, BYTE_ARRAY_FUNNEL, backend=args.backend
        )
    for name, task in {
        "dump_1MiB": large.dumps,
        "load_1MiB": load,
        "statistics_1MiB": large.expected_fpp,
        "merge_repeat_1MiB": lambda: large.put_all(second),
    }.items():
        raw = [
            value / args.number
            for value in timeit.repeat(task, number=args.number, repeat=args.repeat)
        ]
        measurements[name] = {
            "median_seconds": statistics.median(raw),
            "raw_seconds": raw,
        }
    report = {
        "backend": args.backend,
        "python": sys.version,
        "platform": platform.platform(),
        "package_path": str(args.package_path.resolve()),
        "repeat": args.repeat,
        "number": args.number,
        "short_filter_capacity": 5000,
        "fpp": 0.01,
        "keys_per_batch": 500,
        "large_filter_bytes": len(serialized),
        "fingerprints": fingerprints,
        "notes": [
            "Fresh insertion includes constructing an empty filter.",
            "Repeated insertion and merge operate on already populated filters.",
            "Query misses are absent keys and may include false positives.",
            "Operations return full serialized bytes for dump/load.",
        ],
        "measurements": measurements,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                name: round(value["median_seconds"] * 1000, 3)
                for name, value in measurements.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
