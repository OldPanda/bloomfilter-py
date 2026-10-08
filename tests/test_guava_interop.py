import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from bloomfilter import (
    BYTE_ARRAY_FUNNEL,
    INTEGER_FUNNEL,
    LONG_FUNNEL,
    UTF8_STRING_FUNNEL,
    BloomFilter,
    Funnel,
)


class GuavaInteropTest(unittest.TestCase):
    CASES = (
        ("integer", INTEGER_FUNNEL, (-(2**31), -1, 0, 1, 2**31 - 1)),
        ("long", LONG_FUNNEL, (-(2**63), -(2**31) - 1, 0, 2**31, 2**63 - 1)),
        ("string", UTF8_STRING_FUNNEL, ("", "hello", "雪", "emoji 😀")),
        ("bytes", BYTE_ARRAY_FUNNEL, (b"", b"\x00\x01\xff", "雪".encode())),
    )

    @classmethod
    def setUpClass(cls) -> None:
        guava_jar = os.environ.get("GUAVA_JAR")
        java = shutil.which("java")
        javac = shutil.which("javac")
        if not guava_jar or not Path(guava_jar).is_file() or not java or not javac:
            raise unittest.SkipTest(
                "set GUAVA_JAR and install a JDK to run Guava integration tests"
            )

        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls._class_directory = Path(cls._temporary_directory.name)
        source = Path(__file__).parent / "java" / "GuavaBloomFilterInterop.java"
        subprocess.run(
            [javac, "-cp", guava_jar, "-d", str(cls._class_directory), str(source)],
            check=True,
        )
        cls._java = java
        cls._classpath = os.pathsep.join((str(cls._class_directory), guava_jar))

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "_temporary_directory"):
            cls._temporary_directory.cleanup()

    def run_helper(self, operation: str, funnel_name: str, path: Path) -> None:
        subprocess.run(
            [
                self._java,
                "-cp",
                self._classpath,
                "GuavaBloomFilterInterop",
                operation,
                funnel_name,
                str(path),
            ],
            check=True,
        )

    def test_guava_writes_python_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for funnel_name, funnel, values in self.CASES:
                with self.subTest(funnel=funnel_name):
                    path = Path(directory) / f"guava-{funnel_name}.bin"
                    self.run_helper("write", funnel_name, path)
                    serialized = path.read_bytes()

                    bloom_filter = BloomFilter.loads(serialized, funnel=funnel)
                    for value in values:
                        self.assertTrue(bloom_filter.might_contain(value))
                    self.assertEqual(bloom_filter.dumps(), serialized)

    def test_python_writes_guava_reads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for funnel_name, funnel, values in self.CASES:
                with self.subTest(funnel=funnel_name):
                    path = Path(directory) / f"python-{funnel_name}.bin"
                    bloom_filter = self.create_filter(funnel, values)
                    path.write_bytes(bloom_filter.dumps())

                    self.run_helper("read", funnel_name, path)

    @staticmethod
    def create_filter(funnel: Funnel, values: tuple) -> BloomFilter:
        bloom_filter = BloomFilter(100, 0.01, funnel=funnel)
        for value in values:
            bloom_filter.put(value)
        return bloom_filter
