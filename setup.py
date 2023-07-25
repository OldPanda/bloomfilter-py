from setuptools import find_packages, setup

version = "0.2.1"
install_requires = ["bitarray==2.7.6", "mmh3==3.1.0"]
extras_require = {}

setup(
    name="bloomfilter-py",
    version=version,
    description="Yet another bloomfilter implementation in Python",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="OldPanda",
    author_email="me@old-panda.com",
    url="https://github.com/OldPanda/bloomfilter-py",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*")),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require=extras_require,
)
