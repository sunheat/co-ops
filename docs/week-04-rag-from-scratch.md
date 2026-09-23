# Week 4 Report: RAG from Scratch

This report closes Week 4 of the Phase 2 plan. The week built a minimal
retrieval-augmented generation pipeline without LangChain: document loading,
fixed-size chunking, an embedding client, an in-memory vector store,
top-k retrieval, and a citation-aware answer generator. The injected context
is now real corpus retrieval instead of the mocked chunks used in Phase 1.

## What was built

| Day | Deliverable | Status |
| --- | --- | --- |
| 1 | `packages/rag/loaders.py`, document loading tests | Done |
| 2 | `packages/rag/chunkers.py`, chunk statistics example | Done |
| 3 | `packages/llm/embeddings.py`, embed-one-chunk example | Done |
| 4 | `packages/rag/vector_store_in_memory.py`, `examples/retrieve_top_k.py` | Done |
| 5 | `packages/rag/rag_pipeline.py`, `examples/ask_rag.py` | Done |
| 6 | `packages/rag/citation.py`, structured cited answers | Done |

The acceptance question ran end to end with paced embedding batches:
`"Where is margin calculated?"` produced an answer, validated sources,
retrieved chunks with scores, token usage, and latency. The default
`examples/ask_rag.py` run fails under the free-tier quota used for this
verification; see the failure-case and acceptance sections below.

## 1. What are the RAG pipeline steps?

The pipeline follows these stages across its components:

```text
load documents -> chunk -> embed chunks -> store vectors
  -> embed query -> rank by cosine similarity -> build context
  -> generate cited answer -> validate citations
```

1. **Load.** `load_markdown_docs()`, `load_text_docs()`, and
   `load_code_files()` normalize each file into a `Document(id, source_path,
   source_type, content, metadata)`. `source_type` is classified from path
   ancestors (`ticket`, `runbook`, `doc`) or the file extension (`code`).
   The current corpus yields 33 documents: 25 Markdown files and 8 Java
   files; no plain-text files yet.
2. **Chunk.** `chunk_document()` splits each document into fixed-size
   character windows (default 1000 characters with 200 characters of
   overlap) and carries document metadata plus `source_type` and
   `chunk_index` onto every `Chunk`. The default configuration produces 114
   chunks from 82,187 source characters.
3. **Embed chunks.** `RagPipeline.index()` batches chunk contents through
   `EmbeddingClient` (up to 100 inputs per request). A failed batch stops
   indexing, but chunks from earlier batches remain in the in-memory store.
4. **Store vectors.** `InMemoryVectorStore` unit-normalizes each vector on
   insert and keeps `(chunk, vector)` pairs in a list. There is no vector
   database, no persistence, and no numeric-library dependency; the store
   lives for the process lifetime only.
5. **Embed the query.** The question goes through the same embedding
   client and model as the chunks, so query and chunk vectors share one
   space.
6. **Rank.** `search()` computes cosine similarity as a dot product over
   normalized vectors, sorts descending, and returns `top_k` (default 5)
   with insertion-order tie-breaking for determinism.
7. **Build context and generate.** Each retrieved chunk becomes a
   `ContextBlock` labeled `source_path (chunk_id: <id>)`. The system prompt
   requires answers to stay inside the provided context, to cite the source
   path and chunk id behind every claim, and to say so when the context
   does not answer the question. The chat call uses `temperature=0.2` and
   `response_format="json"`; the model must return a `CitedAnswer` JSON
   object with `answer`, `sources`, and `confidence`.
8. **Validate citations.** `validate_citations()` keeps only citations
   whose chunk id was actually retrieved and whose source path matches that
   chunk. Fabricated citations land in `invalid_sources`; duplicate chunk
   ids collapse into one source. `examples/ask_rag.py` prints answer,
   confidence, valid sources, rejected citations, retrieved chunks with
   scores, token usage, and latency.

## 2. How is an embedding model different from a chat model?

They answer different questions: an embedding model maps text into a fixed
vector so that "how similar are these texts?" becomes arithmetic, while a
chat model generates new text token by token.

- **API surface.** Embeddings use `/embeddings` with an `input` list and
  return one vector per input; chat uses `/chat/completions` with messages
  and returns a generated message. The repository keeps two clients
  (`EmbeddingClient`, `LLMClient`) instead of overloading one, because
  request shapes, response contracts, and usage fields differ.
- **Consistency.** Embeddings from the same model and version are intended
  to be comparable, which makes similarity search possible. Changing the
  model or its version can change vectors. Chat output is sampled;
  temperature and provider variance mean the same prompt can produce
  different answers.
