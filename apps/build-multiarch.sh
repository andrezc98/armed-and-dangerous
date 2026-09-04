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
#   `docker buildx imagetools inspect --format` "Format the output using the
#     given Go template", default `{{.Manifest}}`; `{{json .Manifest}}` renders
#     the manifest list as JSON, whose `digest` is the manifest-list digest.
#   https://docs.aws.amazon.com/AmazonECR/latest/userguide/registry_auth.html
#     `aws ecr get-login-password --region <region> | docker login --username AWS
#      --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com` -
#     verbatim from "Private registry authentication in Amazon ECR"; the token
#     "is valid for 12 hours".
#   https://docs.aws.amazon.com/cli/latest/reference/ecr/get-login-password.html
#     CLI command reference synopsis: `get-login-password [--debug] [--region
#     <value>] ...` - no positional or required argument beyond the options
#     above; `--region` is what this script always passes explicitly.
#
# PUSH=0 (default): no registry involved. Builds to a local OCI tarball per
# image, tagged with the bare name the manifests use, and asserts the tarball's
# index.json lists the expected platforms.
# PUSH=1 (GATED, speaker-only): pushes to the four private ECR repositories of
# the sandbox account (infra/ecr), runs imagetools inspect against the registry
# so both manifests are visible, and MERGES the tag and digest of the image(s)
# it built into ../results/images.json (one tag per image - a rebuild of one
# image must never move the tag the other three are already deployed at); it
# refuses to write a file that would end up with fewer than the four images
# (infra/ecr/README.md, "same-day re-push").
set -euo pipefail

TAG="${TAG:-$(date +%F)}"
PUSH="${PUSH:-0}"
OUT_DIR="${OUT_DIR:-./build-out}"
REGION="${REGION:-us-east-1}"
# Empty by default: with PUSH=0 the images are tagged `aad-<name>:<tag>`, which
# is exactly what the manifests carry, and no registry has to exist.
REGISTRY="${REGISTRY:-}"

# The GHCR form this used to have, kept as the alternative:
# REGISTRY=ghcr.io/<owner> PUSH=1 ./build-multiarch.sh
# echo "$GITHUB_TOKEN" | docker login ghcr.io --username <owner> --password-stdin
# It is not the lab's path any more: ECR pulls from inside the region with the
# node IAM role and needs no registry secret in the cluster (infra/ecr/README.md).

cd "$(dirname "$0")"

# Empty REGISTRY (derive it from the caller's sandbox account) or an explicit
# one that is already an ECR host: either way this is the ECR path, and it
# always needs the sandbox profile and a docker login - an explicit
# REGISTRY=<account>.dkr.ecr... does not get to skip either just because it
# was spelled out instead of derived. Only a REGISTRY that is NOT an ECR host
# (the GHCR alternative above) takes the script off the ECR path entirely, and
# then the docker login is the caller's own job.
if [ "$PUSH" = "1" ]; then
  case "$REGISTRY" in
    "" | *.dkr.ecr.*)
      # Bash mirror of runner/config.py require_sandbox(): a push goes to the
      # speaker's sandbox account or it does not go.
      case "${AWS_PROFILE:-}" in
        *sandbox*) ;;
        *) echo "ERROR: AWS_PROFILE must be the personal sandbox profile (name contains 'sandbox'); refusing to push with default credentials" >&2
           exit 1 ;;
      esac
      if [ -z "$REGISTRY" ]; then
        # No --region here on purpose: sts is a global endpoint, and the region
        # that matters is the one baked into the registry host below, which is
        # $REGION (us-east-1, the lab's region) and never the profile's default.
        ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
        REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
      fi
      aws ecr get-login-password --region "$REGION" \
        | docker login --username AWS --password-stdin "$REGISTRY"
      ;;
    *) ;;
  esac
fi

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

digests=()

for name in "${images[@]}"; do
  platforms="$(platforms_for "$name")"
  ref="${REGISTRY:+$REGISTRY/}aad-$name:$TAG"
  echo "=== building $ref ($platforms) ==="

  if [ "$PUSH" = "1" ]; then
    docker buildx build --builder aad --platform "$platforms" --tag "$ref" \
      --provenance=false --sbom=false --push "./$name"
    echo "=== imagetools inspect $ref ==="
    docker buildx imagetools inspect --builder aad "$ref"
    # Only the sha256: value, never the ref: ../results/images.json is committed
    # and must carry no account data.
    digests+=("aad-$name" "$(docker buildx imagetools inspect --builder aad \
      --format '{{json .Manifest}}' "$ref" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])')")
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

if [ "$PUSH" = "1" ]; then
  # The one thing the runner reads out of a push: which tag is in ECR, PER
  # image. The registry is NOT in here - it carries the account id and it
  # reaches the runner through the git-ignored results/<date>/ecr.json instead.
  #
  # MERGE, never overwrite: a positional-args run only rebuilds a subset (one
  # image, on a same-day IMMUTABLE re-push - infra/ecr/README.md), and the
  # other images already deployed must keep the tag they actually have in ECR.
  # Overwriting the whole file with a single top-level tag used to repoint all
  # four at a tag only the rebuilt one carries, which is an ImagePullBackOff on
  # a billing node group. Refuses outright, instead of warning and writing a
  # partial file, if the merged result would still be short of all four -
  # results/images.json is committed and a short file silently ships that gap
  # to the next lab day.
  mkdir -p ../results
  python3 -c '
import json, sys, time

path = "../results/images.json"
tag, pairs = sys.argv[1], sys.argv[2:]
built = dict(zip(pairs[::2], pairs[1::2]))  # name -> digest, only what this run built

try:
    existing = json.load(open(path))
except FileNotFoundError:
    existing = {}
images = existing.get("images", {})
images.update({name: {"tag": tag, "digest": digest} for name, digest in built.items()})

expected = ["aad-java", "aad-go", "aad-iperf3", "aad-ycsb"]
missing = sorted(set(expected) - images.keys())
if missing:
    missing_str = ", ".join(missing)
    sys.exit(
        f"refusing to write {path}: it would end up with {len(images)}/{len(expected)} "
        f"image(s), missing {missing_str}. Build the missing ones too before "
        "committing, e.g. run apps/build-multiarch.sh with no positional args."
    )

json.dump(
    {"tag": tag, "pushed": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "images": images},
    open(path, "w"), indent=1, sort_keys=True,
)
open(path, "a").write("\n")
' "$TAG" "${digests[@]}"
  echo "=== merged ../results/images.json: $TAG for ${images[*]/#/aad-} ==="
fi
