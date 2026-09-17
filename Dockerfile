# syntax=docker/dockerfile:1

ARG SPOTCONNECT_VERSION=0.20.7

FROM debian:13-slim AS builder
ARG SPOTCONNECT_VERSION
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL -o SpotConnect.zip \
      "https://github.com/philippe44/SpotConnect/releases/download/${SPOTCONNECT_VERSION}/SpotConnect-${SPOTCONNECT_VERSION}.zip" \
 && unzip -j SpotConnect.zip spotraop-linux-x86_64-static -d /build \
 && chmod +x /build/spotraop-linux-x86_64-static

FROM debian:13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /build/spotraop-linux-x86_64-static /usr/local/bin/spotraop
WORKDIR /config
ENTRYPOINT ["/usr/local/bin/spotraop"]
