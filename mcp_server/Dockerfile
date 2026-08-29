# Build context is the repo root (see infrastructure/cdk's
# Code.from_docker_build call), matching the mcp_server/ file: prefix below.
FROM python:3.12-slim AS builder

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY mcp_server/pyproject.toml ./

RUN mkdir -p packages && \
    uv pip compile pyproject.toml --no-header -o requirements.txt && \
    uv pip install \
      --no-cache-dir \
      --target packages \
      --compile \
      -r requirements.txt

FROM public.ecr.aws/lambda/python:3.12

WORKDIR /asset

COPY --from=builder /build/packages .
COPY mcp_server/ .

CMD ["index.handler"]
