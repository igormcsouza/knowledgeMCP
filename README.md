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
