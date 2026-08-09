# Amex Developer Copilot

An agentic knowledge assistant over American Express's public open-source
repositories. Ask a developer question, get an answer where **every claim links
to the file it came from** — and where answer quality is measured, not asserted.

> **Want to understand how it works?** → **[HOW-IT-WORKS.md](HOW-IT-WORKS.md)**
> walks one question through the whole system and explains every design
> decision. This file is setup and reference.

---

## What it does

```
GitHub repos ──▶ chunk ──▶ embed ──▶ Postgres + pgvector
                                          │
                          ┌───────────────┴───────────────┐
                     vector search                  keyword search
                          └───────────────┬───────────────┘
                                     RRF fusion
                                          │
                              LangGraph agent loop
                 decide → search → grade → write → check citations
                                          │
                           FastAPI ──▶ React UI  +  CLI
```

Three things make it more than a chatbot:

- **Hybrid retrieval.** Vector search understands meaning but is useless on
  exact identifiers; keyword search is the reverse. Measured on a real config
  option: vector **0/10**, keyword **10/10**. Both run, merged by Reciprocal
  Rank Fusion.
- **A real agent loop.** It picks which corpus to search, judges whether the
  results are good enough, retries with better wording, then verifies every
  claim it wrote is backed by a source — capped at 5 searches per question.
- **Follow-up questions work.** Ask *"How do I authenticate with the Java
  client?"*, then *"What about the .NET one?"*, and the second resolves into a
  real search (`amex-api-dotnet-client-core authentication`). History travels
  with each request, so the backend stays stateless.
- **A quality gate in CI.** A set of real questions runs on every pull request.
  If answers get worse, **the build fails** — even though the code compiles and
  every unit test passes.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI + Pydantic v2 |
| Database | PostgreSQL 16 + pgvector |
| Agent | LangGraph |
| Frontend | React (Vite) + Tailwind CSS |
| Local infra | Docker Compose |

Everything above is open source and runs on your machine. The only hosted
dependency is three model deployments on **Azure AI Foundry**.

---

## Setup

**Prerequisites:** Docker Desktop, Python 3.11+, Node 18+.

### 1. Start Postgres

```bash
docker compose up -d
```

Runs `pgvector/pgvector:pg16` on port 5432 with database `copilot`.

### 2. Configure your models

```bash
cd backend
cp .env.example .env
```

You need **three model deployments**, one per role:

| Role | Example | Why |
|---|---|---|
| Answers | `claude-sonnet-4-6` | the agent |
| Vectors | `text-embedding-3-large` | ingestion and search |
| Judge | `gpt-4.1` | grades answers during evaluation |

The judge is deliberately a **different model family** from the one writing
answers. A model grading its own output scores itself generously and is blind in
the same places, so its verdicts aren't independent. Leave it blank and
evaluation still runs — the preflight script will warn you the scores are
optimistic.

Each value in `.env.example` has a comment explaining what it expects.

> **The embedding model must produce 1536 dimensions.** `text-embedding-3-large`
> is natively 3072, so the code requests 1536 explicitly — pgvector's HNSW index
> caps at 2000, and above that every search silently degrades to a full table
> scan. If you change this, update `VECTOR(n)` in `app/db/schema.sql` to match
> and re-ingest.

