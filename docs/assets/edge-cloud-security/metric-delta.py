#!/usr/bin/env python3
"""Compare explicit Prometheus counter families; never fabricate missing zeros."""
import math
import re
import sys
from pathlib import Path


def total(path, name):
    values = []
    pattern = re.compile(r"^" + re.escape(name) + r"(?:\{[^}]*\})?\s+(\S+)(?:\s+\S+)?$")
    for line in Path(path).read_text().splitlines():
        match = pattern.match(line)
        if match:
            value = float(match.group(1))
            if not math.isfinite(value) or value < 0:
                raise ValueError("invalid sample: " + name)
            values.append(value)
    if not values:
        raise ValueError("missing series: " + name)
    result = sum(values)
    if not math.isfinite(result):
        raise ValueError("nonfinite family total: " + name)
    return result


def main():
    if len(sys.argv) < 4:
        raise ValueError("usage: metric-delta.py BEFORE AFTER FAMILY [FAMILY ...]")
    for name in sys.argv[3:]:
        before, after = total(sys.argv[1], name), total(sys.argv[2], name)
        if after < before:
            raise ValueError("counter decreased; inspect reset/generation: " + name)
        delta = after - before
        print(f"{name}: before={before:g} after={after:g} delta={delta:g}")
        if delta <= 0:
            raise ValueError("expected positive delta: " + name)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
