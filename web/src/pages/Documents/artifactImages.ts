import { artifactDownloadUrl } from './api';
import type { Artifact } from './types';

/**
 * Point a stored document's image references at the artifacts that hold them.
 *
 * Datalab writes markdown that references its images by bare filename
 * (`![desc](43012ae8…_img.jpg)`) and we store each image beside the markdown
 * under exactly that name, so the reference is resolvable — but only by a
 * reader that knows the artifact list. This is that reader.
 *
 * Two deliberate choices:
 *
 * - The rewritten URL is **absolute** (origin included). The shared Markdown
 *   component sends every non-external `src` to `WorkspaceImage`, which reads
 *   from the *workspace* — the wrong bucket for document artifacts, and a 404
 *   for all of them. An absolute same-origin URL is left alone by that
 *   component and fetched by the browser with the session cookie, which is
 *   exactly the owner-checked artifact endpoint we want.
 * - An unmatched reference is left as written. Deleting it would hide that the
 *   document is missing a picture; the alt text is more use than nothing.
 */
export function resolveRelativeImageSources(
  markdown: string,
  artifacts: Artifact[] | undefined,
  origin: string,
): string {
  if (!markdown || !artifacts?.length) return markdown;

  const images = artifacts.filter((artifact) => artifact.artifact_kind === 'embedded_image');
  if (!images.length) return markdown;

  const index = new Map<string, string>();
  const remember = (key: string, artifact: Artifact) => {
    if (key && !index.has(key)) index.set(key, absoluteUrl(artifactDownloadUrl(artifact.artifact_id), origin));
  };
  // Exact paths first, so `images/a.jpg` never loses to a bare `a.jpg`.
  images.forEach((artifact) => remember(artifact.relative_path, artifact));
  images.forEach((artifact) => remember(basename(artifact.relative_path), artifact));

  return markdown.replace(
    /(!\[[^\]]*\]\()([^)\s]+)([^)]*\))/g,
    (whole, head: string, reference: string, tail: string) => {
      const target = index.get(stripRelativePrefix(decodeReference(reference)));
      return target ? `${head}${target}${tail}` : whole;
    },
  );
}

function basename(path: string): string {
  const parts = path.split('/');
  return parts[parts.length - 1] ?? '';
}

function stripRelativePrefix(reference: string): string {
  return reference.startsWith('./') ? reference.slice(2) : reference;
}

/** LLMs and converters both percent-encode punctuation in file names. */
function decodeReference(reference: string): string {
  try {
    return decodeURIComponent(reference);
  } catch {
    return reference;
  }
}

function absoluteUrl(url: string, origin: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;
  const separator = url.startsWith('/') ? '' : '/';
  return `${origin}${separator}${url}`;
}
