"""Tiny fixture project used by the benchmark suite tests."""

import math


def fib(n: int) -> int:
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


class Greeter:
    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        return f"Mae govannen, {self.name}!"


def compute(values: list[int]) -> list[int]:
    return [math.floor(math.sqrt(item)) for item in values]


if __name__ == "__main__":
    print(Greeter("Aragorn").greet())
