import { Bot, HardDriveDownload, Shrink, Terminal } from 'lucide-react';
import type { SlashCommand } from './chat-input.types';

/** Return the appropriate icon for a slash command. */
export function getSlashCommandIcon(cmd: SlashCommand, className: string) {
  if (cmd.type === 'subagent') return <Bot className={className} />;
  if (cmd.name === 'offload') return <HardDriveDownload className={className} />;
  if (cmd.type === 'action') return <Shrink className={className} />;
  return <Terminal className={className} />;
}

/* --- CONSTANTS --- */
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
export const MAX_FILES = 5;
export const PASTE_PILL_MIN_CHARS = 1500;
export const PASTE_PILL_MIN_LINES = 15;

/**
 * A paste this large would flood the draft — the composer stages it as a
 * removable pill instead and flattens it back into the message on send.
 */
export function isLargePaste(text: string): boolean {
  if (text.length >= PASTE_PILL_MIN_CHARS) return true;
  let lines = 1;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\n' && ++lines >= PASTE_PILL_MIN_LINES) return true;
  }
  return false;
}
export const BUILTIN_SLASH_COMMANDS = [
  { type: 'subagent', name: 'subagent' },
  { type: 'action', name: 'compact', aliases: ['compaction', 'summarize'] },
  { type: 'action', name: 'offload', aliases: ['truncate'] },
];

/**
 * Commands the product wants at the top of the menu.
 *
 * The skill half of the list is otherwise registry-ordered, which buries
 * anything added late — and typing a bare `/` is how someone finds out what
 * exists at all. Which commands deserve that first screen is a product
 * decision, so it is stated here rather than left to the order a registry
 * happens to be written in.
 */
const FEATURED_SLASH_COMMANDS: ReadonlySet<string> = new Set([
  'book-to-skill',
  'the-knowledge-guy',
]);

/**
 * Index of the `@`/`/` token the cursor is currently inside, or -1.
 *
 * Scans left from the cursor and stops at the first whitespace: the trigger
 * only counts at a word start (beginning of the draft or after whitespace), so
 * `foo@bar` and a URL's slashes never open a menu.
 */
export function findTriggerIndex(value: string, cursorPos: number, trigger: '@' | '/'): number {
  for (let i = cursorPos - 1; i >= 0; i--) {
    const ch = value[i];
    if (ch === trigger) {
      return i === 0 || /\s/.test(value[i - 1]) ? i : -1;
    }
    if (/\s/.test(ch)) return -1;
  }
  return -1;
}

/**
 * Slash-menu sort key (lower sorts first).
 *
 * Match quality comes first: a prefix match (the name or an alias starts with
 * the query, char-by-char) beats a substring-only one. Within a match quality:
 * featured commands, then system/service commands, then the rest of the
 * skills. So a bare `/` opens with the featured skills and `/d` still puts
 * `/dcf-model` above a featured command that merely contains a "d".
 */
export function slashRank(item: SlashCommand, query: string): number {
  const isPrefix =
    item.name.toLowerCase().startsWith(query) ||
    !!item.aliases?.some((a) => a.toLowerCase().startsWith(query));
  const tier = FEATURED_SLASH_COMMANDS.has(item.name)
    ? 0
    : item.type === 'skill'
      ? 2
      : 1;
  return (isPrefix ? 0 : 10) + tier;
}

/** Derive a short display name from a model key string. */
export function getModelDisplayName(key: string | null): string {
  if (!key) return '';
  let name = key;
  // Strip common provider prefixes
  for (const prefix of ['claude-', 'gpt-', 'chatgpt-', 'o1-', 'o3-', 'o4-']) {
    if (name.startsWith(prefix)) { name = name.slice(prefix.length); break; }
  }
  // Convert version-like patterns: "opus-4-6" → "Opus 4.6", "sonnet-4-6" → "Sonnet 4.6"
  name = name
    .replace(/-(\d+)-(\d+)/, ' $1.$2')
    .replace(/-(\d+\.\d+)/, ' $1')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c: string) => c.toUpperCase());
  return name;
}
