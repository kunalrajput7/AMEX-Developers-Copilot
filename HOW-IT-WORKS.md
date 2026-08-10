# How It Works

A plain-language walkthrough of the Amex Developer Copilot: the problem it
solves, how a question travels through it, why it is built this way, and what
we measured.

For setup instructions see [README.md](README.md). This document is the
explanation.

---

## 1. The problem

A developer wants to use a library. The knowledge they need exists — it is
spread across READMEs, source files, and closed GitHub issues where someone
already hit the same wall. But finding it means knowing which repository to
look in, which file, and what the thing is called.

You could ask a general-purpose chatbot. Two problems:

1. **It may not know.** Small open-source libraries are thinly represented in
   training data, and anything that changed recently isn't there at all.
2. **You can't tell when it's wrong.** A confident, plausible, invented answer
   looks exactly like a correct one. For an API integration — where a wrong
   header name costs an afternoon — that is worse than no answer.

So the problem isn't "answer questions about this code." It's **answer
questions about this code in a way the reader can verify**, and prove that the
answers are actually good rather than asserting it.

---

## 2. What we built

An assistant that answers developer questions about American Express's public
open-source repositories, where **every claim links to the file it came from**.

Two things make it more than a demo:

- **It is an agent, not a search box.** It decides what to look for, judges
  whether what it found is good enough, and searches again with better wording
  when it isn't. It also decides when *not* to search: a greeting gets a
  greeting, not a report that the repositories contain no matches.
- **Its quality is measured, and the measurement blocks bad releases.** A test
  suite of real questions runs in CI. If answers get worse, the build fails —
  even though the code compiles and every unit test passes.

That second point is the one most projects skip, and it is the most valuable
part of this one.

---

## 3. The journey of one question

Here is what actually happens when someone asks *"How do I authenticate with
the Amex API using the Java client?"*

```
 Browser  ──POST /chat/stream──▶  FastAPI  ──▶  The agent (LangGraph)
    ▲                                                    │
    │                                    ┌───────────────┴───────────────┐
    │                                    │  1. DECIDE what to search     │
    │                                    │  2. SEARCH the knowledge base │
    │                                    │  3. GRADE what came back      │
    │                                    │  4. WRITE the answer          │
    │                                    │  5. CHECK every claim is      │
    │                                    │     backed by a source        │
    │                                    └───────────────┬───────────────┘
    │                                                    │
    └──── streamed progress, then answer + citations ◀───┘
```

**Step 1 — Decide.** The model is shown the question, the three searches
available, and what it has already tried. It picks one. First time round it
chose `search_docs("Java client authentication Amex API")`.

**Step 2 — Search.** That runs against the knowledge base (section 4 explains
how). Six results come back.

**Step 3 — Grade.** The model reads those results and judges whether they can
actually answer the question. Here it said no:

> *"The sources only mention that the Java client library handles header
> creation for authentication but provide no actual code examples or steps."*

So it loops back to step 1 and tries `search_code` instead — a different corner
of the corpus, better suited to "show me how."

**Step 4 — Write.** With good sources gathered, it writes the answer, marking
each claim with `[1]`, `[2]` and so on.

**Step 5 — Check.** A separate pass re-reads the answer against the sources and
asks: is every claim actually supported? On this question it caught the model
inventing a `BASE_URL` configuration key that appears nowhere in the corpus. The
answer was thrown away, the rejected claims were fed back in, and the rewrite
came out clean.

**The result:** a grounded answer with 6 citations, from 16 sources read. Took
about 17 seconds and cost roughly 4.5 cents.

Throughout, the browser is streamed a running commentary — *"Searching the
knowledge base → search_code: Java client authentication"* — because 17 seconds
of spinner looks like a crash.

---

## 4. The four layers

### Layer 1 — The knowledge base (what it knows)

Before answering anything, the system has to *have* the knowledge.

```
GitHub repos  ──▶  filter  ──▶  chunk  ──▶  embed  ──▶  Postgres
```

