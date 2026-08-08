"""Load documents from GitHub: repository files and closed issues.

This is the first (and currently only) source adapter. It produces
`SourceDocument`s, which is all the rest of the pipeline knows about.
"""

import logging
import shutil
import subprocess
from pathlib import Path

import httpx

from app.config import settings
from app.ingestion import file_filters
from app.ingestion.repos import GITHUB_ORG, RepoSpec
from app.ingestion.sources import CHUNK_TYPE_ISSUE, SourceDocument

logger = logging.getLogger(__name__)

# Cloned repos live here between runs so re-ingestion does not re-download.
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".repo_cache"

GITHUB_API = "https://api.github.com"

# Issues per repo, newest first. Caps API usage on repos with long histories.
MAX_ISSUES_PER_REPO = 100

# Comments carry the actual answers, but long threads drift off-topic.
MAX_COMMENTS_PER_ISSUE = 6


def _api_headers() -> dict[str, str]:
    """Return GitHub API headers, authenticated if a token is configured."""
    headers = {"Accept": "application/vnd.github+json"}
    token = settings.github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def detect_branch(checkout: Path) -> str:
    """Return the branch name a checkout is on.

    Used to build citation URLs, which must point at a branch that exists.
    """
    result = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    return branch if result.returncode == 0 and branch else "HEAD"


def clone_or_update(repo: RepoSpec) -> Path:
    """Shallow-clone a repo into the cache, or refresh it if already present.

    Shallow (`--depth 1`) because we only need current file contents, not
    history. No branch is specified, so git takes the remote's default --
    these repos variously use main, master, and develop. Raises if git fails,
    so ingestion cannot silently skip a repo.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    destination = CACHE_DIR / repo.name

    if (destination / ".git").exists():
        logger.info("Updating %s", repo.full_name)
        result = subprocess.run(
            ["git", "-C", str(destination), "pull", "--depth", "1", "--ff-only"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return destination
        # A shallow pull can fail if the branch was force-pushed; re-clone.
        logger.warning("Update failed for %s, re-cloning", repo.full_name)
        shutil.rmtree(destination, ignore_errors=True)

    logger.info("Cloning %s", repo.full_name)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo.clone_url, str(destination)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed for {repo.full_name}: {result.stderr}")

    return destination


def load_repo_files(
    repo: RepoSpec, checkout: Path, branch: str
) -> tuple[list[SourceDocument], dict[str, int]]:
    """Walk a cloned repo and return its ingestible files plus skip counts."""
    documents: list[SourceDocument] = []
    skipped: dict[str, int] = {}

    for path in sorted(checkout.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(checkout)
        reason = file_filters.should_skip(path, relative_path)
        if reason is not None:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped["not utf-8 text"] = skipped.get("not utf-8 text", 0) + 1
            continue

        if not text.strip():
            skipped["empty"] = skipped.get("empty", 0) + 1
            continue

        posix_path = relative_path.as_posix()
        documents.append(
            SourceDocument(
                source="github",
                repo=repo.full_name,
                file_path=posix_path,
                chunk_type=file_filters.classify(path),
                text=text,
                source_url=(
                    f"https://github.com/{repo.full_name}/blob/{branch}/{posix_path}"
                ),
            )
        )

    return documents, skipped


def _fetch_issue_comments(client: httpx.Client, repo: RepoSpec, number: int) -> list[str]:
    """Return the first few comments on an issue, oldest first."""
    response = client.get(
        f"{GITHUB_API}/repos/{repo.full_name}/issues/{number}/comments",
        params={"per_page": MAX_COMMENTS_PER_ISSUE},
    )
    if response.status_code != 200:
        return []

    return [
        comment["body"].strip()
        for comment in response.json()
        if (comment.get("body") or "").strip()
    ]


def load_closed_issues(repo: RepoSpec) -> list[SourceDocument]:
    """Fetch closed issues (not pull requests) as question-and-answer documents.

    Closed issues are the most valuable part of the corpus: they are real
    developer questions with real answers, and they double as eval material.
    """
    documents: list[SourceDocument] = []

    with httpx.Client(headers=_api_headers(), timeout=30.0) as client:
        page = 1
        while len(documents) < MAX_ISSUES_PER_REPO:
            response = client.get(
                f"{GITHUB_API}/repos/{repo.full_name}/issues",
                params={
                    "state": "closed",
                    "per_page": 100,
                    "page": page,
                    "sort": "created",
                    "direction": "desc",
                },
            )
            if response.status_code != 200:
                logger.warning(
                    "Could not fetch issues for %s: HTTP %d",
                    repo.full_name,
                    response.status_code,
                )
                break

            batch = response.json()
            if not batch:
                break

            for issue in batch:
                # The issues endpoint returns pull requests too; skip them.
                if "pull_request" in issue:
                    continue

                body = (issue.get("body") or "").strip()
                comments = (
                    _fetch_issue_comments(client, repo, issue["number"])
                    if issue.get("comments", 0) > 0
                    else []
                )

                # An issue with no body and no discussion answers nothing.
                if not body and not comments:
                    continue

                parts = [f"# {issue['title']}"]
                if body:
                    parts.append(body)
                for index, comment in enumerate(comments, start=1):
                    parts.append(f"--- Reply {index} ---\n{comment}")

                documents.append(
                    SourceDocument(
                        source="github",
                        repo=repo.full_name,
                        file_path=f"issues/{issue['number']}",
                        chunk_type=CHUNK_TYPE_ISSUE,
                        text="\n\n".join(parts),
                        source_url=issue["html_url"],
                    )
                )

                if len(documents) >= MAX_ISSUES_PER_REPO:
                    break

            page += 1

    return documents


def load_repo(
    repo: RepoSpec, include_issues: bool = True
) -> tuple[list[SourceDocument], dict[str, int]]:
    """Load every document for one repository: files and, optionally, issues."""
    checkout = clone_or_update(repo)
    branch = detect_branch(checkout)
    documents, skipped = load_repo_files(repo, checkout, branch)

    if include_issues:
        documents.extend(load_closed_issues(repo))

    return documents, skipped


__all__ = [
    "CACHE_DIR",
    "GITHUB_ORG",
    "clone_or_update",
    "detect_branch",
    "load_closed_issues",
    "load_repo",
    "load_repo_files",
]
