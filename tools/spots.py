"""Find the graffiti spots of the stages.

    python tools/spots.py [--game build/xbla]

A spot is a record in the stage archive (no table points at it; it is found by its shape):

    +0x000  u32   size class: 2 (a square spot, three points) or 3 (a wide spot, seven points)
    +0x004  f32 x3  position
    +0x01C  f32 x3  scale (1, 1, 1)
    +0x034  f32 x3  the front vector: out of the wall, the way the skater does not face
    +0x058  f32 x3 x8  eight points of the spot's volume (the skater tags from inside it)
    +0x0E8  u32   bit mask of the pictures that may be drawn here
    +0x0EC  ptr   array of 0x20 byte records, `count` at +0x0F0: where the skater stands, one record after the other, while
                  the picture is sprayed (the first three floats are the position)
    +0x0F4  ptr   array of 0xB0 byte records, `count` at +0x0F8 (the strokes)
    +0x0FC  ptr   object tree: the frame of the spot and, as its second piece, the quad the picture is drawn on

The game's code is `FUN_004a75a0` (copies the record into a task) and the player's tagging state (`FUN_004e4440`), which
moves the skater to the points one after the other.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import layout
import ninja

BASE = 0x8CB00000


def find(game, stage):
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    name, member = layout.STAGE_ARCHIVES[stage]
    d = afs.Archive(os.path.join(root, name)).read(member)
    blob = ninja.Blob(d, BASE)
    objs = ninja.find_objects(blob)
    n = len(d)

    def ok(p):
        return BASE <= p < BASE + n

    def f(o):
        return struct.unpack_from(">f", d, o)[0]

    out = []
    for off in range(0, n - 0x110, 4):
        level = struct.unpack_from(">I", d, off)[0]
        if level not in (2, 3):
            continue
        a, c1, b, c2, tree = struct.unpack_from(">5I", d, off + 0xEC)
        if not (ok(a) and 0 < c1 < 100 and ok(b) and 0 < c2 < 100 and tree in objs):
            continue
        if not all(abs(f(off + 0x1C + 4 * k) - 1.0) < 1e-4 for k in range(3)):
            continue
        pos = [f(off + 4 + 4 * k) for k in range(3)]
        if max(abs(v) for v in pos) > 1e5:
            continue
        mask = struct.unpack_from(">I", d, off + 0xE8)[0]
        points = [[f(a - BASE + 0x20 * i + 4 * k) for k in range(3)] for i in range(c1)]
        volume = [[f(off + 0x58 + 12 * k + 4 * j) for j in range(3)] for k in range(8)]
        front = [f(off + 0x34 + 4 * j) for j in range(3)]
        spot = {"level": level, "pos": pos, "mask": mask, "points": points, "quad": [], "frame": [], "volume": volume,
                "front": front}
        nodes, prims = ninja.read_tree(blob, objs, tree)
        worlds = ninja.world_matrices(nodes)
        for p in prims:
            if not p.indices:
                continue
            world = [ninja.transform_point(worlds[o], v) for v, o in zip(p.positions, p.owners)]
            if p.texture == 1 and len(p.indices) == 6:
                # the quad: four corners in the order of the strip, with the texture coordinates of the picture
                spot["quad"] = [[round(c, 2) for c in v] + [round(uv[0], 4), round(uv[1], 4)] for v, uv in zip(world, p.uvs)]
                spot["quad_indices"] = list(p.indices)
            elif p.texture == 0:
                xs = [v[0] for v in world]
                ys = [v[1] for v in world]
                zs = [v[2] for v in world]
                spot["frame"] = [min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)]
        out.append(spot)
    return out


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    for stage in sorted(layout.STAGE_ARCHIVES):
        found = find(game, stage)
        print("stage %s: %d spots (%d wide, %d square)" % (stage, len(found), sum(1 for s in found if s["level"] == 3),
                                                       sum(1 for s in found if s["level"] == 2)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