**Pick the repos.** We surveyed all 88 public repositories in the
`americanexpress` org and measured which actually contain documentation. This
mattered: the repos *about* Amex APIs turned out to be tiny — 18 documentation
files and 4 closed issues between them. Not enough to build on. So the corpus
is a deliberate mix: the 5 Amex API/SDK client repos (which keep "how do I
authenticate" working as a real question) plus 4 genuinely well-documented
projects for volume.

**Filter out the junk.** `node_modules`, images, lock files, minified code, test
fixtures. Roughly 480 files dropped. Junk costs money to process and actively
degrades search quality.

**Cut into chunks.** A 50-page document is useless as a search result — you'd
get the whole thing back when you needed one paragraph. Everything is sliced
into ~500-token pieces (a few paragraphs) with a small overlap, so an answer
sitting on a boundary isn't cut in half.

**Also grab closed GitHub issues.** These are the best material in the corpus:
real developers asking real questions, with real answers in the replies.

**Turn each chunk into numbers.** Each chunk goes through an embedding model and
comes back as a list of 1,536 numbers. Chunks about similar topics land near
each other numerically — that is what makes meaning-based search possible.

**Store it, with the source URL.** Every chunk keeps the exact GitHub link it
came from. Without that, citations are impossible.

**What's there now:**

```
1,417 chunks across 9 repositories
  933  source code
  280  documentation
  204  GitHub issues
```

Two things make this cheap to maintain:

- **Re-running is nearly free.** Every chunk carries a fingerprint of its
  content. A second run recognises what hasn't changed and skips it — proven:
  it embedded **zero** new chunks.
- **It cannot go stale.** If a file is deleted or rewritten upstream, its old
  chunks are removed. The assistant can never cite code that no longer exists.

### Layer 2 — Retrieval (how it finds things)

This is where most of the engineering judgment lives.

**Two search methods, because each fails where the other works.**

*Meaning search* (vector search) understands that "how do I log in" and
"authentication" are the same topic. It is bad at exact strings.

*Word search* (full-text search) nails exact identifiers — `X-Amex-Api-Key`,
`failureThreshold`, error codes, endpoint paths. It understands no meaning at
all.

We measured the difference rather than assuming it. Searching for the exact
config option `storeReceivedOnFailure`:

| | Results in top 10 that actually contain the term |
|---|---|
| Meaning search | **0 / 10** |
| Word search | **10 / 10** |

Meaning search scores *zero* on an exact identifier. That is not a flaw — a
camelCase option name carries almost no semantic content. It is exactly why the
second method exists.

**Merging them.** The two methods produce scores on completely different scales,
so you can't add them. Instead we use **Reciprocal Rank Fusion**: throw the
scores away and use only each result's *position* in its own list.

```
score(chunk) = sum over both lists of  1 / (60 + position)
```

A chunk ranked highly by either method scores well; one ranked highly by both
scores best. We pull 50 candidates from each method before merging, because a
chunk ranked 40th by one and 2nd by the other is exactly the result fusion
exists to rescue.

### Layer 3 — The agent (how it thinks)

Layers 1 and 2 alone would already give you a working chatbot — but a
simple-minded one that always does the same thing regardless of the question.

The agent turns that fixed pipeline into a loop with judgment. It has:

**Three tools**, which are the same hybrid search aimed at different parts of
the corpus:

| Tool | Best for |
|---|---|
| `search_docs` | Setup, configuration, "how do I" |
| `search_code` | Exact function names, how something actually works |
| `search_issues` | Errors, edge cases, problems others already hit |

**Three guardrails**, which matter as much as the capability:

- **A budget.** At most 5 searches per question. Proven by test: with the cap
  set to 2 and a deliberately unanswerable question, it stopped at exactly 2 and
  said honestly that it didn't know — rather than inventing something.
- **Read-only tools.** The agent can search the knowledge base and nothing else.
  No shell, no writes, no arbitrary code. An agent that *cannot* reach anything
  dangerous doesn't need to be trusted not to.
- **Conversation-scoped memory.** Each question starts from a fresh state.
  Nothing carries between users.

**And citation enforcement.** Only sources the answer actually cites are shown
to the reader, with the `[1]`, `[2]` markers renumbered to match. A listed
source always means "this backs the answer."

**Follow-up questions work.** Earlier turns travel with each request and are
shown to the agent, so *"What about the .NET one?"* resolves into a real search:

```
Q: How do I authenticate with the Amex API using the Java client?
   → search_docs: American Express Java client API authentication
   → search_code: amex-api-java-client authentication credentials HttpClient

Q: What about the .NET one?
   → search_docs: amex-api-dotnet-client-core authentication
```

The second question is meaningless on its own; the agent rewrote the reference
into the actual repository name before searching.

History comes from the client on every request rather than a server-side
session. That keeps the backend stateless — no sessions to expire, and no route
by which one conversation could reach another — and it means the CLI can hold a
conversation just as the web app does. Only the last six turns are sent, each
truncated, so a long session doesn't crowd the retrieved sources out of the
prompt.

### Layer 4 — Evaluation (how we know it's good)

This is the layer that makes the difference between a demo and a system.

**A set of real questions with known answers.** 32 hand-written questions, plus
30 more generated from corpus chunks for volume.

Two kinds, and the second is easy to forget:

- **26 answerable questions**, each with a reference answer and the source URL
  where the answer actually lives. Nearly half target the Amex API and SDK
  repos, so the headline numbers describe the corpus the project is about
  rather than whichever repo happened to have the most documentation.
- **6 unanswerable questions** — Stripe webhooks, a Python SDK that doesn't
  exist, Amex merchant fees, an invented `--deep-scan` flag. The only correct
  response is to say so.

Without that second group the harness measures accuracy and never measures
honesty. Every answerable question rewards producing an answer, so a system
that never refuses would score perfectly while being unusable in practice.
These are scored on one metric — `refusal_correctness` — and answering anyway
is its own failure category, because a confident answer to something the corpus
never covered is a different kind of wrong from an imperfect one.

The generated ones are written by the *judge* model, not the answering one. A
model that authors its own exam gravitates toward questions it already handles
well — the same bias as self-grading, one step earlier in the pipeline. So
GPT-4.1 sets the paper and marks it; Claude sits it.

**Seven metrics, split by how much you should trust them:**

*Exact metrics* — computed by comparing URLs, with no model reading them:

- **context_recall** — did the search find the right source at all?
- **citation_recall** — did the answer actually *cite* it, or find it and ignore it?
- **reciprocal_rank** — how highly was it ranked?

Exact arithmetic, but **not reproducible**, and the distinction matters. These
measure which chunks *the agent gathered*, and the agent writes its own search
queries — which vary between runs even at temperature 0, because model inference
isn't bit-deterministic. On one run the agent searched docs for a token-expiry
question and found the README; on the next it searched code and missed it.
Nothing changed but the query it happened to write.

*Judged metrics* — a model reads the answer and scores it, because "is this
claim supported" has no arithmetic answer:

- **faithfulness** — is every claim backed by the sources?
- **answer_relevance** — does it address what was asked?
- **answer_correctness** — does it agree with the reference answer?

**The judge is a different model family from the agent**, and that matters more
than it sounds. A model grading its own output is a defendant judging its own
trial — it scores itself generously, and worse, it is blind in the same places.
If the answering model misreads a source, the same model as judge tends to
misread it identically and call the answer faithful.

Two models from one vendor share training lineage and therefore share failure
modes, so a stronger sibling only fixes half the problem. Here Claude writes the
answers and **GPT-4.1 grades them** — independent judgement, not a second
opinion from the same mind. Every scorecard names its judge, because a
self-graded run and an independently graded one are not comparable numbers.

**Failure analysis, not just averages.** An average tells you quality moved. The
scorecard also names *why* each case failed, in pipeline order:

```
retrieval_miss  →  retrieved_but_uncited  →  ungrounded  →  wrong_answer
```

Order matters. A retrieval miss causes every downstream failure, so reporting it
as "wrong answer" would send you debugging the wrong stage.

**And it gates the build.** Thresholds live in a config file. If any metric drops
below its floor, the run exits non-zero and **CI fails the pull request.**

---

## 5. What we measured

The 32-question gold set, judged by an independent model:

```
metric                before   after    n
context_recall         0.923   1.000   26
citation_recall        0.923   1.000   26
reciprocal_rank        0.743   0.833   26
faithfulness           0.969   0.985   26
answer_relevance       0.985   1.000   26
answer_correctness     0.965   0.973   26
refusal_correctness    1.000   1.000    6

passed                 30/32   32/32
```

Per question: **~17 seconds, ~4.5 cents, 4 model calls.**

**`refusal_correctness` of 1.000 is the one to notice.** All six unanswerable
questions were declined rather than answered — including an invented
`--deep-scan` flag, which is plausible enough that inventing behaviour for it
would have been the easy path.

**How the two failures were fixed matters more than the fact that they were.**
The tempting fix is to add whatever the agent actually cited to the list of
acceptable sources, which turns any miss green without changing anything. So
both were left red while the cause was found, and the rule was that a source
may only be added after opening the file and confirming it answers the question
on its own merits — never *because* the agent cited it. Neither question needed
that; the dataset is unchanged.

Retrieval turned out not to be the problem. Both questions ranked the correct
source **first** once the query was well formed. The agent was searching the
wrong corpus for a question a README answers, and paraphrasing the other
question into generic vocabulary that matched nothing. The fixes were to the
agent: tool descriptions that say which corpus answers which kind of question,
an instruction to keep the question's distinctive wording, and showing the
grading step which searches have already run so it stops accepting one thin
result. No threshold was moved.

**The floors were left where they were.** Nothing above is a reason to raise a
gate to 1.000 — see the spread below. Raising floors to match a best-ever run
is how a gate starts failing honest work and gets ignored.

**Read the spread, not the single number.** Two earlier runs with identical code
differed by 0.04–0.08 on every metric, and three questions changed verdict. Two
causes, neither a regression:

1. **The agent's queries vary.** Model inference isn't bit-deterministic even at
   temperature 0, so the agent phrases its searches slightly differently and
   sometimes lands on a different corner of the corpus.
2. **The samples are small.** One flipped question moves a metric by 0.038 —
   and among the six refusal cases, by 0.167.

That second point is also the fix: **growing the question sets is the only thing
that tightens these numbers.** Prompt tuning won't; the variance is in the
sample size and the sampling, not the system.

Thresholds are therefore set for the *spread*, not for a best run — each floor
sits roughly two questions below the worse of the two. A gate that trips on a
coin flip gets ignored within a week, and an ignored gate protects nothing.
Every floor in `thresholds.yaml` is annotated with both runs' numbers, so the
next person can see whether it is defensible or merely historical.

---

## 6. Design decisions worth explaining

**Postgres with pgvector, not a dedicated vector database.** One system stores
the vectors, runs the word search, holds the citation metadata, and enforces the
deduplication constraint. One query, one transaction, no syncing between two
stores. A managed search service would have done the hybrid search for us — and
in doing so would have hidden the most interesting engineering in the project
behind an API call.

**Two retrievers, not one.** Measured, not assumed: 0/10 versus 10/10 on an
exact identifier. Each covers the other's blind spot.

**Progress streaming, not token streaming.** The agent makes 4+ model calls over
~17 seconds. Streaming the final answer's tokens would only cover the last few
seconds; streaming *what it is doing* covers the whole wait and happens to be
the most interesting thing to watch.

**One backend, three surfaces.** The web UI, the `ask.py` command line tool, and
the evaluation harness all drive the same agent. Adding a surface doesn't mean
reimplementing the intelligence.

**Temperature 0, and extended thinking off.** Both to hold variance down as far
as it will go, because the evaluation harness gets less useful the noisier the
output is. Worth being precise, though: this reduces variance, it does not
remove it. Model inference is not bit-deterministic, so identical runs still
differ — which is why the thresholds are set for a measured spread rather than
for a single good run (section 5).

**An independent judge.** Three model deployments, split by role: Claude writes
the answers, `text-embedding-3-large` builds the knowledge base, and GPT-4.1
grades. Using the answering model as its own judge would have been free and
would have inflated every generation metric. The preflight script warns loudly
if no independent judge is configured.

**Fail loudly.** If the database schema can't be applied, the API refuses to
start. An API serving requests against a half-built database fails later, in
more confusing ways.

---

## 7. Where everything lives

```
backend/
  app/
    config.py            all settings, read from .env — the only place
                         environment variables are touched

    db/                  Postgres connection, schema, and models
    llm/                 one client per model role
      chat_client.py       Claude — writes the answers
      embedding_client.py  turns text into vectors
      judge_client.py      GPT-4.1 — grades answers during evaluation

    ingestion/           building the knowledge base
      repos.py             which repositories, and why
      file_filters.py      what to skip
      github_loader.py     download and read
      chunker.py           cut into pieces
      embedder.py          turn into numbers
      ingest.py            orchestrate, skip unchanged, clean up stale

    retrieval/           finding things
      vector_search.py     meaning search
      keyword_search.py    word search
      hybrid.py            merge the two

    agent/               the thinking loop
      state.py             what it knows at each step
      tools.py             the three searches it may run
      prompts.py           what the model is told
      nodes.py             the agent's steps
      graph.py             how the steps connect
      citations.py         keep only what the answer used

    api/                 the HTTP endpoints
    observability/       per-request latency, tokens, and cost

  eval/                  the quality harness
    datasets/              the question sets (32 gold, 30 synthetic)
    generate_dataset.py    writes the synthetic set, using the judge model
    evaluators.py          the seven metrics + failure classifier
    run_eval.py            the scorecard and the gate
    thresholds.yaml        the pass marks, annotated with the runs behind them

  scripts/               command-line tools
  tests/                 34 tests

frontend/                the React chat UI
.github/workflows/       CI: tests, build, and the evaluation gate
```

Every file has one job. Median length is 98 lines; four files exceed 200, the
largest being `github_loader.py` at 248 — the messiest job in the project, since
it deals with git, the GitHub API, and the filesystem.

---

## 8. Running it

```bash
docker compose up -d              # Postgres with pgvector

cd backend
python scripts/check_models.py    # verify all three model deployments
python scripts/run_ingestion.py   # build the knowledge base
uvicorn app.main:app --reload

cd ../frontend && npm run dev     # then open http://localhost:5173
```

Other useful commands:

```bash
python scripts/search.py "query" --method all   # retrieval only, no model
python scripts/ask.py "question" --trace        # the agent, with its reasoning
python eval/run_eval.py                         # the scorecard and gate
```