### 3. Install and verify

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
python scripts/check_models.py
```

`check_models.py` makes one tiny call to each of the three deployments and
reports what came back. Run it before ingesting — a wrong deployment name
surfaces in seconds instead of a thousand chunks in.

### 4. Build the knowledge base

```bash
python scripts/run_ingestion.py --dry-run   # costs nothing; shows what it would do
python scripts/run_ingestion.py             # the real run, ~1,400 chunks
```

Re-running is nearly free: every chunk carries a content fingerprint, so a
second run embeds zero new chunks.

### 5. Run it

```bash
uvicorn app.main:app --reload     # backend  → http://localhost:8000
```

```bash
cd frontend && npm install && npm run dev    # UI → http://localhost:5173
```

---

## Environment variables

Live in `backend/.env`, which is **git-ignored** — never commit it.
`backend/.env.example` is the committed template.

| Variable | Required | What it is |
|---|---|---|
| `ANTHROPIC_FOUNDRY_BASE_URL` | ✅ | Foundry's Anthropic surface, ending `/anthropic` |
| `ANTHROPIC_FOUNDRY_API_KEY` | ✅ | key for that resource |
| `ANTHROPIC_CHAT_DEPLOYMENT` | ✅ | deployment name of the answering model |
| `AZURE_OPENAI_ENDPOINT` | ✅ | same resource, no `/anthropic` suffix |
| `AZURE_OPENAI_API_KEY` | ✅ | key for that surface |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | ✅ | must be 1536-dimension capable |
| `AZURE_OPENAI_JUDGE_DEPLOYMENT` | — | evaluation judge; blank = self-graded |
| `AZURE_OPENAI_API_VERSION` | — | defaults to `2024-10-21` |
| `DATABASE_URL` | — | defaults to the Docker Postgres |
| `GITHUB_TOKEN` | — | raises the ingestion rate limit to 5,000/hr |
| `MAX_TOOL_CALLS` | — | agent search budget, defaults to 5 |
| `JSON_LOGS` | — | `true` for machine-readable logs |

**The deployment name is what *you* typed when creating it**, which is often not
the model name. That's the most common thing to get wrong.

`GITHUB_TOKEN` needs **no scopes at all** — reading public repositories works
with an unscoped token, and it still gets the full 5,000 requests/hour.

---

## Command line

```bash
python scripts/check_models.py                  # verify all three deployments
python scripts/run_ingestion.py --dry-run       # build the knowledge base
python scripts/search.py "query" --method all   # retrieval only, no model
python scripts/ask.py "question" --trace        # the agent, showing its steps
python scripts/ask.py "How do I authenticate with the Java client?" \
  --follow-up "What about the .NET one?"        # check follow-ups resolve
python eval/run_eval.py                         # scorecard and quality gate
```

## Tests

```bash
cd backend && pytest
```

Most tests are pure. A few need Postgres — the ones covering the stale-chunk
sweep (the only code path that deletes data) and the smoke test, which boots the
app and therefore applies the schema. Those skip when no database is reachable,
so `pytest` works with Docker down.

CI provides a database and **fails the build if anything skips** — a skipped
test shows the same green tick as a passing one, and the tests most likely to
skip are the ones guarding the destructive path.

## Evaluation

```bash
python eval/run_eval.py                    # gold tier — this is the CI gate
python eval/run_eval.py --tier all         # gold + synthetic
python eval/generate_dataset.py --count 40 # rebuild the synthetic tier
```

Two tiers: 32 hand-written questions that gate the build, and 30 generated ones
for volume and trend.

Seven metrics: three computed from URLs, three scored by the judge, and
`refusal_correctness` for the unanswerable cases.

The gold tier is **26 answerable questions plus 6 unanswerable ones** — Stripe
webhooks, a Python SDK that doesn't exist, an invented CLI flag. Those last six
are the only cases that test whether the assistant says "I don't know" instead
of inventing, since every answerable question rewards producing an answer.

**Read the spread, not a single run.** Two runs with identical code differ by
0.04–0.08 on every metric, because the agent writes its own search queries and
model inference isn't bit-deterministic. Thresholds in `eval/thresholds.yaml`
are set for that measured spread, and annotated with the runs behind them.

Full explanation: [HOW-IT-WORKS.md § Evaluation](HOW-IT-WORKS.md).

## Observability

Every request logs one structured line:

```json
{"method": "POST", "path": "/chat", "status": 200, "duration_ms": 16992.5,
 "chat_calls": 4, "input_tokens": 12267, "output_tokens": 531,
 "estimated_cost_usd": 0.044767}
```

Set `JSON_LOGS=true` for machine-readable output. The cost is an estimate from
list prices in `config.py` — good for spotting a question that costs ten times
the others, not for reconciling an invoice.

## Continuous integration

[.github/workflows/eval.yml](.github/workflows/eval.yml) runs on every pull
request: unit tests, a frontend build, and the evaluation gate. The gate stands
up Postgres, builds the knowledge base, and runs the gold tier through the
agent. If quality drops below the thresholds, the build fails.

Needs these repository secrets: `ANTHROPIC_FOUNDRY_BASE_URL`,
`ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_CHAT_DEPLOYMENT`,
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`, `AZURE_OPENAI_JUDGE_DEPLOYMENT`.

The eval job skips itself on forked pull requests, where secrets aren't
available.

---

## Data sources and licensing

The corpus is nine repositories from the
[American Express open-source GitHub org](https://github.com/americanexpress),
which is Apache-2.0 licensed. The public Developer Portal pages carry Terms of
Use and are **not** scraped. Every chunk records its source URL so answers cite
back to the original.
