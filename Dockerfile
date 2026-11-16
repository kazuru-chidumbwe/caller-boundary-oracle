# Reproduction image for the caller-boundary oracle harness.
#
#   docker build -t caller-boundary-oracle .
#   docker run --rm caller-boundary-oracle                       # make smoke: one profile per library, verified
#   docker run --rm caller-boundary-oracle make evaluate         # every Linux suite, verified
#
# Requires network at build time: pinned library sources (gmrtd, emrtd-dotnet, dmrtd, passauf, OpenPACE,
# vsmartcard) are fetched by the bootstrap scripts, JMRTD 0.8.9 comes from Maven Central and is checked by
# SHA-256. The same steps as the Linux CI workflow. Synthetic and emulated chips only.

FROM eclipse-temurin:17-jdk-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git make maven unzip libicu70 \
    python3 python3-venv python3-dev python3-setuptools python3-pip \
    autoconf automake libtool pkg-config libssl-dev swig gengetopt help2man build-essential \
    && rm -rf /var/lib/apt/lists/*

ARG GO_VERSION=1.26.10
ARG GO_SHA256=ccfe7ae822d2c2f41f4fe7c956199967a4dac22d0ee0d2b2bfdb440aab3b20c5
RUN curl -fsSL -o /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz" \
    && echo "${GO_SHA256}  /tmp/go.tgz" | sha256sum -c - \
    && tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz

ARG RUST_VERSION=1.92.0
RUN curl -fsSL https://sh.rustup.rs -o /tmp/rustup.sh \
    && sh /tmp/rustup.sh -y --profile minimal --default-toolchain "${RUST_VERSION}" && rm /tmp/rustup.sh

ENV PATH="/usr/local/go/bin:/root/go/bin:/root/.cargo/bin:${PATH}"
ENV GOTOOLCHAIN=local
ENV GOPROXY=https://proxy.golang.org,direct

# The bootstrap scripts place pinned sources in ../_vendor, next to this tree.
WORKDIR /workspace/caller-boundary-oracle
COPY . .

RUN bash scripts/bootstrap-vendor.sh \
    && bash scripts/install-jmrtd-local.sh \
    && bash scripts/bootstrap-passauf.sh \
    && bash scripts/bootstrap-vsmartcard.sh \
    && bash scripts/bootstrap-dotnet.sh \
    && bash scripts/bootstrap-dart.sh \
    && make venv \
    && go test ./classifier/...

CMD ["make", "smoke"]
