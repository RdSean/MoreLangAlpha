import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

function localHosts() {
  const addresses = Object.values(os.networkInterfaces())
    .flatMap((entries) => entries || [])
    .filter((entry) => entry.family === 'IPv4' && !entry.internal)
    .map((entry) => entry.address)
  return ['localhost', '127.0.0.1', ...addresses]
}

/** Create a local-only certificate for browsers that require HTTPS media access. */
export function createDevHttpsOptions(rootDir) {
  const certDir = path.join(rootDir, '.vite-dev-https')
  const keyPath = path.join(certDir, 'key.pem')
  const certPath = path.join(certDir, 'cert.pem')
  if (!fs.existsSync(keyPath) || !fs.existsSync(certPath)) {
    fs.mkdirSync(certDir, { recursive: true, mode: 0o700 })
    const san = localHosts()
      .map((host) => host === 'localhost' ? `DNS:${host}` : `IP:${host}`)
      .join(',')
    execFileSync('openssl', [
      'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
      '-keyout', keyPath, '-out', certPath, '-days', '365',
      '-subj', '/CN=LangAlpha local development',
      '-addext', `subjectAltName=${san}`,
    ], { stdio: 'ignore' })
    fs.chmodSync(keyPath, 0o600)
  }
  return {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath),
  }
}
