#!/usr/bin/env bash
# aad build pipeline: buildx multi-arch build for the four apps/ images.
# Docs verified 2026-09-04:
#   https://docs.docker.com/reference/cli/docker/buildx/build/
#     --platform "Set the target platform for the build."
#     --push     "Shorthand for --output=type=registry."
#     --output=type=oci,dest=<path>  "writes the result image or manifest
#       list as an OCI image layout tarball on the client."
#   https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/
#     `docker buildx imagetools inspect NAME` shows the manifest list,
#     including one entry per platform, straight from the registry.
#   --provenance=false --sbom=false: "by default, a minimal provenance
#     attestation will be created for the build result" (--provenance docs);
#     this lab doesn't need supply-chain attestations, and skipping them
#     keeps the OCI index a flat, one-manifest-per-platform list.
#
# PUSH=0 (default): no registry involved. Builds to a local OCI tarball per
# image and asserts the tarball's index.json lists the expected platforms.
# PUSH=1 (GATED, speaker-only): pushes to GHCR and runs imagetools inspect
# against the registry so both manifests are visible.
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io/andrezc98}"
TAG="${TAG:-$(date +%F)}"
PUSH="${PUSH:-0}"
OUT_DIR="${OUT_DIR:-./build-out}"

# ECR fallback for the sandbox account (commented, no account id, no push):
# REGISTRY=<account-id>.dkr.ecr.us-east-1.amazonaws.com
# aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$REGISTRY"

cd "$(dirname "$0")"

# All four images need a builder that can build for a foreign platform and
# export multi-platform results (the default "docker" driver builder cannot).
# `aad` is created once with the docker-container driver; --bootstrap is a
# no-op if it already exists and is running.
docker buildx inspect aad --bootstrap >/dev/null 2>&1 || docker buildx create --name aad --driver docker-container --bootstrap

platforms_for() {
  case "$1" in
    ycsb) echo "linux/amd64" ;;
    *)    echo "linux/amd64,linux/arm64" ;;
  esac
}

# Positional args select a subset of images; default is all four.
images=(java go iperf3 ycsb)
if [ "$#" -gt 0 ]; then
  images=("$@")
fi

mkdir -p "$OUT_DIR"

for name in "${images[@]}"; do
  platforms="$(platforms_for "$name")"
  ref="$REGISTRY/aad-$name:$TAG"
  echo "=== building $ref ($platforms) ==="

  if [ "$PUSH" = "1" ]; then
    docker buildx build --builder aad --platform "$platforms" --tag "$ref" \
      --provenance=false --sbom=false --push "./$name"
    echo "=== imagetools inspect $ref ==="
    docker buildx imagetools inspect --builder aad "$ref"
  else
    tar_path="$OUT_DIR/aad-$name.tar"
    docker buildx build --builder aad --platform "$platforms" --tag "$ref" \
      --provenance=false --sbom=false \
      --output "type=oci,dest=$tar_path" "./$name"

    # A multi-platform OCI image layout wraps its per-platform manifests in
    # one extra index level (index.json points, by digest, at the real
    # manifest-list blob); a single-platform build has no such extra level.
    # Walk index.json, following one hop into any nested index, then list
    # the platform of every image manifest found.
    got="$(python3 -c '
import json, sys, tarfile
tar = tarfile.open(sys.argv[1])
def read_json(member):
    return json.load(tar.extractfile(member))
platforms = []
for entry in read_json("index.json")["manifests"]:
    if entry["mediaType"] == "application/vnd.oci.image.index.v1+json":
        digest = entry["digest"].split(":", 1)[1]
        nested = read_json(f"blobs/sha256/{digest}")["manifests"]
    else:
        nested = [entry]
    for m in nested:
        p = m.get("platform")
        if p:
            platforms.append(p["os"] + "/" + p["architecture"])
print(",".join(sorted(platforms)))
' "$tar_path")"
    want="$(echo "$platforms" | tr ',' '\n' | sort | tr '\n' ',' | sed 's/,$//')"
    echo "expected platforms: $want"
    echo "found platforms:    $got"
    if [ "$got" != "$want" ]; then
      echo "ERROR: $tar_path platforms mismatch (expected [$want], got [$got])" >&2
      exit 1
    fi
  fi
done
