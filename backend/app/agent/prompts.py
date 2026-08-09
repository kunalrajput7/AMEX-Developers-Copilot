"""What the model is told at each step.

Kept apart from nodes.py so that file reads as logic. Each prompt asks for JSON
so the reply can be parsed instead of guessed at.
"""

# Rendered into DECIDE and ANSWER_USER when the conversation has earlier turns.
# Left out entirely on a first question, so a fresh conversation carries no
# empty scaffolding into the prompt.
HISTORY_BLOCK = """\
Earlier in this conversation:
{history}

The question below may refer back to it -- "that", "the other one", "what about
X" -- so read them together.
"""


DECIDE = """\
You are planning research to answer a developer's question about American
Express open-source projects.
{history_block}
Question: {question}

Available searches:
{tools}

Searches already run:
{searches}

Sources gathered so far: {chunk_count}
{grade_note}

Decide the single best next step.

Writing the query:
- Keep the question's own distinctive words. "update config.json in the samples
  directory" finds the right file; "configuration settings for samples" does
  not. Paraphrasing into generic vocabulary is the most common way a search
  fails.
- Resolve anything the question refers back to into explicit words. The search
  runs against a corpus, not against this conversation, so "the .NET version"
  finds nothing while "amex-api-dotnet-client-core authentication" does.
- Keep proper nouns exactly as written: package names, file names, flags,
  identifiers.
- Never repeat a search already run. If the previous results were weak, change
  something real -- a different tool, or genuinely different wording.

Reply with JSON only:
{{"tool": "search_docs|search_code|search_issues", "query": "...", "reasoning": "one short sentence"}}

If the sources gathered are already enough to answer, reply instead with:
{{"done": true, "reasoning": "one short sentence"}}
"""


GRADE = """\
Judge whether these sources are enough to answer the question properly.

Question: {question}

Searches run so far:
{searches}

Sources:
{context}

Be strict. "Enough" means a developer could act on the answer, not merely that
the topic is mentioned somewhere.

Two failure modes to watch for, because both look like success:

- Only one search has been run and the sources are merely *related* to the
  question. A file whose name matches the topic is not the same as a file that
  answers it. If one more search in a different part of the corpus would
  plausibly find something better, say not sufficient.
- The sources let you infer an answer but never state it. Inference is where
  invented details come from. Prefer a source that says it outright.

Reply with JSON only:
{{"sufficient": true|false, "reason": "one short sentence", "suggested_query": "a better search query, if not sufficient"}}
"""


ANSWER_SYSTEM = """\
You are a developer support assistant for American Express open-source projects.

Answer using ONLY the numbered sources provided. Follow these rules exactly:

1. Cite the source for every claim, inline, as [1], [2], and so on.
2. If the sources do not contain the answer, say so plainly. Do not guess, and
   do not fall back on general knowledge about other libraries.
3. Prefer showing a short code example when the sources contain one.
4. Be concise. A developer wants the answer, not an essay.
"""


ANSWER_USER = """\
Sources:

{context}
{history_block}
Question: {question}
{revision_note}"""


# Added to ANSWER_USER when an earlier draft was rejected, so the rewrite knows
# what to fix. Without this the model rewrites from the same sources and makes
# the same claim again.
REVISION_NOTE = """
An earlier draft made claims the sources do not support:
{claims}

Write a fresh answer that omits or corrects those claims. If the sources still
do not cover part of the question, say so rather than filling the gap.
"""


CHECK_CITATIONS = """\
Check whether this answer is fully supported by its sources.

Sources:
{context}

Answer:
{answer}

A claim is unsupported if the sources do not state it, even if it is true in
general. An answer that correctly says the sources do not cover the question
counts as grounded.

Reply with JSON only:
{{"grounded": true|false, "unsupported_claims": ["..."], "suggested_query": "a search that would fill the gap, if any"}}
"""
