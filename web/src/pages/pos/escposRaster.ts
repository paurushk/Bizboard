/** 1-bit ESC/POS raster (GS v 0). Text mode stays the fast path; this prints any script. */

export function rasterCommand(width: number, height: number, rgba: Uint8ClampedArray): Uint8Array {
  const widthBytes = Math.ceil(width / 8);
  const body = new Uint8Array(8 + widthBytes * height);
  body[0] = 0x1d;
  body[1] = 0x76;
  body[2] = 0x30;
  body[3] = 0x00;
  body[4] = widthBytes & 0xff;
  body[5] = (widthBytes >> 8) & 0xff;
  body[6] = height & 0xff;
  body[7] = (height >> 8) & 0xff;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const ink = rgba[i] < 128;
      if (ink) {
        const byte = 8 + y * widthBytes + (x >> 3);
        body[byte] |= 0x80 >> (x & 7);
      }
    }
  }
  return body;
}
