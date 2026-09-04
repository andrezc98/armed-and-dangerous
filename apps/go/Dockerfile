# aad-go: Go stdlib baseline. Pins verified 2026-09-03:
#   golang:1.27.1 (go1.27.1 released 2026-09-01, https://go.dev/doc/devel/release; amd64+arm64 on Docker Hub)
#   gcr.io/distroless/static-debian13:nonroot (README: "Distroless images are based on Debian 13 (trixie)";
#   amd64+arm64, https://github.com/GoogleContainerTools/distroless)
# Cross-compiles on the build host instead of emulating: buildx sets TARGETARCH per platform.
FROM --platform=$BUILDPLATFORM golang:1.27.1 AS build
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY go.mod ./
COPY *.go ./
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -ldflags='-s -w' -o /out/aad-go .

FROM gcr.io/distroless/static-debian13:nonroot
COPY --from=build /out/aad-go /aad-go
EXPOSE 8080
USER nonroot
ENTRYPOINT ["/aad-go"]
