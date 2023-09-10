import os

guava_file_dir: str = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "guava_dump_files"
)


def read_data(filename: str) -> bytes:
    """
    Read Bloomfilter serialized data from Guava's dump file.

    :param filename: Guava dump file name.
    :type filename: str
    """
    with open(os.path.join(guava_file_dir, filename), "rb") as f:
        return f.read()
