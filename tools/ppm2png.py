#!/usr/bin/env python3
"""Convert P6 binary PPM to standard PNG using only Python's built-in zlib & struct."""
import struct
import sys
import zlib

def ppm_to_png(ppm_path, png_path):
    with open(ppm_path, "rb") as f:
        # Read header
        magic = f.readline().strip()
        if magic != b"P6":
            raise ValueError("Expected P6 binary PPM format")
        
        dims = f.readline().strip()
        while dims.startswith(b"#"):
            dims = f.readline().strip()
        
        parts = dims.split()
        if len(parts) == 2:
            width, height = int(parts[0]), int(parts[1])
            maxval = int(f.readline().strip())
        else:
            width = int(parts[0])
            height = int(parts[1])
            maxval = int(parts[2])

        raw_pixels = f.read()

    # PNG format
    raw_data = bytearray()
    row_bytes = width * 3
    for y in range(height):
        raw_data.append(0)  # Filter byte: None
        raw_data.extend(raw_pixels[y * row_bytes : (y + 1) * row_bytes])

    compressed = zlib.compress(bytes(raw_data), level=9)

    def make_chunk(chunk_type, data):
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_chunk = make_chunk(b"IHDR", ihdr_data)

    # IDAT
    idat_chunk = make_chunk(b"IDAT", compressed)

    # IEND
    iend_chunk = make_chunk(b"IEND", b"")

    with open(png_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(ihdr_chunk)
        f.write(idat_chunk)
        f.write(iend_chunk)

    print(f"[ppm2png] Converted {ppm_path} ({width}x{height}) -> {png_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ppm2png.py <input.ppm> <output.png>")
        sys.exit(1)
    ppm_to_png(sys.argv[1], sys.argv[2])
