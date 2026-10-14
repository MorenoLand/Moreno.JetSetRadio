"""Read the ARCB containers of the HD port (CUSTOM/MUSIC.ARC, SOUNDS.ARC, IMAGES.ARC, FONTS.ARC).

    python tools/arc.py FILE [--extract DIR]

Layout: "ARCB" (Xbox 360) or "ARCL" (PC, little endian throughout), a u16 count, then count entries of 0x48 bytes: a 64 byte null-terminated name,
u32 offset and u32 size (big endian), 0x40 and 0x44 into the entry. The entries are scrambled with a byte stream of
the minimal standard generator (x' = 48271 * x mod 2^31 - 1, seeded with the entry count): each byte is XORed with
the low byte of x' plus the low byte of x' / 255. The members are stored as they are.
"""
import os
import struct
import sys


def _stream(seed):
    x = seed
    while True:
        # Schrage's method, as the game computes it
        t = 48271 * (x % 44488) - 3399 * (x // 44488)
        if t < 1:
            t += 0x7FFFFFFF
        x = t
        yield (x + x // 255) & 0xFF


class Container:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(6)
            if head[:4] not in (b"ARCB", b"ARCL"):
                raise ValueError("not an ARCB or ARCL container")
            order = ">" if head[:4] == b"ARCB" else "<"
            count = struct.unpack(order + "H", head[4:6])[0]
            raw = bytearray(f.read(count * 0x48))
        key = _stream(count)
        for i in range(len(raw)):
            raw[i] ^= next(key)
        self.entries = []
        for i in range(count):
            e = raw[i * 0x48:(i + 1) * 0x48]
            name = bytes(e[:0x40]).split(b"\0")[0].decode("latin-1")
            offset, size = struct.unpack(order + "II", bytes(e[0x40:0x48]))
            self.entries.append((name, offset, size))

    def read(self, index):
        _, offset, size = self.entries[index]
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(size)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    c = Container(argv[0])
    out = argv[argv.index("--extract") + 1] if "--extract" in argv else None
    for i, (name, offset, size) in enumerate(c.entries):
        print("%3d %-48s offset %10d size %9d" % (i, name, offset, size))
        if out:
            path = os.path.join(out, name.replace("\\", "/"))
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(c.read(i))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
