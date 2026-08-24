import { zip, type Zippable } from 'fflate';
import { shouldIncludeFile } from './repoFilter';

// Mirrors backend/ragbot/api/routes/repos.py's MAX_UPLOAD_BYTES - checked
// again server-side regardless, but failing fast client-side avoids zipping
// and uploading a huge tree only to have it rejected at the end.
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

export interface FolderSelection {
  name: string;
  fileCount: number;
  zipBytes: Uint8Array;
}

/**
 * Filter a browser folder selection down to indexable files (see
 * repoFilter.ts - the same allowlist the backend applies), zip them
 * in-memory, and return the archive ready to upload as a single file.
 *
 * Reads every included file into memory before zipping, so this is bounded by
 * what a browser tab can hold - fine for a source repo post-filtering, not
 * meant for arbitrary large binary trees (MAX_FILE_BYTES already excludes
 * anything over 200KB per file, and MAX_UPLOAD_BYTES caps the total).
 */
export async function buildFolderUpload(fileList: FileList | File[]): Promise<FolderSelection> {
  const files = Array.from(fileList).filter(
    (f) => f.webkitRelativePath && shouldIncludeFile(f.webkitRelativePath, f.size),
  );

  if (files.length === 0) {
    throw new Error('No indexable files found in that folder.');
  }

  const name = files[0].webkitRelativePath.split('/')[0] || 'repo';

  const entries: Zippable = {};
  for (const file of files) {
    entries[file.webkitRelativePath] = new Uint8Array(await file.arrayBuffer());
  }

  const zipBytes = await new Promise<Uint8Array>((resolve, reject) => {
    zip(entries, (err, data) => {
      if (err) reject(err);
      else resolve(data);
    });
  });

  if (zipBytes.byteLength > MAX_UPLOAD_BYTES) {
    const mb = (n: number) => Math.round(n / (1024 * 1024));
    throw new Error(
      `That folder is too large to upload (${mb(zipBytes.byteLength)}MB, limit ${mb(MAX_UPLOAD_BYTES)}MB).`,
    );
  }

  return { name, fileCount: files.length, zipBytes };
}
