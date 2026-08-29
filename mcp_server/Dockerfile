# Build context is the repo root (see infrastructure/cdk's
# DockerImageCode.from_image_asset call), matching the mcp_server/ file:
# prefix below.
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

# Container-image Lambda's runtime interface client resolves the handler
# under LAMBDA_TASK_ROOT, which defaults to /var/task — not /asset (that
# was only relevant to the old zip-based Code.from_docker_build packaging).
WORKDIR ${LAMBDA_TASK_ROOT}

COPY --from=builder /build/packages .
COPY mcp_server/ .

CMD ["index.handler"]