- **Usage and cost.** Embeddings bill input tokens only and carry no
  completion tokens; chat bills prompt plus completion tokens. Indexing
  114 chunks require two batched embedding requests at the default batch
  size of 100, or six requests at the paced batch size of 20 used here.
  One question needs one query embedding request plus one chat request
  (observed: 1,443-1,939 total chat tokens per answer, dominated by the
  retrieved context).
- **Coupling.** The two can, and here do, come from different providers:
  verification for this report used Gemini
  (`gemini-embedding-001`, 3072-dimension vectors) for embeddings and
  OpenRouter (`openai/gpt-4o-mini`) for chat. The pipeline only requires
  that chunk and query embeddings come from the same model.
- **Failure modes differ.** Embedding failures are shape problems
  (dimension mismatch, non-finite values, out-of-order or missing indexes);
  chat failures include JSON or schema violations, which is why the
  citation layer parses and validates the answer instead of trusting it.

## 3. How does chunk size affect results?

Measured on the current 33-document corpus with the repository chunker:

| `chunk_size` / `overlap` | Chunks | Characters stored in chunks |
| --- | --- | --- |
| 400 / 80 | 266 | 100,827 |
| 1000 / 200 (default) | 114 | 98,387 |
| 2000 / 400 | 61 | 93,387 |

Source text totals 82,187 characters, so overlap alone inflates stored
characters by roughly 23% at 400/80, 20% at 1000/200, and 14% at 2000/400.

The table measures chunk counts and stored characters, not answer quality
or retrieval accuracy across the three configurations. The effects below
are expected trade-offs unless tied to the default-size probe runs.

- **Smaller chunks** may improve retrieval precision for narrow questions:
  a 400-character window is less likely to mix two topics. The costs are
  context fragmentation (the answer often spans several windows, and only
  some of them make top-k), more vectors to embed, and a larger share of
  near-duplicate neighbors from the overlap.
- **Larger chunks** keep more surrounding context per hit and reduce the
  number of vectors, but a vector representing several topics may rank
  less precisely. They can also spend more prompt tokens. In the default-size
  probe runs, the full chat requests used 1.4-1.9k total tokens per question.
- **Overlap** protects statements that straddle a boundary, but it is
  stored and embedded twice and can crowd out diversity: in the
  "Which Java class calculates margin?" run, four of the five retrieved
  chunks came from `MarginCalculator.java` through overlapping windows
  (`[0:1000]`, `[800:1800]`, `[1600:2600]`, `[4000:5000]`), so the model
  saw one file four times.
- **Boundaries are not semantic yet.** Because the chunker is
  character-based, windows cut through words and code: `architecture.md`
  chunk at offset 1600 starts with `cknowledgment status. |`, and the
  `MarginCalculator.java` chunk at offset 4800 starts mid-token with
  `e BigDecimal calculateVariationMargin(List<Position>...`. Tail chunks
  are the only small ones (3 of 114 are under 300 characters), so size
  skew is modest with this corpus.
- **Configuration is a trade-off, not a constant.** Chunk size also
  interacts with `top_k` and the context budget, since the retrieved set
  becomes the whole context. A size worth tuning for this corpus is
  whatever keeps a full answer inside the top-k windows without padding
  the prompt with duplicates; Week 5 replaces these windows with
  structure-aware chunking instead of tuning constants.

## 4. Why are citations important?

- **Verifiability.** An enterprise answer is only useful if a reviewer can
  open the exact source. Requiring `source_path` and `chunk_id` makes every
  claim traceable to a chunk, not to "the docs somewhere".
- **Hallucination control.** The model must name chunk ids that exist in
  the retrieved set. `validate_citations()` treats any other citation as a
  fabrication and reports it separately, so a confident-sounding answer
  with an invented source is visible rather than silent.
- **Evaluation.** Source-level metrics (expected source, source hit,
  retrieval rank) need stable, structured citations; `data/eval_seed/
  questions_v0.jsonl` already carries gold sources, and Week 8's baseline
  evaluation scores answers against them.
- **Machine-checkable output.** The `CitedAnswer` schema turns answers into
  data: JSON parsing plus Pydantic validation catch malformed output before
  it reaches a user.
- **Honest limits.** Validation is structural: it confirms that a cited
  chunk exists and was retrieved, not that the chunk actually supports the
  sentence. `confidence` is likewise model-declared and unverified. Claim
  level checking, refusal gates, and answer-quality evaluation are Week 7
  and Phase 3 work.

## 5. What are the current failure cases?

Observed on 2026-09-23 while verifying this report, plus what code and chunk
inspection already show.

**Retrieval quality**

