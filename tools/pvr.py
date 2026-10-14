"""Decode PVR textures (GBIX + PVRT blocks) to RGBA and write PNG files.

    python tools/pvr.py ARCHIVE_OR_FILE [--member N] [--out DIR]    # decode and write PNGs
    python tools/pvr.py ARCHIVE_OR_FILE --check                     # decode everything, report problems

Pixel formats: 0 ARGB1555, 1 RGB565, 2 ARGB4444 (little endian 16-bit words).
Data formats: 0x01 twiddled, 0x02/0x12 twiddled with mip maps, 0x03 vector quantised, 0x04 vector quantised with mip maps,
0x09 rectangle, 0x0B stride, 0x0D twiddled rectangle, 0x10 small vector quantised, 0x11 small vector quantised with mip maps.
Only the full-size level is decoded. Standard library only.
"""
import os
import struct
import sys
import zlib

ARGB1555, RGB565, ARGB4444 = 0, 1, 2


class PvrError(Exception):
    pass


def _make_tables():
    tables = []
    t = []
    for v in range(65536):
        a = 255 if v & 0x8000 else 0
        r = (v >> 10) & 31
        g = (v >> 5) & 31
        b = v & 31
        t.append(bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, a)))
    tables.append(t)
    t = []
    for v in range(65536):
        r = (v >> 11) & 31
        g = (v >> 5) & 63
        b = v & 31
        t.append(bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2, 255)))
    tables.append(t)
    t = []
    for v in range(65536):
        a = (v >> 12) & 15
        r = (v >> 8) & 15
        g = (v >> 4) & 15
        b = v & 15
        t.append(bytes((r * 17, g * 17, b * 17, a * 17)))
    tables.append(t)
    return tables


_TABLES = None


def _spread(n):
    """Insert a zero bit between the bits of n (Morton order)."""
    out = 0
    bit = 0
    while n:
        out |= (n & 1) << (2 * bit)
        n >>= 1
        bit += 1
    return out


_SPREAD = [_spread(i) for i in range(2048)]


def twiddle(x, y):
    return (_SPREAD[x] << 1) | _SPREAD[y]


def _mip_sizes(n):
    """Sizes of the levels below a square of side n: 1, 2, 4 ... n/2."""
    s = 1
    while s < n:
        yield s
        s *= 2


def iter_textures(data):
    """Yield (global index, pixel format, data format, width, height, payload) for each GBIX/PVRT pair in data."""
    for q, gbix, pvrt, end in locate(data):
        pixel, fmt = data[pvrt + 8], data[pvrt + 9]
        w, h = struct.unpack_from("<HH", data, pvrt + 12)
        yield gbix, pixel, fmt, w, h, data[pvrt + 16:end]


def locate(data):
    """Yield (offset, global index, PVRT offset, payload end) for every texture in a pack.

    Some headers carry a length that runs past the texture, so a payload ends at the
    earlier of its stated length and the start of the next texture.
    """
    starts = []
    q = data.find(b"GBIX")
    while q >= 0:
        if q % 4 == 0 and q + 16 <= len(data):
            length = struct.unpack_from("<I", data, q + 4)[0]
            if length < 64 and data[q + 8 + length:q + 12 + length] == b"PVRT":
                starts.append(q)
        q = data.find(b"GBIX", q + 4)
    for i, q in enumerate(starts):
        length = struct.unpack_from("<I", data, q + 4)[0]
        gbix = struct.unpack_from("<I", data, q + 8)[0] if length >= 4 else None
        pvrt = q + 8 + length
        stated = pvrt + 8 + struct.unpack_from("<I", data, pvrt + 4)[0]
        limit = starts[i + 1] if i + 1 < len(starts) else len(data)
        yield q, gbix, pvrt, min(stated, limit)



_SMALL_BOOKS = (16, 32, 64, 128, 256)


def _small_book(width, mips):
    """Code book entries of a small vector quantised texture."""
    if width <= 16:
        return 16
    if width == 32:
        return 64 if mips else 32
    if width == 64:
        return 256 if mips else 128
    return 256


