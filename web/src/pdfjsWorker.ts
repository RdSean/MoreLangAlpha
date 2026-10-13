// PDF.js executes in a separate realm. Keep its legacy build's required APIs
// available when the host is an older Chromium (the page polyfills do not cross
// the worker boundary).
import 'core-js/actual/array/at';
import 'core-js/actual/promise/with-resolvers';
export { WorkerMessageHandler } from 'pdfjs-dist/legacy/build/pdf.worker.mjs';
