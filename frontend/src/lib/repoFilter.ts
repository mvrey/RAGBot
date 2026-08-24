// Mirrors backend/ragbot/core/Repository.py's should_include() - the backend
// re-applies the same allowlist on every uploaded zip entry regardless (it is
// the authority on what actually gets indexed), so a mismatch here is a
// bandwidth/UX nicety, not a correctness bug: this just avoids zipping and
// uploading node_modules, build output, and other dead weight in the first
// place, and gives the user an accurate file/size count before they wait on it.

const INCLUDED_EXTENSIONS = new Set([
  'py', 'js', 'jsx', 'mjs', 'ts', 'tsx', 'go', 'rs', 'java', 'kt',
  'rb', 'php', 'cs', 'c', 'h', 'cpp', 'cc', 'hpp', 'swift', 'scala',
  'sh', 'bash', 'sql', 'yaml', 'yml', 'toml', 'json', 'html', 'css',
  'scss', 'vue', 'svelte', 'md', 'mdx', 'rst', 'txt', 'ini', 'cfg',
]);

const INCLUDED_FILENAMES = new Set(['dockerfile', 'makefile']);

const EXCLUDED_DIRECTORIES = new Set([
  '.git', 'node_modules', '.venv', 'venv', 'vendor', 'dist', 'build', 'target',
  '__pycache__', 'site-packages', '.next', '.nuxt', 'coverage', '.mypy_cache',
  '.pytest_cache', '.ruff_cache', 'logs',
]);

const EXCLUDED_FILENAMES = new Set([
  'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'poetry.lock',
  'uv.lock', 'cargo.lock', 'go.sum', 'composer.lock',
]);

const EXCLUDED_SUFFIXES = ['.min.js', '.min.css', '.map', '.lock'];

export const MAX_FILE_BYTES = 200 * 1024;

/** Decide whether a path is worth indexing - same rules as the backend,
 * applied before upload instead of after. `relativePath` is expected to still
 * carry the selected folder's own name as its first segment (i.e. a browser
 * File's webkitRelativePath, unmodified) - that first segment is skipped when
 * checking for excluded directories, same as the backend skips the zip's
 * top-level "<repo>-<branch>/" segment, so a folder that happens to be named
 * e.g. "dist" isn't excluded for being its own name. */
export function shouldIncludeFile(relativePath: string, sizeBytes: number): boolean {
  const parts = relativePath.split('/').filter(Boolean);
  const dirParts = parts.slice(1, -1);
  if (dirParts.some((p) => EXCLUDED_DIRECTORIES.has(p.toLowerCase()))) return false;

  const filename = parts[parts.length - 1] ?? '';
  const nameLower = filename.toLowerCase();
  if (EXCLUDED_FILENAMES.has(nameLower) || nameLower.startsWith('.')) return false;
  if (EXCLUDED_SUFFIXES.some((suffix) => nameLower.endsWith(suffix))) return false;
  if (sizeBytes > MAX_FILE_BYTES) return false;

  if (INCLUDED_FILENAMES.has(nameLower)) return true;
  const dotIndex = nameLower.lastIndexOf('.');
  const extension = dotIndex >= 0 ? nameLower.slice(dotIndex + 1) : '';
  return INCLUDED_EXTENSIONS.has(extension);
}
