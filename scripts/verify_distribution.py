"""Check built artifacts and install the wheel offline in a fresh environment."""

import email
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


def main():
    directory = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Expected exactly one wheel and sdist"
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert wheel.testzip() is None
        names = wheel.namelist()
        assert "bloomfilter/py.typed" in names
        metadata = email.message_from_bytes(
            wheel.read(next(n for n in names if n.endswith("/METADATA")))
        )
        requirements = metadata.get_all("Requires-Dist") or []
        assert all("extra ==" in req for req in requirements), requirements
        assert len(requirements) == 2, requirements
        assert metadata["Requires-Python"] == ">=3.8"
        assert any(n.endswith("/LICENSE") for n in names)
        assert not any(
            n.startswith(("tests/", "benchmarks/", "scripts/")) for n in names
        )
    with tarfile.open(sources[0]) as source:
        names = source.getnames()
        assert any(n.endswith("/tests/data/murmur3-vectors.json") for n in names)
        assert any(
            n.endswith("/tests/java/GuavaBloomFilterInterop.java") for n in names
        )
        assert any(n.endswith("/benchmarks/benchmark_backends.py") for n in names)
        assert any(n.endswith("/scripts/verify_distribution.py") for n in names)
        assert not any("/.git/" in n or "/.venv/" in n for n in names)
    with tempfile.TemporaryDirectory() as temp:
        env = Path(temp) / "clean-env"
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                str(wheels[0]),
            ],
            check=True,
        )
        smoke = """
import importlib.util
from importlib.metadata import requires, version
from pathlib import Path
import sys
import bloomfilter
from bloomfilter import BloomFilter, INTEGER_FUNNEL
assert Path(sys.prefix) in Path(bloomfilter.__file__).parents
assert importlib.util.find_spec('bitarray') is None
assert importlib.util.find_spec('mmh3') is None
assert all('extra ==' in req for req in requires('bloomfilter-py') or [])
b = BloomFilter(100, .01, funnel=INTEGER_FUNNEL)
for value in (-2**31, 0, 42, 2**31-1):
    b.put(value)
loaded = BloomFilter.loads(b.dumps(), INTEGER_FUNNEL)
assert loaded == b and loaded.backend == 'python'
for value in (-2**31, 0, 42, 2**31-1):
    assert value in loaded
try:
    BloomFilter(1,.01,backend='native')
except ImportError:
    pass
else:
    raise AssertionError('native mode should require explicit extras')
print('Installed wheel verified:', version('bloomfilter-py'), bloomfilter.__file__)
"""
        subprocess.run([str(python), "-I", "-c", smoke], cwd=temp, check=True)
    print(
        "Wheel and sdist contents, optional-only requirements, and offline clean installation: OK"
    )


if __name__ == "__main__":
    main()
