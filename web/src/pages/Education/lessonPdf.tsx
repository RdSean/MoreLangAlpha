import { renderToStaticMarkup } from 'react-dom/server';
import { ThemeProvider } from '@/contexts/ThemeContext';
import Markdown from '@/pages/ChatAgent/components/Markdown';
import katexCss from 'katex/dist/katex.min.css?inline';

export interface LessonPrintSection {
  role: 'material' | 'user' | 'assistant';
  markdown: string;
  html: string;
}

export function renderLessonSections(markdown: string, messages: readonly { role: string; content: string; content_type?: string }[]): LessonPrintSection[] {
  const records: Array<{ role: LessonPrintSection['role']; content: string }> = [{ role: 'material', content: markdown }];
  for (const message of messages) {
    if ((message.role === 'user' || message.role === 'assistant') && (message.content_type ?? 'text') === 'text' && message.content) {
      records.push({ role: message.role, content: message.content });
    }
  }
  return records.map((record) => ({
    role: record.role,
    markdown: record.content,
    html: renderToStaticMarkup(<ThemeProvider><Markdown content={record.content} codeTheme="light" /></ThemeProvider>),
  }));
}

function blobDataUrl(blob: Blob, signal: AbortSignal): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const reader = new FileReader();
    const abort = () => reader.abort();
    const cleanup = () => signal.removeEventListener('abort', abort);
    reader.onload = () => { cleanup(); resolve(String(reader.result)); };
    reader.onerror = () => { cleanup(); reject(new Error('导出字体读取失败，请重试。')); };
    reader.onabort = () => { cleanup(); reject(new DOMException('Aborted', 'AbortError')); };
    signal.addEventListener('abort', abort, { once: true });
    reader.readAsDataURL(blob);
  });
}

export async function lessonFontCss(signal: AbortSignal): Promise<string> {
  // Parse the shipped stylesheet; embed only WOFF2, not all three fallback formats.
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(katexCss);
  const rules = await Promise.all(Array.from(sheet.cssRules).map(async (rule) => {
    if (rule.type !== CSSRule.FONT_FACE_RULE) return rule.cssText;
    const face = rule as CSSFontFaceRule;
    const source = face.style.getPropertyValue('src');
    const match = /url\(["']?([^"')]+)["']?\)\s*format\(["']?woff2["']?\)/.exec(source);
    if (!match) throw new Error('导出公式字体不可用。');
    const response = await fetch(new URL(match[1], window.location.href), { credentials: 'omit', signal });
    if (!response.ok) throw new Error('导出公式字体加载失败，请重试。');
    const blob = await response.blob();
    if (blob.size > 200_000) throw new Error('导出公式字体过大。');
    const data = await blobDataUrl(new Blob([blob], { type: 'font/woff2' }), signal);
    face.style.setProperty('src', `url("${data}") format("woff2")`);
    return face.cssText;
  }));
  return rules.join('\n');
}
