# syntax=docker/dockerfile:1

FROM python:3.13-slim

# Pinned on purpose. Upgrading means changing this number and rebuilding.
ARG ZEROCONF_VERSION=0.151.3

RUN pip install --no-cache-dir --root-user-action=ignore "zeroconf==${ZEROCONF_VERSION}"

WORKDIR /app
COPY spotconfig.py matching.py commands.py discovery.py server.py device test_*.py ./

# The build fails when a test fails.
RUN python3 -m unittest -q

ENV PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8131 \
    CONFIG_PATH=/config/config.xml

USER 1000:1000
EXPOSE 8131
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s \
  CMD ["python3", "server.py", "--healthcheck"]
CMD ["python3", "server.py"]
