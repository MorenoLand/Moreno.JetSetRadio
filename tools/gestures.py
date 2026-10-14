"""Read the tables of the spraying gestures from the executable of the PC release.

    python tools/gestures.py PC_DIR [--out DIR]

Writes <out>/gestures.json. The tables are in the data of jetsetradio.exe (little endian):

    0x9011B0  gestures, 0x1C bytes each, eleven used: i32 a, b, c, d, e, threshold, kind (0 flick, 1 and 2 arcs)
    0x901310  sequences: [size class 0..2][step 0..6], 0x10 bytes: three gesture numbers and the count of them
    0x90148C  per gesture: bit mask of the motions that may be played
    0x9012E4  motion numbers 102..112 (the set most skaters use), 0x901460 113..123 (the set of the pointer entries 11..13)
    0x90150C  motions the spraying starts with: 128..131
    0x907818  pointers to the parameter blocks of the 16 characters (0x280 bytes each, from 0x905018)

The code that uses them is `FUN_004E4000` (one gesture) and `FUN_004E4440` (the tagging state of the player).
"""
import json
import os
import struct
import sys


def read(pc):
    d = open(os.path.join(pc, "jetsetradio.exe"), "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    secs = []
    for i in range(n):
        o = pe + 24 + opt + 40 * i
        vs, va, rs, rp = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, vs, rp))

    def rd(addr, k):
        for va, vs, rp in secs:
            if base + va <= addr < base + va + vs:
                o = rp + addr - base - va
                return d[o:o + k]
        raise ValueError(hex(addr))

    gestures = [list(struct.unpack("<7i", rd(0x9011B0 + 0x1C * g, 0x1C))) for g in range(11)]
    sequences = []
    for size in range(3):
        row = []
        for step in range(7):
            w = struct.unpack("<4i", rd(0x901310 + (size * 7 + step) * 16, 16))
            row.append({"list": list(w[:3]), "count": w[3]})
        sequences.append(row)
    masks = [struct.unpack("<I", rd(0x90148C + 4 * g, 4))[0] for g in range(11)]
    # the parameter block of every character: [0] ?, [1] 60, [2] the size class of its gestures (the row of the
    # sequence table), [3] the most spray cans it carries
    characters = []
    for i in range(16):
        p = struct.unpack("<I", rd(0x907818 + 4 * i, 4))[0]
        characters.append(list(struct.unpack("<4i", rd(p, 16))))
    return {
        "characters": characters,
        "gestures": gestures,
        "sequences": sequences,
        "masks": masks,
        "motions_a": [struct.unpack("<i", rd(0x9012E4 + 4 * j, 4))[0] for j in range(11)],
        "motions_b": [struct.unpack("<i", rd(0x901460 + 4 * j, 4))[0] for j in range(11)],
        "start": [struct.unpack("<i", rd(0x90150C + 4 * j, 4))[0] for j in range(4)],
        "set_b_entries": [11, 12, 13],
    }


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    info = read(argv[0])
    with open(os.path.join(out, "gestures.json"), "w") as f:
        json.dump(info, f)
    print("%d gestures" % len(info["gestures"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
