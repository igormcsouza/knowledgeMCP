# Knowledge Base MCP Server — Implementation Plan

Personal MCP server exposing a MkDocs-based GitHub knowledge base to an AI client, so concepts, weak spots, and past fixes can be recalled by asking instead of manually searching the site.

## Architecture

```
MkDocs repo (GitHub)
    -> Indexer Lambda (scheduled + webhook-triggered)
    -> DynamoDB (content chunks + embeddings, usage tracking)
    -> MCP Server Lambda (FastMCP, streamable-http, stateless_http=True)
    -> Lambda Function URL
    -> MCP client (Claude Desktop / Claude Code)
```

Two Lambdas: an **indexer** (batch) and the **MCP server** (request/response, stateless). Indexing never happens on-request.

Stack conventions should match existing SoftMedium / JGAutoCar patterns: Python, AWS CDK, DynamoDB-backed, serverless.

**LangChain/LangGraph usage is scoped, not blanket:**
- LangChain used only for text splitting + the embeddings wrapper in the indexer (Phase 1)
- LangGraph used only for `suggest_review_queue()` (Phase 3), the one tool that needs multi-step reasoning over several data sources
- Every other tool is a single retrieval call — plain Python calling DynamoDB/Bedrock directly, no framework wrapper. The MCP client (Claude) is the reasoning layer; the tools should stay thin.

---

## Phase 1 — Content Pipeline (Indexing)

- [ ] **1.1 GitHub content fetcher**
  - [ ] Pull markdown files from the MkDocs repo (GitHub API, or shallow `git clone` into `/tmp`)
  - [ ] Parse `mkdocs.yml` `nav` structure to get category/hierarchy metadata per article
  - [ ] Extract frontmatter (tags, dates) if present

- [ ] **1.2 Chunking + embedding**
  - [ ] Chunk articles using LangChain's `MarkdownHeaderTextSplitter` (or `RecursiveCharacterTextSplitter` as fallback) — handles code blocks/tables better than a hand-rolled splitter
  - [ ] Generate embeddings via LangChain's `BedrockEmbeddings` wrapper (Titan Embeddings model — keeps everything AWS-native)
  - [ ] Store chunks + embeddings in DynamoDB (brute-force cosine similarity at query time is fine at this KB's scale; revisit pgvector/OpenSearch only if it gets slow)

- [ ] **1.3 Usage/metadata tracking table**
  - [ ] New DynamoDB table: per article/concept — last-queried date, query count, first-seen date, edit count (git history as a proxy for depth)
  - [ ] This table is what powers "weak concepts" detection — it comes from usage patterns, not content alone

- [ ] **1.4 Trigger wiring**
  - [ ] GitHub webhook on push -> indexer Lambda re-indexes only changed files (diff against last-indexed commit SHA stored in DynamoDB)
  - [ ] EventBridge scheduled rule (e.g. daily) as a fallback safety net

---

## Phase 2 — MCP Server Core

- [ ] **2.1 FastMCP scaffold**
  - [ ] `FastMCP("knowledge-base-mcp", stateless_http=True, json_response=True)`
  - [ ] Transport: `streamable-http` (current standard; SSE-only transport is legacy)

- [ ] **2.2 Lambda adapter**
  - [ ] Wrap the FastMCP ASGI app with Mangum
  - [ ] Deploy behind a Lambda Function URL (simplest for a personal MCP server; switch to API Gateway HTTP API later only if throttling/custom domain/usage plans are needed)

- [ ] **2.3 Auth**
  - [ ] Static bearer token in middleware, stored in Secrets Manager, injected via env var
  - [ ] (OAuth 2.1 is spec-supported but overkill unless this gets exposed beyond personal use)

---

## Phase 3 — Tools

- [ ] **3.1 `search_concept(query: str)`**
  Semantic search across the KB; returns top-k chunks with article title/path/section.

- [ ] **3.2 `find_weak_concepts(topic: str | None)`**
  Surfaces articles/sections with low word count, few internal links, or low edit history — optionally filtered by topic.

- [ ] **3.3 `get_article_context(article_path: str)`**
  Returns full article content, for use as grounding context in a follow-up explanation.

- [ ] **3.4 `list_related_concepts(concept: str)`**
  Embedding-similarity lookup for adjacent articles not directly asked about.

- [ ] **3.5 `recall_solution(problem_description: str)`**
  Search tuned toward troubleshooting/fix-tagged content — separate tool because the intent differs from concept lookup.

- [ ] **3.6 `get_recently_added(days: int)`**
  Lists articles/sections added or edited in the last N days.

- [ ] **3.7 `suggest_review_queue()`** *(LangGraph)*
  Combines weak concepts + stale (not queried recently) + old-and-never-revisited content into a prioritized spaced-repetition-style list.
  - [ ] Small graph: `fetch_weak_concepts` node -> `fetch_stale_concepts` node -> `fetch_untouched_concepts` node -> `merge_and_rank` node
  - [ ] Only this tool uses LangGraph — it's the sole tool needing multi-source reasoning rather than a single lookup

- [ ] **3.8 `log_query_feedback(concept: str, was_helpful: bool)`**
  Writes back to the usage-tracking table, closing the loop so weak-concept detection improves over time.

- [ ] **3.9 `get_article_history(article_path: str)`**
  Returns git log for a file, showing how a concept/fix evolved over time.

---

## Phase 4 — Infra (CDK)

- [ ] CDK stack(s) mirroring existing project conventions
  - [ ] Indexer Lambda + EventBridge schedule + webhook endpoint (Function URL or API Gateway route)
  - [ ] MCP server Lambda + Function URL
  - [ ] DynamoDB tables: content index, usage/weak-concept tracking
  - [ ] Secrets Manager entries: bearer token, GitHub PAT (if repo is private)
  - [ ] IAM roles scoped minimally per Lambda

---

## Phase 5 — Testing & Validation

- [ ] Validate the deployed server with the official MCP Inspector (`npx @modelcontextprotocol/inspector`) before wiring into any client
- [ ] Test cold-start latency — all embeddings should be precomputed at index time; only the query itself gets embedded at request time
- [ ] Consider provisioned concurrency on the MCP server Lambda if cold starts are too slow in practice
- [ ] Wire into Claude Desktop / Claude Code as an MCP server once Inspector validation passes

---

## Suggested Build Order

1. CDK skeleton + DynamoDB tables
2. GitHub fetcher + MkDocs nav parser (standalone script first, not yet a Lambda)
3. Chunking + embedding pipeline (LangChain splitter + Bedrock embeddings wrapper), tested locally against a few articles
4. Indexer Lambda wrapping steps 2–3, wired to EventBridge schedule
5. FastMCP server with `search_concept` only, deployed, validated via MCP Inspector
6. Remaining tools added incrementally, each validated via Inspector before moving to the next
7. Usage-tracking-dependent tools added last, once the other tools are in active use: `log_query_feedback` (plain function), then `suggest_review_queue` (LangGraph graph, built once the data it queries actually has history to reason over)
