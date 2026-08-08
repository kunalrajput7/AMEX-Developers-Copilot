"""Rules deciding which repository files are worth ingesting.

Kept separate from the loader so the rules are easy to read and adjust in one
place. Junk in the corpus costs money to embed and actively hurts retrieval,
so the filters are deliberately strict.
"""

from pathlib import Path

from app.ingestion.sources import CHUNK_TYPE_CODE, CHUNK_TYPE_DOC

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".mdx"}

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".cs",
    ".go",
    ".kt",
    ".swift",
    ".rb",
}

# Directories that only ever contain dependencies, build output, or fixtures.
SKIP_DIRECTORIES = {
    ".git",
    ".github",
    ".idea",
    ".next",
    ".venv",
    "__pycache__",
    "__snapshots__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

# Exact filenames that are generated or otherwise not worth reading.
SKIP_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "go.sum",
    "Gemfile.lock",
}

# Suffixes marking minified, generated, or test-fixture files.
SKIP_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".map",
    ".snap",
    ".lock",
    ".d.ts",
)

# Path fragments marking test fixture data. These are .txt files that look like
# documentation to the extension filter but contain expected-output dumps, so
# they pollute retrieval with content no developer would ever ask about.
SKIP_PATH_FRAGMENTS = (
    "test/resources",
    "tests/resources",
    "testdata",
    "fixtures",
)

# Files above this size are almost always generated or vendored.
MAX_FILE_BYTES = 200_000

# Files below this are usually stubs with nothing to retrieve.
MIN_FILE_BYTES = 80


def classify(path: Path) -> str | None:
    """Return the chunk_type for a file, or None if it should be skipped."""
    suffix = path.suffix.lower()
    if suffix in DOC_EXTENSIONS:
        return CHUNK_TYPE_DOC
    if suffix in CODE_EXTENSIONS:
        return CHUNK_TYPE_CODE
    return None


def should_skip(path: Path, relative_path: Path) -> str | None:
    """Return a reason to skip this file, or None if it should be ingested.

    Returning the reason (rather than a bool) lets the CLI report *why* files
    were dropped, which is how you notice a filter is too aggressive.
    """
    if any(part in SKIP_DIRECTORIES for part in relative_path.parts):
        return "in skipped directory"

    posix_path = relative_path.as_posix().lower()
    if any(fragment in posix_path for fragment in SKIP_PATH_FRAGMENTS):
        return "test fixture data"

    if path.name in SKIP_FILENAMES:
        return "generated file"

    lowered = path.name.lower()
    if any(lowered.endswith(suffix) for suffix in SKIP_SUFFIXES):
        return "minified or generated"

    if classify(path) is None:
        return "unsupported file type"

    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"

    if size > MAX_FILE_BYTES:
        return f"too large ({size // 1024} KB)"
    if size < MIN_FILE_BYTES:
        return "too small"

    return None
