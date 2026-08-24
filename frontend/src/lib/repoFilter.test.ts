import { describe, expect, it } from 'vitest';
import { MAX_FILE_BYTES, shouldIncludeFile } from './repoFilter';

describe('shouldIncludeFile', () => {
  it.each([
    'repo/src/app.py',
    'repo/main.go',
    'repo/README.md',
    'repo/pyproject.toml',
    'repo/Dockerfile',
    'repo/web/index.html',
  ])('includes %s', (path) => {
    expect(shouldIncludeFile(path, 100)).toBe(true);
  });

  it.each([
    'repo/node_modules/lib/index.js',
    'repo/.venv/lib/site.py',
    'repo/dist/bundle.js',
    'repo/__pycache__/mod.py',
    'repo/logs/run.json',
  ])('excludes %s (excluded directory)', (path) => {
    expect(shouldIncludeFile(path, 100)).toBe(false);
  });

  it.each([
    'repo/package-lock.json',
    'repo/uv.lock',
    'repo/go.sum',
    'repo/app.min.js',
    'repo/style.min.css',
    'repo/bundle.js.map',
  ])('excludes %s (excluded filename/suffix)', (path) => {
    expect(shouldIncludeFile(path, 100)).toBe(false);
  });

  it('excludes dotfiles', () => {
    expect(shouldIncludeFile('repo/.gitignore', 100)).toBe(false);
    expect(shouldIncludeFile('repo/.eslintrc.json', 100)).toBe(false);
  });

  it('excludes files over the size cap', () => {
    expect(shouldIncludeFile('repo/src/app.py', MAX_FILE_BYTES + 1)).toBe(false);
  });

  it('includes files at exactly the size cap', () => {
    expect(shouldIncludeFile('repo/src/app.py', MAX_FILE_BYTES)).toBe(true);
  });

  it('does not exclude a folder whose own name matches an excluded directory', () => {
    // The selected folder is literally named "dist" - that's the zip's/
    // upload's top-level segment, not a nested build-output directory.
    expect(shouldIncludeFile('dist/src/app.py', 100)).toBe(true);
  });

  it('still excludes a nested directory with that name inside the folder', () => {
    expect(shouldIncludeFile('myproject/dist/bundle.js', 100)).toBe(false);
  });

  it('is case-insensitive for excluded directories and filenames', () => {
    expect(shouldIncludeFile('repo/NODE_MODULES/lib/index.js', 100)).toBe(false);
    expect(shouldIncludeFile('repo/Package-Lock.json', 100)).toBe(false);
  });

  it('rejects files with no recognized extension', () => {
    expect(shouldIncludeFile('repo/some-binary', 100)).toBe(false);
  });
});
