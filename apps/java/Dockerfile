# syntax=docker/dockerfile:1
# aad-java: spring-petclinic-rest on JDK 25, multi-arch. Pins verified 2026-09-03 (see README.md).
#   source: spring-petclinic-rest master @ 4cd8e1b0cd42578e882247d8801f6be5d402f118 (2026-09-01),
#           project version 4.0.2 on Spring Boot 4.1.1 (the v4.0.2 git tag still points at Boot 4.0.2)
#   build:  maven:3.9.16-eclipse-temurin-25-noble (pom enforces Maven >= 3.9.9; amd64+arm64)
#   run:    eclipse-temurin:25.0.4_7-jre-noble (amd64+arm64)
# The jar is architecture independent, so Maven runs once on the build host
# (--platform=$BUILDPLATFORM) and buildx copies it into each runtime stage.
FROM --platform=$BUILDPLATFORM maven:3.9.16-eclipse-temurin-25-noble AS build
ARG PETCLINIC_SHA=4cd8e1b0cd42578e882247d8801f6be5d402f118
# Fix round 1, Important 2: the SHA in the URL pins the commit, but GitHub's
# archive/*.tar.gz bytes are not itself content-addressed, so ADD --checksum
# pins the tarball's own SHA-256 (verified twice, 2026-09-03, five seconds
# apart, both downloads matched). ADD --checksum needs Dockerfile syntax
# >= 1.6 and a sha256:<hex> value for HTTP sources; verified 2026-09-03
# against https://docs.docker.com/reference/dockerfile/ ("For git repository
# sources, the checksum is the commit SHA... For sources fetched over HTTP,
# the checksum is the SHA-256 content digest, formatted as sha256:<hash>. Only
# SHA256 is supported."); "# syntax=docker/dockerfile:1" is the version Docker
# recommends ("always points to the latest stable release of the version 1
# syntax"), which satisfies the >= 1.6 requirement.
ADD --checksum=sha256:c0ebdc167cfe8dedd438b274ca8ec74847d8da74c5e06731eac712115d2edf3a \
    https://github.com/spring-petclinic/spring-petclinic-rest/archive/${PETCLINIC_SHA}.tar.gz /tmp/src.tgz
RUN mkdir -p /src && tar -xzf /tmp/src.tgz -C /src --strip-components=1
WORKDIR /src
# -DskipTests: upstream CI covers them on JDK 17; the runtime JDK is what this image tests.
RUN mvn -q -B -DskipTests package && cp target/spring-petclinic-rest-*.jar /app.jar

FROM eclipse-temurin:25.0.4_7-jre-noble
COPY --from=build /app.jar /app/app.jar
# Controls, identical in every cell (not knobs):
#   SPRING_JPA_SHOW_SQL=false  the h2 profile ships show-sql=true; logging each statement is not the workload
#   JAVA_TOOL_OPTIONS empty    heap and JIT/THP flags come from the per-cell overlay (Task 5), never from the image
ENV SPRING_JPA_SHOW_SQL=false \
    JAVA_TOOL_OPTIONS=""
EXPOSE 9966
USER 1000:1000
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
