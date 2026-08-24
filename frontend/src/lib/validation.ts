// Mirrors backend/ragbot/core/Repository.py's CODELOAD_URL_RE - client-side
// validation catches a malformed URL before spending a round trip on it, but
// the backend remains the source of truth for what it will actually accept.
const CODELOAD_URL_RE = /^https:\/\/codeload\.github\.com\/[^/]+\/[^/]+\/zip\/refs\/heads\/.+$/;

const GITHUB_URL_RE = /^https:\/\/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?(?:\/tree\/([^/]+))?$/;

export function isValidCodeloadUrl(url: string): boolean {
  return CODELOAD_URL_RE.test(url.trim());
}

export interface ParsedGithubUrl {
  owner: string;
  repo: string;
  /** Explicit branch from a /tree/<branch> URL, or null if unspecified. */
  branch: string | null;
}

/** Parse a plain github.com repo URL, without resolving its default branch. */
export function parseGithubUrl(url: string): ParsedGithubUrl | null {
  const trimmed = url.trim().replace(/\/$/, '');
  const match = trimmed.match(GITHUB_URL_RE);
  if (!match) return null;
  const [, owner, repo, branch] = match;
  return { owner, repo, branch: branch ?? null };
}

/** True if the string is either a codeload URL or a plain github.com repo URL. */
export function looksLikeRepoUrl(url: string): boolean {
  return isValidCodeloadUrl(url) || parseGithubUrl(url) !== null;
}

/** Build a codeload zip URL for a known owner/repo/branch. */
export function buildCodeloadUrl(owner: string, repo: string, branch: string): string {
  return `https://codeload.github.com/${owner}/${repo}/zip/refs/heads/${branch}`;
}

/**
 * Turn a normal github.com repo URL into the codeload zip URL the API expects,
 * WITHOUT resolving the actual default branch - callers that need the real
 * default (not just a guess) should use resolveCodeloadUrl instead. Kept for
 * callers that already know the branch doesn't matter (e.g. a /tree/<branch>
 * URL) or that accept "main" as a fallback guess.
 */
export function toCodeloadUrl(url: string): string | null {
  const parsed = parseGithubUrl(url);
  if (!parsed) return null;
  return buildCodeloadUrl(parsed.owner, parsed.repo, parsed.branch ?? 'main');
}

/**
 * Resolve a github.com or codeload URL to a codeload zip URL, looking up the
 * repository's actual default branch via the GitHub API when the URL doesn't
 * name one explicitly. Guessing "main" is wrong often enough to matter - any
 * repo predating GitHub's 2020 default-branch rename still uses "master", and
 * ingestion would otherwise 404 against a real, existing repository.
 *
 * Falls back to "main" if the lookup fails (rate-limited, offline, private
 * repo) - a codeload 404 downstream is still comprehensible, and ingestion
 * shouldn't be blocked entirely by a lookup that isn't load-bearing for most
 * repos (github.com now defaults new repos to "main").
 */
export async function resolveCodeloadUrl(url: string): Promise<string | null> {
  const trimmed = url.trim();
  if (isValidCodeloadUrl(trimmed)) return trimmed;

  const parsed = parseGithubUrl(trimmed);
  if (!parsed) return null;
  if (parsed.branch) return buildCodeloadUrl(parsed.owner, parsed.repo, parsed.branch);

  const branch = await resolveDefaultBranch(parsed.owner, parsed.repo);
  return buildCodeloadUrl(parsed.owner, parsed.repo, branch);
}

async function resolveDefaultBranch(owner: string, repo: string): Promise<string> {
  try {
    const res = await fetch(`https://api.github.com/repos/${owner}/${repo}`);
    if (!res.ok) return 'main';
    const data: { default_branch?: string } = await res.json();
    return data.default_branch || 'main';
  } catch {
    return 'main';
  }
}
