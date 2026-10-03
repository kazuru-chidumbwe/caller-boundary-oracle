# Bounded reproduction image for the eMRTD differential harness.
# Goal: one buildable artifact reviewers can run without a hand-tuned host.
#
#   docker build -t emrtd-harness .
#   docker run --rm emrtd-harness                 # make smoke (TC-AC-01)
#   docker run --rm emrtd-harness bash scripts/run_offline_pa.sh
#
# Requires network at build time (gmrtd clone + Maven Central JMRTD 0.8.6).
# Synthetic profiles only — no NFC / physical documents.
# Option A: does NOT clone E3V3A; JMRTD comes from Maven Central and is
# verified by SHA-256 in scripts/install-jmrtd-local.sh.

FROM eclipse-temurin:17-jdk-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    make \
    maven \
    python3 \
    && rm -rf /var/lib/apt/lists/*

ARG GO_VERSION=1.26.5
ARG GO_SHA256=5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053
RUN curl -fsSL -o /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    && echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c - \
    && tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz
ENV PATH="/usr/local/go/bin:/root/go/bin:${PATH}"
ENV GOTOOLCHAIN=local
ENV GOPROXY=https://proxy.golang.org,direct
ENV JMRTD_VERSION=0.8.6

# go.mod replace path expects sibling ../_vendor/gmrtd relative to this tree.
WORKDIR /workspace/emrtd-differential-harness
COPY . .

RUN bash scripts/bootstrap-vendor.sh \
    && bash scripts/install-jmrtd-local.sh \
    && (cd drivers/jmrtd && mvn -q -DskipTests package) \
    && go test ./classifier/... ./middleware/...

CMD ["make", "smoke"]
