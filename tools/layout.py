"""Where the objects of a stage are placed.

    python tools/layout.py [--exe build/exe] [--game build/xbla] [--stage 1]

A stage archive holds object trees modelled around their own origin. The game draws each tree with a placement taken
from lists of entries

    word 0      object id (-1 = unused, below -1 = end of a run)
    words 1..3  position (floats)
    words 4..6  rotation (integers, 65536 per turn)
    ...         10 or 13 words in all

An id selects an object pointer in an object table and a texture list header in a parallel list table (both in the
executable's data). The entry lists are found through a table indexed by block number; the blocks are the sectors of
the stage and are drawn when the player is near them. A family is one such set of a block table, an object table and
a list table. Two kinds of block table exist:

    ptr   each block holds a pointer to a null-terminated array of entry pointers
    run   each block holds a pointer to entries laid out one after another

The addresses below are those of the retail executable. The rotation order is the one of the game's own matrix
routine: the point is turned about X, then Y, then Z.
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = 0x82000000
BLOB_BASE = 0x8CB00000
MAX_BLOCKS = 72
MAX_ENTRIES = 4000

# (block table, object table, list table or None, kind, entry words, number of blocks[, number of types])
FAMILIES = {
    "1": [
        (0x82D7D080, 0x82D7D750, 0x82D7DA08, "ptr", 10, 63),
        (0x82D7D2A0, 0x82D7E1F0, 0x82D7E2B8, "ptr", 10, 63),
        (0x82D7D3C0, 0x82D7E510, 0x82D7E5E8, "run", 10, 63),
        (0x82D7D600, 0x82D7EB18, None, "run", 10, 63),
        (0x82D7D038, 0x82D7D750, 0x82D7DA08, "ptr", 10, 1),
        (0x82D7D03C, 0x82D7D07C, 0x82D7D17C, "ptr", 10, 1),
        # props the game creates as tasks when a block is entered (cones, bikes, signs ...)
        (0x82D7D4E0, 0x82D7E948, 0x82D7E9B8, "ptr", 10, 63, 28),
    ],
    "2": [
        (0x82D7F040, 0x82D7FA00, 0x82D7FBD0, "run", 13, 1),
        (0x82D7F0A8, 0x82D7FA00, 0x82D7FBD0, "run", 13, MAX_BLOCKS),
        (0x82D7F270, 0x82D80098, 0x82D805B8, "run", 10, MAX_BLOCKS),
        (0x82D7F438, 0x82D80AD8, 0x82D80C10, "run", 13, MAX_BLOCKS),
        (0x82D7F7C8, 0x82D81828, None, "run", 10, MAX_BLOCKS),
        (0x82D7F600, 0x82D810F0, 0x82D81260, "run", 10, MAX_BLOCKS, 92),
    ],
    "3": [
        (0x82CCDD08, 0x82CCE158, 0x82CCE340, "run", 10, MAX_BLOCKS),
        (0x82CCDDC0, 0x82CCE8E0, 0x82CCEA40, "run", 10, MAX_BLOCKS),
        (0x82CCDE78, 0x82CCEBA0, 0x82CCEF60, "run", 13, MAX_BLOCKS),
        (0x82CCDFE8, 0x82CCFF18, 0x82CCFF98, "run", 13, MAX_BLOCKS),
        (0x82CCDF30, 0x82CCFAA0, 0x82CCFBB8, "ptr", 13, MAX_BLOCKS, 70),
    ],
    "5": [
        (0x82C9D4D8, 0x82C9DA78, 0x82C9DB60, "run", 10, MAX_BLOCKS),
        (0x82C9D5F8, 0x82C9DE18, 0x82C9DF68, "run", 10, MAX_BLOCKS),
        (0x82C9D718, 0x82C9E358, 0x82C9E3E8, "run", 13, MAX_BLOCKS),
        (0x82C9D838, 0x82C9E898, None, "run", 10, MAX_BLOCKS),
        (0x82C9D958, 0x82C9E6B8, 0x82C9E708, "run", 13, MAX_BLOCKS, 20),
    ],
    "6": [
        (0x82C92B70, 0x82C93238, 0x82C93320, "run", 10, MAX_BLOCKS),
        (0x82C92CD8, 0x82C935D4, 0x82C935DC, "run", 10, MAX_BLOCKS),
        (0x82C92E40, 0x82C92B4C, 0x82C92CB4, "run", 13, MAX_BLOCKS),
        (0x82C930F0, 0x82C935F8, 0x82C93688, "run", 13, MAX_BLOCKS, 36),
    ],
}


# stage -> (archive, member) of the geometry
STAGE_ARCHIVES = {"1": ("STAGE1.AFS", 0), "2": ("STAGE2.AFS", 0), "3": ("STAGE3.AFS", 0),
                  "5": ("STAGE5.AFS", 0), "6": ("STAGE6.AFS", 0)}


class Placement:
    __slots__ = ("family", "block", "id", "pos", "rot", "root", "list")

    def __init__(self, family, block, ident, pos, rot, root, header):
        self.family = family
        self.block = block
        self.id = ident
        self.pos = pos
        self.rot = rot
        self.root = root
        self.list = header


def matrix(pos, rot):
    """Placement as a 4x4 matrix: translate, then turn about Z, Y and X (X is applied to the point first)."""
    ax, ay, az = [a * (2.0 * math.pi / 65536.0) for a in rot]
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    # Rz * Ry * Rx
    r = [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]
    return [r[0] + [pos[0]], r[1] + [pos[1]], r[2] + [pos[2]], [0.0, 0.0, 0.0, 1.0]]


def read(stage, image, blob, base=BLOB_BASE, families=None):
    """All placements of a stage: image is the executable image, blob the stage archive member."""
    families = FAMILIES.get(stage, []) if families is None else families
    size = len(blob)

    def u32(va):
        return struct.unpack_from(">I", image, va - BASE)[0]

    def dc(p):
        return 0x8C000000 | (p & 0x01FFFFFF) if 0x20000000 <= p < 0x22000000 else p

    def in_blob(p, need=4):
        p = dc(p)
        return base <= p and p + need <= base + size

    def entry(a):
        o = a - base
        ident, = struct.unpack_from(">i", blob, o)
        pos = struct.unpack_from(">3f", blob, o + 4)
        rot = struct.unpack_from(">3i", blob, o + 16)
        return ident, pos, rot

    out = []
    seen = set()
    for number, family in enumerate(families):
        table, objects, lists, kind, words, blocks = family[:6]
        types = family[6] if len(family) > 6 else 1000
        for block in range(min(blocks, MAX_BLOCKS)):
            w = u32(table + 4 * block)
            if w == 0:
                continue
            if not in_blob(w, 4 * words):
                break
            addresses = []
            a = dc(w)
            if kind == "ptr":
                while len(addresses) < MAX_ENTRIES and in_blob(a):
                    e, = struct.unpack_from(">I", blob, a - base)
                    if e == 0 or not in_blob(e, 4 * 7):
                        break
                    addresses.append(dc(e))
                    a += 4
            else:
                while len(addresses) < MAX_ENTRIES and in_blob(a, 4 * words):
                    ident, = struct.unpack_from(">i", blob, a - base)
                    if ident < -1:
                        break
                    addresses.append(a)
                    a += 4 * words
            for a in addresses:
                ident, pos, rot = entry(a)
                if ident < 0 or ident >= types:
                    continue
                if not all(math.isfinite(v) and abs(v) < 1e5 for v in pos):
                    continue
                root = u32(objects + 4 * ident)
                if root == 0:
                    continue
                root = dc(root)
                if not in_blob(root, 0x34):
                    continue
                header = u32(lists + 4 * ident) if lists else 0
                key = (root, pos, rot)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Placement(number, block, ident, pos, rot, root, header))
    return out


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    import afs
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    wanted = argv[argv.index("--stage") + 1] if "--stage" in argv else None
    image = open(os.path.join(exe, "image.bin"), "rb").read()
    for stage, (name, member) in STAGE_ARCHIVES.items():
        if wanted and stage != wanted:
            continue
        data = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", name)).read(member)
        found = read(stage, image, data)
        roots = {p.root for p in found}
        xs = [p.pos[0] for p in found]
        zs = [p.pos[2] for p in found]
        print("stage %s: %d placements of %d objects, x %.0f..%.0f z %.0f..%.0f" %
              (stage, len(found), len(roots), min(xs, default=0), max(xs, default=0),
               min(zs, default=0), max(zs, default=0)))
        per = {}
        for p in found:
            per[p.family] = per.get(p.family, 0) + 1
        print("    per family:", dict(sorted(per.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
