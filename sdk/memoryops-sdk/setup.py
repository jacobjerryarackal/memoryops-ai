from setuptools import setup, find_packages

setup(
    name="memoryops-sdk",
    version="0.1.0",
    description="Python client SDK for the MemoryOps AI Platform",
    author="MemoryOps Team",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
)
