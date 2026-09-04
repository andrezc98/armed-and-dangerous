# aad-ycsb: go-ycsb (pingcap) with the mongodb backend, runs on the loader node.
# Pins verified 2026-09-03:
#   go-ycsb v1.0.3 = commit f030f9942393a8febbf4365c2d582711723159f5 (released 2025-12-31,
#   current master HEAD; https://github.com/pingcap/go-ycsb/releases). go.mod says go 1.18,
#   Makefile builds with `go build -o bin/go-ycsb cmd/go-ycsb/*`; no cgo without TAGS.
#   golang:1.27.1 and alpine:3.24.1 as in the sibling images.
# Upstream Dockerfile hardcodes an amd64 dumb-init binary, so it is not reused.
# The Dockerfile is arch-agnostic; the loader is x86 today, so build-multiarch.sh
# pushes linux/amd64 only.
FROM --platform=$BUILDPLATFORM golang:1.27.1 AS build
ARG TARGETOS TARGETARCH
ARG GO_YCSB_COMMIT=f030f9942393a8febbf4365c2d582711723159f5
WORKDIR /src
RUN git clone --quiet https://github.com/pingcap/go-ycsb.git . \
 && git checkout --quiet ${GO_YCSB_COMMIT}
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags='-s -w' -o /out/go-ycsb ./cmd/go-ycsb

FROM alpine:3.24.1
COPY --from=build /out/go-ycsb /usr/local/bin/go-ycsb
COPY --from=build /src/workloads /workloads
# Usage (Task 5 Jobs):
#   go-ycsb load mongodb -P /workloads/workloada -p mongodb.url=mongodb://mongo.aad.svc:27017/ycsb?w=1 -p recordcount=N --threads T
#   go-ycsb run  mongodb -P /workloads/workloadb -p mongodb.url=...            -p operationcount=N --threads T --target OPS
# Non-root (fix round 1, Important 1): go-ycsb only reads /workloads and talks
# to the target DB over the network, so a bare numeric UID:GID is enough
# (matches apps/go and apps/java, which already run non-root).
USER 1000:1000
ENTRYPOINT ["go-ycsb"]
