import { afterEach, describe, expect, it, vi } from 'vitest';
import { isValidCodeloadUrl, looksLikeRepoUrl, parseGithubUrl, resolveCodeloadUrl, toCodeloadUrl } from './validation';

describe('isValidCodeloadUrl', () => {
  it('accepts a well-formed codeload URL', () => {
    expect(isValidCodeloadUrl('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')).toBe(true);
  });

  it('accepts branch names containing slashes', () => {
    expect(isValidCodeloadUrl('https://codeload.github.com/o/r/zip/refs/heads/feature/x')).toBe(true);
  });

  it('rejects a plain github.com URL', () => {
    expect(isValidCodeloadUrl('https://github.com/mvrey/RAGBot')).toBe(false);
  });

  it('rejects a non-github host', () => {
    expect(isValidCodeloadUrl('https://example.com/zip/refs/heads/main')).toBe(false);
  });

  it('rejects an empty string', () => {
    expect(isValidCodeloadUrl('')).toBe(false);
  });

  it('tolerates surrounding whitespace', () => {
    expect(isValidCodeloadUrl('  https://codeload.github.com/o/r/zip/refs/heads/main  ')).toBe(true);
  });
});

describe('toCodeloadUrl', () => {
  it('converts a plain repo URL to its codeload zip URL, defaulting to main', () => {
    expect(toCodeloadUrl('https://github.com/mvrey/RAGBot')).toBe(
      'https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main',
    );
  });

  it('respects an explicit branch from a /tree/ URL', () => {
    expect(toCodeloadUrl('https://github.com/mvrey/RAGBot/tree/develop')).toBe(
      'https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/develop',
    );
  });

  it('strips a trailing slash', () => {
    expect(toCodeloadUrl('https://github.com/mvrey/RAGBot/')).toBe(
      'https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main',
    );
  });

  it('strips a .git suffix', () => {
    expect(toCodeloadUrl('https://github.com/mvrey/RAGBot.git')).toBe(
      'https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main',
    );
  });

  it('returns null for an unrecognized URL shape', () => {
    expect(toCodeloadUrl('not a url')).toBeNull();
  });
});

describe('parseGithubUrl', () => {
  it('parses owner and repo with no branch', () => {
    expect(parseGithubUrl('https://github.com/mvrey/RAGBot')).toEqual({
      owner: 'mvrey', repo: 'RAGBot', branch: null,
    });
  });

  it('parses an explicit branch from a /tree/ URL', () => {
    expect(parseGithubUrl('https://github.com/mvrey/RAGBot/tree/develop')).toEqual({
      owner: 'mvrey', repo: 'RAGBot', branch: 'develop',
    });
  });

  it('returns null for a non-github URL', () => {
    expect(parseGithubUrl('https://gitlab.com/mvrey/RAGBot')).toBeNull();
  });
});

describe('looksLikeRepoUrl', () => {
  it('accepts a plain github.com URL', () => {
    expect(looksLikeRepoUrl('https://github.com/mvrey/RAGBot')).toBe(true);
  });

  it('accepts a codeload URL', () => {
    expect(looksLikeRepoUrl('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main')).toBe(true);
  });

  it('rejects an unrelated URL', () => {
    expect(looksLikeRepoUrl('https://example.com')).toBe(false);
  });
});

describe('resolveCodeloadUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('passes a codeload URL through unchanged, without calling the GitHub API', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const result = await resolveCodeloadUrl('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main');

    expect(result).toBe('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('uses an explicit /tree/ branch without calling the GitHub API', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const result = await resolveCodeloadUrl('https://github.com/mvrey/RAGBot/tree/develop');

    expect(result).toBe('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/develop');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('resolves the real default branch when none is given - the mvrey/Rasterizer case (master, not main)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ default_branch: 'master' }),
    })));

    const result = await resolveCodeloadUrl('https://github.com/mvrey/Rasterizer');

    expect(result).toBe('https://codeload.github.com/mvrey/Rasterizer/zip/refs/heads/master');
  });

  it('falls back to main if the GitHub API lookup fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })));

    const result = await resolveCodeloadUrl('https://github.com/mvrey/RAGBot');

    expect(result).toBe('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main');
  });

  it('falls back to main if the GitHub API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network error'); }));

    const result = await resolveCodeloadUrl('https://github.com/mvrey/RAGBot');

    expect(result).toBe('https://codeload.github.com/mvrey/RAGBot/zip/refs/heads/main');
  });

  it('returns null for an unrecognized URL shape', async () => {
    expect(await resolveCodeloadUrl('not a url')).toBeNull();
  });
});
