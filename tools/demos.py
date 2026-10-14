"""Write the recorded demonstrations of the PC release (DATA/JETRADIO/PLAYDEMO.AFS) as assets/demos.json.

    python tools/demos.py PC_DIR [--out DIR]

Each member is a table of up to four pointers (at 0x8CFE0000, little endian) to input streams. A stream is a header of
eight words (scene number, a float, the start position x y z, the heading, two more) and, from byte 0x24 on, records of four
bytes: byte 0 the number of extra frames the record is held (bit 7 ends the demo), byte 1 the buttons, byte 2 the angle of
the stick (256 per turn) and byte 3 its strength. Frames are 60 a second.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs


def read_stream(data, offset):
    scene, speed, x, y, z, heading, a, b = struct.unpack_from("<If3f3i", data, offset)
    records = []
    q = offset + 0x24
    while q + 4 <= len(data):
        wait, buttons, angle, strength = data[q], data[q + 1], data[q + 2], data[q + 3]
        records.append([wait & 0x7F, buttons, angle, strength])
        if wait & 0x80:
            break
        q += 4
    return {"scene": scene, "start": [round(x, 2), round(y, 2), round(z, 2)], "heading": heading, "records": records}


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    pc = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    arc = afs.Archive(os.path.join(pc, "DATA", "JETRADIO", "PLAYDEMO.AFS"))
    demos = []
    for i in range(len(arc)):
        data = arc.read(i)
        first = struct.unpack_from("<I", data, 0)[0]
        base = first & 0xFFFF0000
        offset = first - base
        if not first or offset + 0x30 > len(data) or base != 0x8CFE0000:
            continue
        demo = read_stream(data, offset)
        demo["member"] = i
        demo["frames"] = sum(1 + r[0] for r in demo["records"])
        demos.append(demo)
    with open(os.path.join(out, "demos.json"), "w") as f:
        json.dump({"demos": demos}, f)
    print("%d demos, frames %s" % (len(demos), [d["frames"] for d in demos]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
