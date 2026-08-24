import { createHighlighterCore, type HighlighterCore } from 'shiki/core';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';

// Only the languages this app's LANG_BY_EXTENSION map can produce, imported by
// name rather than through shiki's "full bundle" - the full bundle registers
// dynamic import() calls for all ~200 grammars shiki ships, which Next's
// bundler tries to statically resolve at build time and fails on, since
// @shikijs/langs/@shikijs/themes live nested under shiki's own node_modules.
const LANG_LOADERS = {
  python: () => import('@shikijs/langs/python'),
  javascript: () => import('@shikijs/langs/javascript'),
  jsx: () => import('@shikijs/langs/jsx'),
  typescript: () => import('@shikijs/langs/typescript'),
  tsx: () => import('@shikijs/langs/tsx'),
  go: () => import('@shikijs/langs/go'),
  rust: () => import('@shikijs/langs/rust'),
  java: () => import('@shikijs/langs/java'),
  kotlin: () => import('@shikijs/langs/kotlin'),
  ruby: () => import('@shikijs/langs/ruby'),
  php: () => import('@shikijs/langs/php'),
  csharp: () => import('@shikijs/langs/csharp'),
  c: () => import('@shikijs/langs/c'),
  cpp: () => import('@shikijs/langs/cpp'),
  swift: () => import('@shikijs/langs/swift'),
  scala: () => import('@shikijs/langs/scala'),
  bash: () => import('@shikijs/langs/bash'),
  sql: () => import('@shikijs/langs/sql'),
  yaml: () => import('@shikijs/langs/yaml'),
  toml: () => import('@shikijs/langs/toml'),
  json: () => import('@shikijs/langs/json'),
  html: () => import('@shikijs/langs/html'),
  css: () => import('@shikijs/langs/css'),
  scss: () => import('@shikijs/langs/scss'),
  vue: () => import('@shikijs/langs/vue'),
  svelte: () => import('@shikijs/langs/svelte'),
  markdown: () => import('@shikijs/langs/markdown'),
  mdx: () => import('@shikijs/langs/mdx'),
  ini: () => import('@shikijs/langs/ini'),
} as const;

type SupportedLang = keyof typeof LANG_LOADERS;

const LANG_BY_EXTENSION: Record<string, SupportedLang> = {
  py: 'python', js: 'javascript', jsx: 'jsx', mjs: 'javascript', ts: 'typescript', tsx: 'tsx',
  go: 'go', rs: 'rust', java: 'java', kt: 'kotlin', rb: 'ruby', php: 'php', cs: 'csharp',
  c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', hpp: 'cpp', swift: 'swift', scala: 'scala',
  sh: 'bash', bash: 'bash', sql: 'sql', yaml: 'yaml', yml: 'yaml', toml: 'toml', json: 'json',
  html: 'html', css: 'css', scss: 'scss', vue: 'vue', svelte: 'svelte',
  md: 'markdown', mdx: 'mdx', ini: 'ini', cfg: 'ini',
};

export function langForPath(path: string): SupportedLang | 'text' {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  return LANG_BY_EXTENSION[ext] ?? 'text';
}

export interface HighlightedToken {
  content: string;
  color?: string;
}

const THEME = 'github-light-default';

let highlighterPromise: Promise<HighlighterCore> | null = null;
const loadedLangs = new Set<SupportedLang>();

async function getHighlighter(lang: SupportedLang | 'text'): Promise<HighlighterCore | null> {
  if (lang === 'text') return null;

  if (!highlighterPromise) {
    highlighterPromise = createHighlighterCore({
      themes: [import('@shikijs/themes/github-light-default')],
      langs: [],
      engine: createJavaScriptRegexEngine(),
    });
  }
  const highlighter = await highlighterPromise;

  if (!loadedLangs.has(lang)) {
    await highlighter.loadLanguage(await LANG_LOADERS[lang]());
    loadedLangs.add(lang);
  }
  return highlighter;
}

/** Tokenize source into per-line, per-token color runs for a custom renderer
 * (rather than shiki's HTML string output), so line numbers and the cited
 * range's highlight can be laid out precisely around it. */
export async function highlightLines(code: string, path: string): Promise<HighlightedToken[][]> {
  const lang = langForPath(path);
  try {
    const highlighter = await getHighlighter(lang);
    if (!highlighter) throw new Error('no highlighter for plain text');

    const { tokens } = highlighter.codeToTokens(code, { lang, theme: THEME });
    return tokens.map((line) => line.map((t) => ({ content: t.content, color: t.color })));
  } catch {
    // Unknown/unsupported language for shiki - fall back to plain, uncolored lines.
    return code.split('\n').map((line) => [{ content: line }]);
  }
}
