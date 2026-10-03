# Evidence assets (not slides)

- `flamegraphs/java-{arm,amd,x86}-{stock,tuned}.{svg,png}`: Java CPU flame graphs, Task 7 day 3 run 1 (Pyroscope
  export, pruned: small frames fold into "other"). Rebuild:
  `python3 .superpowers/sdd/2026-09-02-armed-and-dangerous/scripts/fg2svg.py results/2026-09-27-task7-d3/java/<cell>/run-1/flamegraph.json <out.svg> "<title>"`.
- `aperf/<workload>-<variant>-arm-amd-x86/index.html` (git-ignored, ~60 MB each): APerf v1.2.3 comparison reports,
  base = m9g, comparisons = m8a, m8i, Task 7 day 3 run 1. Rebuild (Docker, bash):
  `docker run --rm -v "$PWD":/w -w /w public.ecr.aws/aperf/aperf:v1.2.3 aperf report -r /w/<arm tar.gz> -r /w/<amd tar.gz> -r /w/<x86 tar.gz> -n /w/slides/assets/aperf/<name>`.
  Headers show instance IDs, AMI IDs and private hostnames: crop them out of any screenshot.
