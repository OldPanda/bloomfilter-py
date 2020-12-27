from setuptools import setup, find_packages

version = "0.0.2"
install_requires = ["bitarray==1.6.1", "murmurhash3==2.3.5"]
extras_require = {}

setup(
    name="bloomfilter-py",
    version=version,
    description="Yet another bloomfilter implementation in Python",
    long_description=open("README.md").read(),
    author="OldPanda",
    author_email="me@old-panda.com",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*")),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require=extras_require,
)
