# Knowledge Base MCP

A personal MCP server that exposes a MkDocs-based knowledge base (hosted on
GitHub) to AI assistants — so concepts, weak spots, and past fixes can be
recalled by asking, instead of manually searching the docs site.

## Architecture

```
 ┌─────────────────┐        push / webhook        ┌───────────────────┐
 │  MkDocs repo     │ ────────────────────────────▶│  Indexer Lambda    │
 │  (GitHub)        │        + daily schedule       │  (batch, offline)  │
 └─────────────────┘                                └─────────┬──────────┘
                                                                │ chunks + embeddings
                                                                ▼
                                                     ┌────────────────────┐
                                                     │     DynamoDB       │
                                                     │  content + usage   │
                                                     └─────────┬──────────┘
                                                                │ read
                                                                ▼
                                                     ┌────────────────────┐
                                                     │  MCP Server Lambda  │
                                                     │ (FastMCP, request/  │
                                                     │  response, stateless)│
                                                     └─────────┬──────────┘
                                                                │
                                                                ▼
                                                     ┌────────────────────┐
                                                     │ Lambda Function URL │
                                                     │  (streamable-http)  │
                                                     └─────────┬──────────┘
                                                                │
                                                                ▼
                                                     ┌────────────────────┐
                                                     │     MCP client       │
                                                     │ Claude / ChatGPT /   │
                                                     │      Gemini          │
                                                     └────────────────────┘
```

Two Lambdas, kept deliberately separate:

- **Indexer** — pulls markdown from the MkDocs repo, chunks and embeds it,
  and writes it to DynamoDB. Runs on a GitHub webhook (push) and on a
  scheduled fallback. Indexing never happens on a request.
- **MCP server** — a stateless FastMCP app (`streamable-http` transport)
  that only reads from DynamoDB and answers tool calls. Deployed behind a
  Lambda Function URL.

The server is public and read-mostly, so it's unauthenticated behind an
unguessable Function URL rather than gated with OAuth or a bearer token.

## Connecting an MCP client

The server speaks the standard MCP `streamable-http` transport at its
Lambda Function URL (find it in your CDK deploy output, or the AWS Console
under the MCP server Lambda's Function URL). No auth headers are required.

### Claude Code

```bash
claude mcp add --transport http knowledge-base <your-function-url>
```

### Claude Desktop

Settings → Connectors → Add custom connector, then enter the Function URL
as an HTTP MCP server.

### ChatGPT

Settings → Connectors → Add connector (or, in developer mode, add an MCP
server), and enter the Function URL. ChatGPT requires the connector to be
reachable over HTTPS, which the Function URL already is.

### Gemini (Gemini CLI / Extensions)

Add an MCP server entry pointing at the Function URL, e.g. in
`~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "knowledge-base": {
      "httpUrl": "<your-function-url>"
    }
  }
}
```

Exact menu names vary by client version — if a client's UI doesn't match,
look for wherever it manages "MCP servers" or "connectors" and add this as
an HTTP-based one.

## Troubleshooting

Issues hit (and fixed) while building this out, in case they recur:

- **Bedrock embeddings unusable — account-wide quota is 0.** This
  account's on-demand quota for every Bedrock embedding model (Titan,
  Cohere, TwelveLabs) is 0 in every region, and it's not self-serve
  adjustable. Fix: switched both the indexer and MCP server to a local
  `fastembed` (ONNX) model (`BAAI/bge-small-en-v1.5`) run in-process —
  no AWS dependency, no quota, and the same model on both sides so
  cosine similarity stays meaningful.

- **`fastembed` model download fails with "Read-only file system".**
  fastembed's HF download accelerator (`hf_xet`) writes to
  `$HOME/.cache/huggingface` regardless of the `cache_dir` you pass it,
  and Lambda's default `$HOME` isn't writable — only `/tmp` is. Fix: set
  `HOME=/tmp` in the Lambda environment.

- **Container-image Lambda deploy fails: "Unzipped size must be smaller
  than 262144000 bytes".** `Code.from_docker_build` still packages the
  build output as a zip (250MB unzipped limit), and `fastembed`'s
  `onnxruntime` dependency blows past that. Fix: use
  `DockerImageFunction` + `DockerImageCode.from_image_asset` instead —
  real container-image Lambdas, 10GB limit.

- **Docker build fails with `ENAMETOOLONG` while staging the image
  context.** `DockerImageCode.from_image_asset` stages the whole repo
  root as the build context. Without a `.dockerignore`, that staging
  copy recursively included `infrastructure/cdk/cdk.out` (which itself
  holds previous staging output), nesting infinitely. Fix: add a
  `.dockerignore` excluding `cdk.out/`, `.venv/`, `.git/`, etc.

- **Container-image Lambda returns 502, logs "No module named 'index'".**
  `WORKDIR /asset` was a leftover from the old zip-packaging setup. A
  real container-image Lambda's runtime interface client resolves the
  handler relative to `LAMBDA_TASK_ROOT` (`/var/task`), not `/asset`.
  Fix: set `WORKDIR` to `LAMBDA_TASK_ROOT` in the Dockerfile.

- **Indexer times out silently on a full backfill run.** Two compounding
  causes: (1) unauthenticated GitHub REST calls are capped at 60
  req/hour shared across every Lambda customer on the same egress IPs,
  and PyGithub backs off silently instead of raising, so a ~50-file run
  just hangs until the Lambda timeout with no error. Fix: authenticate
  GitHub API calls with a token (Secrets Manager, set out-of-band via
  `put-secret-value`, never committed) — bumps the limit to 5000
  req/hour. (2) Even authenticated, a ~55-article run can exceed the
  default 5-minute timeout with the CPU-bound ONNX embedding step and no
  visible progress. Fix: bumped the indexer to 15 minutes (Lambda's hard
  ceiling) / 2048MB (more memory buys more vCPU), and added a per-article
  INFO log line so a slow run is diagnosable instead of a silent
  timeout.

- **MCP server 502s from the second request onward.** The `FastMCP`
  instance (and its `StreamableHTTPSessionManager`) was built once at
  module import and cached across warm Lambda invocations, but Mangum
  runs the ASGI lifespan on every invocation — the session manager
  raises "can only be called once per instance" on its second run. Fix:
  build a fresh `FastMCP` app per invocation instead of a module-level
  singleton.

- **MCP server returns 421 to every client.** The MCP SDK's
  DNS-rebinding protection rejects any `Host` header that isn't
  `localhost` by default, which is exactly what a Lambda Function URL
  sends. Fix: disable it via `TransportSecuritySettings` — a Function
  URL has no fixed hostname to allowlist anyway, and this endpoint is
  unauthenticated read access.

- **claude.ai custom connector can't authenticate.** claude.ai's
  web/desktop custom-connector UI only supports OAuth, not a static
  bearer header. Fix: dropped bearer auth entirely rather than
  implementing OAuth for a personal, read-mostly KB sitting behind an
  unguessable Function URL.
