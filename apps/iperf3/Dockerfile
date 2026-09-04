# aad-iperf3: minimal multi-arch iperf3 for the network cell (spec section 4).
# Pins verified 2026-09-03: alpine:3.24.1 (released 2026-06-09, amd64+arm64),
# iperf3 3.20-r0 in Alpine v3.24 main for both x86_64 and aarch64
# (https://pkgs.alpinelinux.org/packages?name=iperf3&branch=v3.24).
# 3.20 >= 3.16, so -P spawns one thread per stream (iperf3(1) man page).
FROM alpine:3.24.1
RUN apk add --no-cache iperf3=3.20-r0
EXPOSE 5201
# Non-root (fix round 1, Important 1): iperf3 only needs network I/O, no
# privileged port or filesystem writes, so a bare numeric UID:GID is enough
# (matches apps/go and apps/java, which already run non-root).
USER 1000:1000
ENTRYPOINT ["iperf3"]
