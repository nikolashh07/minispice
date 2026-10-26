"""Phase 19 benchmark: time MiniSpice on resistor meshes of 10 to 10,000 nodes.

    python tools/benchmark.py            prints a table (and writes docs/benchmarks.md)
    python tools/benchmark.py --profile  also profiles the 10,000-node solve
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minispice import operating_point, parse  # noqa: E402

SIZES = (10, 100, 1000, 10000)
DENSE_LIMIT = 2000  # a dense 10,000 x 10,000 matrix would need 800 MB


def mesh_netlist(nodes):
    """A square grid of 1k resistors, driven by 1 V at one corner and grounded at the other."""
    side = max(2, round(math.sqrt(nodes)))
    lines = ["* resistor mesh", "V1 n0_0 0 1"]
    count = 0
    for r in range(side):
        for c in range(side):
            if c + 1 < side:
                count += 1
                lines.append(f"R{count} n{r}_{c} n{r}_{c + 1} 1k")
            if r + 1 < side:
                count += 1
                lines.append(f"R{count} n{r}_{c} n{r + 1}_{c} 1k")
    lines.append(f"RGND n{side - 1}_{side - 1} 0 1k")
    return "\n".join(lines), side * side


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def run():
    # Import scipy once before timing, so the first row doesn't include its import time.
    operating_point(parse(mesh_netlist(10)[0]), sparse=True)
    rows = []
    for size in SIZES:
        text, nodes = mesh_netlist(size)
        circuit, t_parse = timed(lambda: parse(text))
        sparse, t_sparse = timed(lambda: operating_point(circuit, sparse=True))
        if nodes <= DENSE_LIMIT:
            dense, t_dense = timed(lambda: operating_point(circuit, sparse=False))
            diff = max(abs(a - b) for a, b in zip(dense.x, sparse.x))
        else:
            t_dense, diff = None, None
        rows.append((nodes, len(circuit.components), t_parse, t_dense, t_sparse, diff))
    return rows


def table(rows):
    lines = [
        "| Nodes | Parts | Parse | Dense solve | Sparse solve | Max difference |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for nodes, parts, t_parse, t_dense, t_sparse, diff in rows:
        dense = f"{t_dense * 1e3:.1f} ms" if t_dense is not None else "(skipped: 800 MB matrix)"
        difference = f"{diff:.1e} V" if diff is not None else "-"
        lines.append(f"| {nodes:,} | {parts:,} | {t_parse * 1e3:.1f} ms | {dense} | {t_sparse * 1e3:.1f} ms | {difference} |")
    return "\n".join(lines)


def main():
    rows = run()
    text = table(rows)
    print(text)
    out = os.path.join(os.path.dirname(__file__), "..", "docs", "benchmarks.md")
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("# Benchmarks\n\nResistor meshes, DC operating point, measured with `python tools/benchmark.py`.\n\n")
        handle.write(text + "\n")
    if "--profile" in sys.argv:
        import cProfile
        import pstats

        circuit = parse(mesh_netlist(SIZES[-1])[0])
        cProfile.runctx("operating_point(circuit)", globals(), {"circuit": circuit, "operating_point": operating_point}, "bench.prof")
        pstats.Stats("bench.prof").sort_stats("cumulative").print_stats(15)
        os.remove("bench.prof")


if __name__ == "__main__":
    main()