- Overlap duplication and no diversity control: one file can occupy most of
  top-k (four of five chunks in the margin-class question), so the context
  budget is spent on near-duplicates.
- Character windows cut words and code lines (`cknowledgment`, mid-token
  method signatures) and carry no class, method, or line-number metadata,
  so code questions depend on luck rather than structure.
- Pure vector search ignores exact tokens that matter in this domain
  (class names, table names, error codes, ticket ids). There is no BM25 and
  no metadata filtering yet, even though `source_type` is already stored on
  every chunk; both land in Week 6.

**Evidence handling**

- No score threshold and no refusal gate: "What is the capital of France?"
  still retrieved five chunks (scores 0.49-0.51). The model correctly
  answered "The context does not provide information about the capital of
  France.", but nothing in the pipeline enforces that behavior; refusal
  currently depends on prompt compliance, and `confidence: "low"` is
  self-reported. Week 7 adds explicit insufficient-evidence refusal.
- Citation validation cannot detect an unsupported claim attached to a real
  chunk. In the acceptance run the cited source (`data/sample_docs/faq.md`)
  differed from the top-ranked chunk (`data/sample_docs/data-flow.md`),
  which is legitimate but shows that ranking and citation are not
  reconciled.

**Provider and operations**

- Gemini embedding quota: a 100-input index batch is rejected with
  HTTP 429 `Resource exhausted` on the free tier, while batches of 1-20
  inputs pass. The default `EMBED_BATCH_SIZE = 100` therefore fails on the
  first batch; this verification indexed 114 chunks in paced batches of 20
  with 20-second gaps. Rate limits were the first real indexing failure of
  the week, matching the "Rate Limits" topic of the phase plan.
- Chat robustness: `gemini-flash-latest` returned HTTP 503 `UNAVAILABLE`
  ("experiencing high demand") after all retries; the run succeeded on
  OpenRouter afterwards. Transient provider load is not something the
  pipeline can smooth over yet.
- Local and Azure paths were unavailable during verification: Ollama is not
  installed (`Connection refused`), and the configured Azure endpoint did
  not resolve from this network (`getaddrinfo failed`), so both the `.env`
  defaults (`LLM_PROVIDER=local`) and the Azure deployment could not be
  exercised.
- `RateLimitError` does not keep the provider's response body, so the 429
  detail (which quota, which window) is dropped; diagnosing the batch
  rejection above needed a raw HTTP probe.
- No index persistence: every run re-embeds all 114 chunks. That is the
  slowest and most rate-limit-sensitive part of a question, and it repeats
  even when only the question changes.

**Answer quality**

- Answers are terse ("In the Margin Service (Java).", 90 completion
  tokens) and cite exactly one source even when several chunks were
  relevant; whether that is desirable is an evaluation question for the
  Week 8 baseline, but the pipeline currently offers no control over answer
  length or citation breadth.

## Acceptance check

The Week 4 acceptance criterion is a runnable question with answer,
sources, retrieved chunks, usage, and latency. Because the free-tier
embedding limit rejects the default 100-input batch, the verification run
drove the same pipeline with paced 20-input batches:

```text
indexed chunks: 114
QUESTION: Where is margin calculated?
ANSWER:   In the Margin Service (Java).
SOURCES:  data/sample_docs/faq.md
RETRIEVED: 5 chunks (top score 0.6890 data-flow.md [1600:2600])
USAGE:    1,882 tokens   LATENCY: 3,085 ms

QUESTION: What is the capital of France?        (out of corpus)
ANSWER:   The context does not provide information about the capital of France.
SOURCES:  none                                  CONFIDENCE: low

QUESTION: Which Java class calculates margin?
ANSWER:   The Java class that calculates margin is MarginCalculator.
SOURCES:  .../margin/service/MarginCalculator.java
RETRIEVED: 4 of 5 chunks from that one file     LATENCY: 9,697 ms
```

Embeddings: `gemini-embedding-001` (3,072 dimensions). Chat:
`openai/gpt-4o-mini` via OpenRouter. `examples/ask_rag.py` prints the same
fields when its provider environment can satisfy the embedding request
shape.

## Next steps

- Week 5: structure-aware chunking for Markdown, Java, SQL schema, and
  tickets, which addresses the boundary and metadata failures above.
- Week 6: BM25 plus hybrid retrieval with metadata filters, which addresses
  exact-token queries and duplicate-heavy top-k.
- Week 7: query rewriting, reranking, citation validation v2, and
  insufficient-evidence refusal.
- Week 8: baseline evaluation over the 36 seeded questions, index/batch
  handling for provider rate limits, and the API/UI demo.