def decode(pixel, fmt, w, h, payload):
    """Return RGBA bytes (w * h * 4) for the full-size level."""
    global _TABLES
    if pixel not in (ARGB1555, RGB565, ARGB4444):
        raise PvrError("pixel format %d" % pixel)
    if _TABLES is None:
        _TABLES = _make_tables()
    table = _TABLES[pixel]

    if fmt in (0x01, 0x02, 0x12):
        if w != h:
            raise PvrError("twiddled data format %#x with a %dx%d image" % (fmt, w, h))
        start = 0
        if fmt != 0x01:
            small = sum(s * s for s in _mip_sizes(w))
            start = len(payload) - 2 * (w * w) - 2 * small
            start = max(start, 0) + 2 * small
        words = struct.unpack_from("<%dH" % (w * w), payload, start)
        return _untwiddle(words, w, h, table)

    if fmt == 0x0D:
        n = min(w, h)
        words = struct.unpack_from("<%dH" % (w * h), payload, 0)
        out = bytearray(w * h * 4)
        blocks = (max(w, h)) // n
        for b in range(blocks):
            sub = words[b * n * n:(b + 1) * n * n]
            part = _untwiddle(sub, n, n, table)
            for y in range(n):
                row = part[y * n * 4:(y + 1) * n * 4]
                if w > h:
                    at = (y * w + b * n) * 4
                else:
                    at = ((b * n + y) * w) * 4
                out[at:at + n * 4] = row
        return bytes(out)

    if fmt in (0x09, 0x0B):
        words = struct.unpack_from("<%dH" % (w * h), payload, 0)
        return b"".join([table[v] for v in words])

    if fmt in (0x03, 0x04, 0x10, 0x11):
        mips = fmt in (0x04, 0x11)
        # indices of the full level: one byte per 2x2 block
        index_bytes = (w // 2) * (h // 2)
        small = 0
        if mips:
            for s in _mip_sizes(min(w, h)):
                small += max(1, (s // 2) * (s // 2))
        book_bytes = len(payload) - index_bytes - small
        if fmt in (0x03, 0x04):
            book_bytes = 2048
        elif book_bytes % 8 or book_bytes // 8 not in _SMALL_BOOKS:
            # trailing padding after the data: take the code book size from the image size
            book_bytes = 8 * _small_book(w, mips)
        entries = book_bytes // 8
        if book_bytes < 8 or book_bytes % 8 or entries > 256:
            raise PvrError("vector quantised size mismatch (%d bytes of codebook)" % book_bytes)
        book = struct.unpack_from("<%dH" % (entries * 4), payload, 0)
        # one 2x2 block per entry: pixels in twiddled order (0,0) (0,1) (1,0) (1,1) as (x, y)
        cells = []
        for e in range(entries):
            p = [table[v] for v in book[e * 4:e * 4 + 4]]
            cells.append((p[0] + p[2], p[1] + p[3]))      # top row: (x0,y0) (x1,y0); bottom row: (x0,y1) (x1,y1)
        base = book_bytes + small
        idx = payload[base:base + index_bytes]
        if len(idx) < index_bytes - 64:
            raise PvrError("vector quantised indices truncated")
        # a few textures lose the end of their last row of blocks; the missing indices read as the first entry
        idx = idx + bytes(index_bytes - len(idx))
        bw, bh = w // 2, h // 2
        top = [None] * bh
        bottom = [None] * bh
        rows_t = [[None] * bw for _ in range(bh)]
        rows_b = [[None] * bw for _ in range(bh)]
        if bw == bh:
            for by in range(bh):
                st = rows_t[by]
                sb = rows_b[by]
                for bx in range(bw):
                    c = cells[idx[twiddle(bx, by)] % entries]
                    st[bx] = c[0]
                    sb[bx] = c[1]
        else:
            nmin = min(bw, bh)
            nblocks = max(bw, bh) // nmin
            for blk in range(nblocks):
                for by in range(nmin):
                    for bx in range(nmin):
                        c = cells[idx[blk * nmin * nmin + twiddle(bx, by)] % entries]
                        if bw > bh:
                            rows_t[by][blk * nmin + bx] = c[0]
                            rows_b[by][blk * nmin + bx] = c[1]
                        else:
                            rows_t[blk * nmin + by][bx] = c[0]
                            rows_b[blk * nmin + by][bx] = c[1]
        out = []
        for by in range(bh):
            out.append(b"".join(rows_t[by]))
            out.append(b"".join(rows_b[by]))
        return b"".join(out)

    raise PvrError("data format %#x" % fmt)


def _untwiddle(words, w, h, table):
    out = [None] * (w * h)
    tw_y = [_SPREAD[y] for y in range(h)]
    for y in range(h):
        ty = tw_y[y]
        base = y * w
        for x in range(w):
            out[base + x] = table[words[(_SPREAD[x] << 1) | ty]]
    return b"".join(out)


def png_bytes(w, h, rgba):
    def chunk(tag, body):
        c = struct.pack(">I", len(body)) + tag + body
        return c + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    return png


def write_png(path, w, h, rgba):
    with open(path, "wb") as f:
        f.write(png_bytes(w, h, rgba))


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    path = argv[0]
    member = int(argv[argv.index("--member") + 1]) if "--member" in argv else None
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    check = "--check" in argv
    if path.upper().endswith(".AFS"):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import afs
        arc = afs.Archive(path)
        blobs = [(i, arc.read(i)) for i in range(len(arc)) if member is None or i == member]
    else:
        with open(path, "rb") as f:
            blobs = [(0, f.read())]
    ok = bad = 0
    problems = {}
    for index, data in blobs:
        for n, (gbix, pixel, fmt, w, h, payload) in enumerate(iter_textures(data)):
            try:
                rgba = decode(pixel, fmt, w, h, payload)
            except (PvrError, struct.error) as e:
                bad += 1
                problems.setdefault("%s (pixel %d, data %#x)" % (e, pixel, fmt), 0)
                problems["%s (pixel %d, data %#x)" % (e, pixel, fmt)] += 1
                continue
            ok += 1
            if out_dir and not check:
                os.makedirs(out_dir, exist_ok=True)
                name = "%03d_%02d_%s_%dx%d.png" % (index, n, ("%08X" % gbix) if gbix is not None else "nogbix", w, h)
                write_png(os.path.join(out_dir, name), w, h, rgba)
    print("decoded %d textures, %d failed" % (ok, bad))
    for k, v in sorted(problems.items(), key=lambda kv: -kv[1]):
        print("  %5d  %s" % (v, k))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
