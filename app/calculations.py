"""Decimal-safe calculations; never delegate arithmetic to a language model."""
from decimal import Decimal
from functools import reduce


def decimal(value):
    return Decimal(str(value))


def percentage_change(start, end):
    start, end = decimal(start), decimal(end)
    if start == 0:
        raise ValueError("Percentage change is undefined for a zero starting value")
    return (end / start - 1) * 100


def compound(returns):
    if not returns:
        raise ValueError("At least one periodic return is required")
    return (reduce(lambda a, r: a * (1 + decimal(r) / 100), returns, Decimal(1)) - 1) * 100


def difference(fund, benchmark):
    return decimal(fund) - decimal(benchmark)


def display(value, places=2):
    return f"{decimal(value):,.{places}f}"
