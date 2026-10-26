# Benchmarks

Resistor meshes, DC operating point, measured with `python tools/benchmark.py`.

| Nodes | Parts | Parse | Dense solve | Sparse solve | Max difference |
|---:|---:|---:|---:|---:|---:|
| 9 | 14 | 0.1 ms | 0.2 ms | 0.2 ms | 3.3e-16 V |
| 100 | 182 | 0.9 ms | 1.9 ms | 0.6 ms | 3.7e-15 V |
| 1,024 | 1,986 | 9.5 ms | 20.4 ms | 5.0 ms | 4.5e-14 V |
| 10,000 | 19,802 | 104.5 ms | (skipped: 800 MB matrix) | 58.5 ms | - |
