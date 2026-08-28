/**
 * Generate all favicon / PWA raster icons from the source SVGs in public/.
 *
 *   node scripts/generate-icons.mjs
 *
 * Re-run whenever public/favicon.svg or public/maskable-icon.svg changes.
 * Sources of truth are the SVGs; the PNGs/ICO here are build artifacts.
 */
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import sharp from "sharp";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pub = join(root, "public");

const rounded = await readFile(join(pub, "favicon.svg"));
const maskable = await readFile(join(pub, "maskable-icon.svg"));

// [source svg, output filename, size]
const targets = [
  [rounded, "pwa-192x192.png", 192],
  [rounded, "pwa-512x512.png", 512],
  [rounded, "apple-touch-icon.png", 180],
  [rounded, "favicon-32x32.png", 32],
  [rounded, "favicon-16x16.png", 16],
  [maskable, "maskable-icon-512x512.png", 512],
];

for (const [svg, name, size] of targets) {
  await sharp(svg).resize(size, size).png({ compressionLevel: 9 }).toFile(join(pub, name));
  console.log(`  ✓ ${name} (${size}×${size})`);
}

// Assemble a multi-resolution favicon.ico from the 16 & 32 PNGs.
// ICO entries may be PNG-encoded, so we just embed the PNG bytes directly.
async function pngBuffer(size) {
  return sharp(rounded).resize(size, size).png({ compressionLevel: 9 }).toBuffer();
}
const sizes = [16, 32, 48];
const images = await Promise.all(sizes.map(pngBuffer));

const header = Buffer.alloc(6);
header.writeUInt16LE(0, 0); // reserved
header.writeUInt16LE(1, 2); // type: icon
header.writeUInt16LE(images.length, 4); // image count

const dirEntries = [];
let offset = 6 + images.length * 16;
images.forEach((img, i) => {
  const e = Buffer.alloc(16);
  const s = sizes[i];
  e.writeUInt8(s >= 256 ? 0 : s, 0); // width
  e.writeUInt8(s >= 256 ? 0 : s, 1); // height
  e.writeUInt8(0, 2); // palette
  e.writeUInt8(0, 3); // reserved
  e.writeUInt16LE(1, 4); // color planes
  e.writeUInt16LE(32, 6); // bits per pixel
  e.writeUInt32LE(img.length, 8); // data size
  e.writeUInt32LE(offset, 12); // data offset
  offset += img.length;
  dirEntries.push(e);
});

await writeFile(join(pub, "favicon.ico"), Buffer.concat([header, ...dirEntries, ...images]));
console.log("  ✓ favicon.ico (16/32/48)");
console.log("Done.");
