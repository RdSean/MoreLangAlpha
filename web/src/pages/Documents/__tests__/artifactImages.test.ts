import { describe, expect, it } from 'vitest';
import { resolveRelativeImageSources } from '../artifactImages';
import type { Artifact } from '../types';

const ORIGIN = 'http://localhost:5177';

function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    artifact_id: 'art-AAAA1111BBBB',
    document_id: 'doc-AAAA1111BBBB',
    producer_job_id: 'job-AAAA1111BBBB',
    artifact_kind: 'embedded_image',
    format: 'jpeg',
    media_type: 'image/jpeg',
    relative_path: 'a_img.jpg',
    ...overrides,
  } as Artifact;
}

const url = (id: string) => `${ORIGIN}/api/v1/document-artifacts/${id}/download`;

describe('resolving document image references', () => {
  it('points a referenced image at its artifact', () => {
    const markdown = '![A picture](a_img.jpg)\n\nbody';

    expect(resolveRelativeImageSources(markdown, [artifact()], ORIGIN)).toBe(
      `![A picture](${url('art-AAAA1111BBBB')})\n\nbody`,
    );
  });

  it('matches a bare reference against a nested artifact path', () => {
    const markdown = '![x](a_img.jpg)';

    expect(
      resolveRelativeImageSources(
        markdown,
        [artifact({ relative_path: 'images/a_img.jpg' })],
        ORIGIN,
      ),
    ).toBe(`![x](${url('art-AAAA1111BBBB')})`);
  });

  it('prefers an exact path over another file that shares its basename', () => {
    // Two artifacts, one named in a folder and one at the root, and a
    // reference that names the root one. The nested artifact is listed first
    // on purpose: a resolver that indexes basenames before paths answers with
    // the wrong picture here.
    const nested = artifact({
      artifact_id: 'art-NESTED0001',
      relative_path: 'images/a_img.jpg',
    });
    const root = artifact({
      artifact_id: 'art-ROOT000001',
      relative_path: 'a_img.jpg',
    });

    expect(
      resolveRelativeImageSources('![x](a_img.jpg)', [nested, root], ORIGIN),
    ).toBe(`![x](${url('art-ROOT000001')})`);
  });

  it('leaves anything that already has an address alone', () => {
    const markdown = [
      '![a](https://example.com/a.png)',
      '![b](data:image/png;base64,AAAA)',
      '![c](blob:http://localhost/abc)',
    ].join('\n');

    expect(resolveRelativeImageSources(markdown, [artifact()], ORIGIN)).toBe(markdown);
  });

  it('leaves a reference with no artifact behind it alone', () => {
    // Silently deleting it would hide that the document is missing something;
    // the alt text is more useful than nothing.
    const markdown = '![missing](nowhere.jpg)';

    expect(resolveRelativeImageSources(markdown, [artifact()], ORIGIN)).toBe(markdown);
  });

  it('ignores artifacts that are not images', () => {
    const markdown = '![a](a_img.jpg)';
    const primary = artifact({
      artifact_kind: 'primary_document',
      relative_path: 'a_img.jpg',
      media_type: 'text/markdown',
    });

    expect(resolveRelativeImageSources(markdown, [primary], ORIGIN)).toBe(markdown);
  });

  it('keeps an image title', () => {
    const markdown = '![a](a_img.jpg "the caption")';

    expect(resolveRelativeImageSources(markdown, [artifact()], ORIGIN)).toBe(
      `![a](${url('art-AAAA1111BBBB')} "the caption")`,
    );
  });

  it('does not touch a plain link', () => {
    const markdown = '[the file](a_img.jpg)';

    expect(resolveRelativeImageSources(markdown, [artifact()], ORIGIN)).toBe(markdown);
  });

  it('resolves every reference in a real converted document', () => {
    const names = ['43012ae8_img.jpg', 'b29945fa_img.jpg', 'c3e977b5_img.jpg'];
    const markdown = names
      .map((name, index) => `![picture ${index}](${name})`)
      .join('\n\n');
    const artifacts = names.map((name, index) =>
      artifact({ artifact_id: `art-IMG${index}0000`, relative_path: name }),
    );

    const resolved = resolveRelativeImageSources(markdown, artifacts, ORIGIN);

    expect(resolved.match(/api\/v1\/document-artifacts/g)).toHaveLength(3);
    expect(resolved).not.toContain('](43012ae8_img.jpg)');
  });
});
