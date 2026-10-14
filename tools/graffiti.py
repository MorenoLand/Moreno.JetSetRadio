"""Export the pictures that can be sprayed (E_GRF.AFS).

    python tools/graffiti.py [--game DIR] [--out DIR] [--pack E_GRF.AFS]

Members 5 to 115 are raw 16 bit pictures, ARGB 4-4-4-4, little endian words, without a header; the size follows from
the length of the member: 131072 bytes 256 x 256, 65536 bytes 256 x 128, 32768 bytes 128 x 128 (37 of each). They are
written to <out>/graffiti/<member>.png and listed in <out>/graffiti.json by size.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import pvr

SIZES = {131072: (256, 256), 65536: (256, 128), 32768: (128, 128)}


def export(game, out, pack="E_GRF.AFS"):
    a = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", pack))
    folder = os.path.join(out, "graffiti")
    os.makedirs(folder, exist_ok=True)
    index = {"256x256": [], "256x128": [], "128x128": []}
    for m in range(len(a)):
        data = a.read(m)
        size = SIZES.get(len(data))
        if size is None or m < 5 or m > 115:
            continue
        w, h = size
        words = struct.unpack("<%dH" % (w * h), data)
        rgba = bytearray(w * h * 4)
        for i, v in enumerate(words):
            rgba[4 * i] = ((v >> 8) & 15) * 17
            rgba[4 * i + 1] = ((v >> 4) & 15) * 17
            rgba[4 * i + 2] = (v & 15) * 17
            rgba[4 * i + 3] = ((v >> 12) & 15) * 17
        pvr.write_png(os.path.join(folder, "%d.png" % m), w, h, bytes(rgba))
        index["%dx%d" % size].append("graffiti/%d.png" % m)
    with open(os.path.join(out, "graffiti.json"), "w") as f:
        json.dump(index, f)
    return {k: len(v) for k, v in index.items()}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    pack = argv[argv.index("--pack") + 1] if "--pack" in argv else "E_GRF.AFS"
    print(export(game, out, pack))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
