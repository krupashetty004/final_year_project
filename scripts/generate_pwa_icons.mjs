import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function makeChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crcBuf = Buffer.alloc(4);
  const combined = Buffer.concat([typeBuf, data]);
  crcBuf.writeUInt32BE(crc32(combined), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function createSolidIconPng(size, paddingRatio = 0.0) {
  const width = size;
  const height = size;
  const raw = Buffer.alloc((width * 4 + 1) * height);
  const pad = Math.floor(size * paddingRatio);
  const innerMin = pad;
  const innerMax = size - pad;
  const doorLeft = Math.floor(size * 0.42);
  const doorRight = Math.floor(size * 0.58);
  const doorTop = Math.floor(size * 0.52);
  const roofBottom = Math.floor(size * 0.36);

  for (let y = 0; y < height; y++) {
    const rowStart = y * (width * 4 + 1);
    raw[rowStart] = 0;
    for (let x = 0; x < width; x++) {
      const idx = rowStart + 1 + x * 4;
      // Background #0F766E (15, 118, 110)
      let r = 15, g = 118, b = 110, a = 255;

      const inSafeX = x >= innerMin + size * 0.16 && x <= innerMax - size * 0.16;
      const inSafeY = y >= innerMin + size * 0.18 && y <= innerMax - size * 0.18;

      if (inSafeX && inSafeY) {
        if (y <= roofBottom) {
          // Awning #CCFBF1
          r = 204; g = 251; b = 241;
        } else if (x >= doorLeft && x <= doorRight && y >= doorTop) {
          // Doorway #0F766E
          r = 15; g = 118; b = 110;
        } else {
          // Storefront body #FFFFFF
          r = 255; g = 255; b = 255;
        }
      }

      raw[idx] = r;
      raw[idx + 1] = g;
      raw[idx + 2] = b;
      raw[idx + 3] = a;
    }
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  const compressed = zlib.deflateSync(raw);
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  return Buffer.concat([
    sig,
    makeChunk('IHDR', ihdr),
    makeChunk('IDAT', compressed),
    makeChunk('IEND', Buffer.alloc(0)),
  ]);
}

const outDir = path.resolve('public');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'pwa-192x192.png'), createSolidIconPng(192, 0.04));
fs.writeFileSync(path.join(outDir, 'pwa-512x512.png'), createSolidIconPng(512, 0.04));
fs.writeFileSync(path.join(outDir, 'pwa-maskable-512x512.png'), createSolidIconPng(512, 0.15));
fs.writeFileSync(path.join(outDir, 'apple-touch-icon.png'), createSolidIconPng(180, 0.04));
console.log('Generated PWA PNG icons in public/.');
