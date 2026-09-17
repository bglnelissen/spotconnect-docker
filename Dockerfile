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
# SpotConnect is MIT licensed; its notice travels with the binary.
RUN curl -fsSL -o /build/LICENSE \
      "https://raw.githubusercontent.com/philippe44/SpotConnect/${SPOTCONNECT_VERSION}/LICENSE"

FROM debian:13-slim
ARG SPOTCONNECT_VERSION
LABEL org.opencontainers.image.title="spotraop" \
      org.opencontainers.image.description="spotraop ${SPOTCONNECT_VERSION} from philippe44/SpotConnect: AirPlay devices as Spotify Connect devices" \
      org.opencontainers.image.source="https://github.com/bglnelissen/spotconnect-docker" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${SPOTCONNECT_VERSION}"
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /build/spotraop-linux-x86_64-static /usr/local/bin/spotraop
COPY --from=builder /build/LICENSE /usr/share/doc/spotconnect/LICENSE
WORKDIR /config
ENTRYPOINT ["/usr/local/bin/spotraop"]
