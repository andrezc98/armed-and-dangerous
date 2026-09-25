#!/usr/bin/env bash
# llama.cpp server for arm64 with Arm KleidiAI micro-kernels compiled in.
#
# The official image (ghcr.io/ggml-org/llama.cpp:server-b10775) is built with
# GGML_CPU_ALL_VARIANTS and no KleidiAI, while its x86 build carries AMX: on
# calibration day 2026-09-24 system_info read AMX_INT8 = 1 on the Xeon and no
# KLEIDIAI on Graviton. This builds the SAME pinned tag from llama.cpp's own
# .devops/cpu.Dockerfile, target `server`, adding exactly one flag to its cmake
# line: -DGGML_CPU_KLEIDIAI=ON (docs/build.md at b10775, "Arm KleidiAI": valid
# only for AArch64; runtime still picks the best kernel per op).
#
#   apps/llama/build-kleidiai.sh              # build and load locally (arm64 host)
#   PUSH=<registry> apps/llama/build-kleidiai.sh   # also push <registry>/aad-llama:<tag>
set -euo pipefail

REF=b10775
TAG=${TAG:-$REF-kleidiai}
SRC=apps/build-out/llama.cpp-$REF

if [ ! -d "$SRC" ]; then
  git clone --quiet --depth 1 --branch "$REF" https://github.com/ggml-org/llama.cpp "$SRC"
fi
DOCKERFILE=$SRC/.devops/cpu.Dockerfile
grep -q 'GGML_CPU_KLEIDIAI' "$DOCKERFILE" ||
  sed -i.orig 's/-DGGML_CPU_ALL_VARIANTS=ON;/-DGGML_CPU_ALL_VARIANTS=ON -DGGML_CPU_KLEIDIAI=ON;/' "$DOCKERFILE"
grep -q -- '-DGGML_CPU_KLEIDIAI=ON;' "$DOCKERFILE" || { echo "cmake line not patched" >&2; exit 1; }

OUT=(--load)
[ -n "${PUSH:-}" ] && OUT=(--push --provenance=false --sbom=false)
docker buildx build --platform linux/arm64 --target server \
  -f "$DOCKERFILE" -t "${PUSH:-local}/aad-llama:$TAG" "${OUT[@]}" "$SRC"
