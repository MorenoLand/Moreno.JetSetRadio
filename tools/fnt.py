"""Read the bitmap fonts (`FNT1`) of the PC release (CUSTOM/FONTS.ARC) and write each as a picture and a glyph table.

    python tools/fnt.py FONTS.ARC [--out DIR]

A font file is little endian:

    char[4]  "FNT1"
    f32      line height
    f32 f32  two more metrics (2.0 in every font seen)
    f32      baseline
    u32 u32  size of the picture in pixels
    u32      number of table entries plus one
    u16[]    character code (UTF-16) -> glyph number + 1, 0 = no glyph
    glyph[]  12 bytes each: i16 x offset, u16 advance, u16 left, top, right, bottom (rectangle in the picture)
    u16[]    the picture, two bytes a pixel: luminance, alpha (white letters with a black edge)

Output: <out>/fonts/<name>.png (white letters with the alpha of the picture, tint it to colour the letters, the
dark edge stays) and <out>/fonts/<name>.json with the line height and `glyphs`, a map of character code to
[x offset, advance, left, top, right, bottom].
"""
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arc


def png_bytes(w, h, rgba):
    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def read(data):
    """(info, rgba bytes) of a font file, or None when the layout is not the one described above."""
    if data[:4] != b"FNT1":
        return None
    line, _, _, base = struct.unpack_from("<4f", data, 4)
    w, h, entries = struct.unpack_from("<3I", data, 20)
    count = entries - 1
    table = struct.unpack_from("<%dH" % count, data, 32)
    glyphs_at = 32 + 2 * count
    picture_at = len(data) - w * h * 2
    if picture_at < glyphs_at or w * h > 4096 * 4096:
        return None
    n = (picture_at - glyphs_at) // 12
    glyphs = {}
    for code, v in enumerate(table):
        if v == 0 or v - 1 >= n:
            continue
        xo, adv, x0, y0, x1, y1 = struct.unpack_from("<hHHHHH", data, glyphs_at + 12 * (v - 1))
        if x1 > w or y1 > h or x1 <= x0 and y1 <= y0:
            continue
        glyphs[code] = [xo, adv, x0, y0, x1, y1]
    pixels = struct.unpack_from("<%dH" % (w * h), data, picture_at)
    rgba = bytearray(w * h * 4)
    for i, v in enumerate(pixels):
        lum = v & 0xFF
        rgba[4 * i] = rgba[4 * i + 1] = rgba[4 * i + 2] = lum
        rgba[4 * i + 3] = v >> 8
    return {"line": line, "base": base, "size": [w, h], "glyphs": glyphs}, bytes(rgba)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    container = arc.Container(argv[0])
    os.makedirs(os.path.join(out, "fonts"), exist_ok=True)
    for i, (name, _, _) in enumerate(container.entries):
        if not name.lower().endswith(".fnt"):
            continue
        got = read(container.read(i))
        if got is None:
            print("%-28s not read" % name)
            continue
        info, rgba = got
        stem = os.path.splitext(name)[0].lower()
        with open(os.path.join(out, "fonts", stem + ".png"), "wb") as f:
            f.write(png_bytes(info["size"][0], info["size"][1], rgba))
        info["glyphs"] = {str(k): v for k, v in info["glyphs"].items()}
        with open(os.path.join(out, "fonts", stem + ".json"), "w") as f:
            json.dump(info, f)
        print("%-28s %d glyphs, %dx%d" % (name, len(info["glyphs"]), info["size"][0], info["size"][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
