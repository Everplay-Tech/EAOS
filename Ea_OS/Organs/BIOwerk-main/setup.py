"""Setup script for BIOwerk Matrix shared library."""

from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="biowerk-matrix",
    version="0.1.0",
    description="Shared library for BIOwerk microservices - Core utilities, models, auth, database, and LLM integration",
    author="BIOwerk Team",
    packages=["matrix"],
    python_requires=">=3.10",
    install_requires=requirements,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)
