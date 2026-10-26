"""Compare actual BloomFilter behavior against a separate baseline checkout.

The audit returns success when it ran correctly, even when compatibility is
false. A change to the expected core operations is treated as a regression and
fails the audit; extension-interface changes are recorded for version choice.
Run with a Python environment containing the baseline's bitarray/mmh3 packages.
"""

import argparse
import inspect
import io
import json
from pathlib import Path
import subprocess
import sys


def snapshot(checkout, backend):
    sys.path.insert(0, str(checkout.resolve()))
    import bitarray as external
    from bloomfilter import (
        BloomFilter,
        INTEGER_FUNNEL,
        LONG_FUNNEL,
        UTF8_STRING_FUNNEL,
        BYTE_ARRAY_FUNNEL,
        LEGACY_FUNNEL,
        StringFunnel,
    )
    from bloomfilter.bloomfilter_strategy import MURMUR128_MITZ_32, MURMUR128_MITZ_64

    options = {} if backend == "original" else {"backend": backend}

    def make(*args, **kwargs):
        return BloomFilter(*args, **kwargs, **options)

    cases = [
        (INTEGER_FUNNEL, [-(2**31), -1, 0, 42, 2**31 - 1], list(range(500, 550))),
        (LONG_FUNNEL, [-(2**63), -1, 0, 2**40, 2**63 - 1], list(range(500, 550))),
        (
            UTF8_STRING_FUNNEL,
            ["", "雪", "emoji 😀", "\ud800", "\ud83d\ude00"],
            ["probe-" + str(i) for i in range(50)],
        ),
        (
            StringFunnel("utf-16"),
            ["", "雪", "emoji 😀", "\ud800", "\ud83d\ude00"],
            ["probe-" + str(i) for i in range(50)],
        ),
        (
            BYTE_ARRAY_FUNNEL,
            [b"", b"\x00\x01\xff", bytes(range(256))],
            [str(i).encode() for i in range(50)],
        ),
        (
            LEGACY_FUNNEL,
            [True, False, 42, -(2**40), "雪"],
            ["probe-" + str(i) for i in range(50)],
        ),
    ]

    class ShortStream(io.BytesIO):
        def read(self, size=-1):
            return super().read(min(3, size))

        def write(self, data):
            return super().write(data[:3])

    core = {"filters": []}
    for strategy in (MURMUR128_MITZ_32, MURMUR128_MITZ_64):
        for funnel, values, probes in cases:
            bf = make(100, 0.01, strategy, funnel)
            changed = [bf.put(value) for value in values]
            repeated = [bf.put(value) for value in values]
            raw = bf.dumps()
            loaded = [
                BloomFilter.loads(raw, funnel, **options),
                BloomFilter.loads_from_hex(raw.hex(), funnel, **options),
                BloomFilter.loads_from_base64(bf.dumps_to_base64(), funnel, **options),
            ]
            assert all(value in result for result in loaded for value in values)
            assert all(result == bf for result in loaded)
            output = ShortStream()
            bf.write_to(output)
            assert not output.closed and output.getvalue() == raw
            stream = ShortStream(raw + b"trailer")
            streamed = BloomFilter.read_from(stream, funnel, **options)
            assert streamed == bf and stream.tell() == len(raw) and not stream.closed
            copy = bf.copy()
            assert copy == bf and copy.data is not bf.data
            extra = make(100, 0.01, strategy, funnel)
            extra.put(probes[0])
            source = extra.dumps()
            assert copy.is_compatible(extra)
            copy.put_all(extra)
            assert extra.dumps() == source
            core["filters"].append(
                {
                    "strategy": strategy.ordinal(),
                    "funnel": type(funnel).__name__,
                    "changed": changed,
                    "repeated": repeated,
                    "dump": raw.hex(),
                    "merged": copy.dumps_to_hex(),
                    "probes": [bf.might_contain(value) for value in probes],
                    "fpp": bf.expected_fpp(),
                    "count": bf.approximate_element_count(),
                    "size": bf.serialized_size(),
                }
            )

    class CustomHash(MURMUR128_MITZ_64):
        @classmethod
        def hash_key(cls, key, funnel=LEGACY_FUNNEL):
            return 1, 2

    custom = make(100, 0.01, CustomHash)
    core["custom_hash_override"] = [
        custom.put("a"),
        custom.might_contain("b"),
        custom.dumps_to_hex(),
    ]
    core["sizing"] = [
        [
            BloomFilter.num_of_bits(n, p),
            BloomFilter.num_of_hash_functions_for_error_rate(p),
        ]
        for n, p in ((0, 0.01), (1, 0.03), (500, 0.01), (100000, 0.001))
    ]
    core["zero_capacity"] = make(0, 0.01).dumps_to_hex()
    core["invalid_input_errors"] = []
    for args in ((-1, 0.01), (10, 0), (10, 1), (10, float("nan"))):
        try:
            make(*args)
        except (ValueError, TypeError) as exc:
            core["invalid_input_errors"].append(type(exc).__name__)
        else:
            core["invalid_input_errors"].append("accepted")
    bf = make(1, 0.01)
    interface = {
        "data_type": type(bf.data).__module__ + "." + type(bf.data).__name__,
        "data_is_third_party_bitarray": isinstance(bf.data, external.bitarray),
        "data_has_to01": callable(getattr(bf.data, "to01", None)),
    }
    try:
        memoryview(bf.data)
    except TypeError:
        interface["data_supports_buffer_protocol"] = False
    else:
        interface["data_supports_buffer_protocol"] = True
    raw = external.bitarray(64)
    raw.setall(0)
    bf.setup(1, raw, MURMUR128_MITZ_64)
    interface["setup_retains_input_identity"] = bf.data is raw
    raw[5] = 1
    interface["external_mutation_visible_after_setup"] = bool(bf.data[5])
    bf.data[6] = 1
    interface["filter_mutation_visible_in_external_input"] = bool(raw[6])
    methods = {
        name
        for name in dir(BloomFilter)
        if not name.startswith("_") and callable(getattr(BloomFilter, name))
    }
    signatures = {}
    for name in sorted(methods | {"__init__"}):
        signatures[name] = [
            {
                "name": p.name,
                "kind": p.kind.name,
                "required": p.default is inspect.Parameter.empty,
            }
            for p in inspect.signature(getattr(BloomFilter, name)).parameters.values()
        ]
    return {
        "checkout": str(checkout.resolve()),
        "backend": backend,
        "core": core,
        "extension_interfaces": interface,
        "signatures": signatures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--backend", choices=("original", "python", "native"))
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.snapshot:
        print(json.dumps(snapshot(args.snapshot, args.backend), ensure_ascii=True))
        return
    if not all((args.baseline, args.candidate, args.output)):
        parser.error("--baseline, --candidate and --output are required")

    def read(path, backend):
        return json.loads(
            subprocess.check_output(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--snapshot",
                    str(path.resolve()),
                    "--backend",
                    backend,
                ],
                text=True,
            )
        )

    baseline = read(args.baseline, "original")
    candidates = [read(args.candidate, mode) for mode in ("python", "native")]
    changes = []
    for candidate in candidates:
        assert candidate["core"] == baseline["core"], (
            "Core behavior regression: " + candidate["backend"]
        )
        for method, parameters in baseline["signatures"].items():
            actual = [
                p for p in candidate["signatures"][method] if p["name"] != "backend"
            ]
            assert actual == parameters, "Existing call signature changed: " + method
        for field, old in baseline["extension_interfaces"].items():
            new = candidate["extension_interfaces"][field]
            if new != old:
                changes.append(
                    {
                        "backend": candidate["backend"],
                        "behavior": field,
                        "baseline": old,
                        "candidate": new,
                    }
                )
    result = {
        "core_behavior_compatible": True,
        "existing_call_signatures_compatible": True,
        "extension_interfaces_compatible": not changes,
        "fully_backward_compatible": not changes,
        "recommended_version": "2.0.0" if changes else "1.4.0",
        "breaking_changes": changes,
        "baseline": baseline,
        "candidates": candidates,
    }
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in ("baseline", "candidates")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
