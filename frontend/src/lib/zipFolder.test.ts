import { unzipSync } from 'fflate';
import { describe, expect, it } from 'vitest';
import { buildFolderUpload } from './zipFolder';

function fakeFile(relativePath: string, content: string): File {
  const file = new File([content], relativePath.split('/').pop()!, { type: 'text/plain' });
  // webkitRelativePath is read-only and not settable via the File
  // constructor - it's how <input webkitdirectory> reports a picked file's
  // path within the chosen folder, which is exactly what's under test here.
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
}

describe('buildFolderUpload', () => {
  it('zips only the files that pass the repo filter', async () => {
    const files = [
      fakeFile('myproject/src/app.py', 'def f(): pass'),
      fakeFile('myproject/node_modules/lib/index.js', 'module.exports = {}'),
      fakeFile('myproject/README.md', '# hi'),
    ];

    const result = await buildFolderUpload(files);

    expect(result.fileCount).toBe(2);
    expect(result.name).toBe('myproject');

    const unzipped = unzipSync(result.zipBytes);
    expect(Object.keys(unzipped).sort()).toEqual(['myproject/README.md', 'myproject/src/app.py']);
  });

  it('preserves file contents through the zip round-trip', async () => {
    const files = [fakeFile('repo/src/app.py', 'def hybrid_search(): pass')];

    const result = await buildFolderUpload(files);
    const unzipped = unzipSync(result.zipBytes);
    const content = new TextDecoder().decode(unzipped['repo/src/app.py']);

    expect(content).toBe('def hybrid_search(): pass');
  });

  it('derives the folder name from the first included file', async () => {
    const files = [fakeFile('CoolRepo/a.py', 'x = 1')];

    const result = await buildFolderUpload(files);

    expect(result.name).toBe('CoolRepo');
  });

  it('throws when every file is filtered out', async () => {
    const files = [fakeFile('myproject/node_modules/lib/index.js', 'module.exports = {}')];

    await expect(buildFolderUpload(files)).rejects.toThrow('No indexable files found');
  });

  it('throws on an empty selection', async () => {
    await expect(buildFolderUpload([])).rejects.toThrow('No indexable files found');
  });
});
