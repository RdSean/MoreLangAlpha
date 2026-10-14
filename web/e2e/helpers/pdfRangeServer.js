import { createServer } from 'node:http';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export function createLargePdf() {
  return execFileSync('uv', ['run', 'python', '-c', `
import sys, random
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, NumberObject, DecodedStreamObject, ArrayObject
reader = PdfReader('tests/fixtures/documents/text.pdf')
writer = PdfWriter()
rng = random.Random(42)
for i in range(32):
    page = writer.add_page(reader.pages[0])
    image = DecodedStreamObject()
    image.set_data(rng.randbytes(256 * 256 * 3))
    image.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                  NameObject('/Width'): NumberObject(256), NameObject('/Height'): NumberObject(256),
                  NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8)})
    resources = DictionaryObject(page['/Resources'])
    resources[NameObject('/XObject')] = DictionaryObject({NameObject('/TestImage'): writer._add_object(image)})
    page[NameObject('/Resources')] = resources
    draw = DecodedStreamObject()
    draw.set_data(b'q 250 0 0 250 40 100 cm /TestImage Do Q')
    content = page.raw_get('/Contents')
    page[NameObject('/Contents')] = ArrayObject([content, writer._add_object(draw)])
output = BytesIO()
writer.write(output)
sys.stdout.buffer.write(output.getvalue())
`], { cwd: fileURLToPath(new URL('../../../', import.meta.url)), maxBuffer: 16 * 1024 * 1024 });
}

export async function startPdfRangeServer(bytes, { delay = 30, ranges = true } = {}) {
  const requests = [];
  const server = createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', req.headers.origin ?? 'http://127.0.0.1:5176');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Type');
    res.setHeader('Access-Control-Expose-Headers', 'Accept-Ranges, Content-Length, Content-Range, Content-Encoding');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
    if (!(req.headers.cookie ?? '').includes('pdf-test-session=authenticated')) {
      res.writeHead(403); res.end(); return;
    }
    const match = ranges && /^bytes=(\d+)-(\d*)$/.exec(req.headers.range ?? '');
    const start = match ? Number(match[1]) : 0;
    const end = match && match[2] ? Math.min(Number(match[2]), bytes.length - 1) : bytes.length - 1;
    const record = { range: req.headers.range ?? null, cookie: req.headers.cookie ?? '', bytesSent: 0, finished: false, cancelled: false, startedAt: Date.now() };
    requests.push(record);
    if (start >= bytes.length || end < start) {
      res.writeHead(416, { 'Content-Range': `bytes */${bytes.length}` }); res.end(); return;
    }
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Encoding', 'identity');
    res.setHeader('Cache-Control', 'private, no-store');
    res.setHeader('Content-Length', end - start + 1);
    if (ranges) res.setHeader('Accept-Ranges', 'bytes');
    if (match) res.setHeader('Content-Range', `bytes ${start}-${end}/${bytes.length}`);
    res.writeHead(match ? 206 : 200);
    res.flushHeaders();
    let offset = start;
    const timer = setInterval(() => {
      const next = Math.min(offset + 65536, end + 1);
      res.write(bytes.subarray(offset, next));
      record.bytesSent += next - offset;
      offset = next;
      if (offset > end) { record.finished = true; record.finishedAt = Date.now(); clearInterval(timer); res.end(); }
    }, match ? 1 : delay);
    res.on('close', () => { clearInterval(timer); record.cancelled = !record.finished; });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}/original.pdf`, requests,
    close: () => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); }),
  };
}
