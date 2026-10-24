import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const base = fileURLToPath(new URL('../dist/', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.md': 'text/plain; charset=utf-8' };
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let name = decodeURIComponent(url.pathname).replace(/^\/SadRobo(?=\/|$)/, '');
    if (name.endsWith('/')) name += 'index.html';
    const target = path.resolve(base, '.' + name);
    if (!target.startsWith(base)) throw new Error('Outside static root');
    const data = await readFile(target);
    res.writeHead(200, { 'Content-Type': types[path.extname(target)] || 'application/octet-stream' });
    res.end(data);
  } catch { res.writeHead(404); res.end('Not found'); }
});
const port = Number(process.env.PORT || 4317);
server.listen(port, '127.0.0.1', () => console.log(`Local: http://127.0.0.1:${port}/SadRobo/`));
