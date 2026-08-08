"""The corpus: which American Express repositories we ingest, and why.

Deliberately small. The spec warns that ingesting all 80+ org repos adds noise
and hurts retrieval quality, so this list is curated in two halves:

  * Amex API / SDK clients -- the integration questions the copilot exists to
    answer. Small repos, but they carry the "how do I authenticate" content.
  * Documentation-rich tooling -- the org's genuinely well-documented projects.
    These supply the volume that makes hybrid retrieval and evaluation
    meaningful, and their closed issues are real developer Q&A.
"""

from dataclasses import dataclass

GITHUB_ORG = "americanexpress"


@dataclass(frozen=True)
class RepoSpec:
    """One repository to ingest.

    The branch is deliberately not configured here. These repos disagree about
    whether the default is main, master, or develop, and the API's reported
    default has already proven wrong once. The loader clones whatever the
    remote's default is and reads the branch name back from the checkout.
    """

    name: str
    theme: str

    @property
    def full_name(self) -> str:
        """Return 'org/name', used as the `repo` column value."""
        return f"{GITHUB_ORG}/{self.name}"

    @property
    def clone_url(self) -> str:
        """Return the HTTPS clone URL."""
        return f"https://github.com/{GITHUB_ORG}/{self.name}.git"


REPOS: list[RepoSpec] = [
    # --- Amex API / SDK clients --------------------------------------------
    RepoSpec("amex-api-java-client-core", "amex-api"),
    RepoSpec("amex-api-dotnet-client-core", "amex-api"),
    RepoSpec("targeted-offers-client", "amex-api"),
    RepoSpec("prefill-client-node", "amex-api"),
    RepoSpec("defaultoffers-client-node", "amex-api"),
    # --- Documentation-rich tooling ----------------------------------------
    RepoSpec("unify-flowret", "tooling"),
    RepoSpec("fetchye", "tooling"),
    RepoSpec("earlybird", "tooling"),
    RepoSpec("jest-image-snapshot", "tooling"),
]
