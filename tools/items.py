"""Export the spray cans.

    python tools/items.py [--game DIR] [--out DIR]

Writes assets/models/items.glb: one node per kind of can (`can0`, the small yellow one, and `can1`, the larger
teal one) and an animation for each (`spin0`, `spin1`).

The cans are objects of the `main` block of PLAYER.AFS (member 16, loaded at 0x8C8E1000), drawn with the first
picture of the XTFE block that follows it (member 17). The game's pickup code picks them by address:

    kind 0   object 0x8C8E1AEC, motion 0x8C8EADD0
    others   object 0x8C8E283C, motion 0x8C8EAE98

A motion is 29 frames of a turn about the vertical axis; the second one starts a little further round.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import extract
import glb
import motion
import ninja

BASE = 0x8C8E1000
TURN = 2.0 * math.pi / 65536.0
FPS = 30.0
CANS = [("can0", 0x8C8E1AEC, 0x8C8EADD0), ("can1", 0x8C8E283C, 0x8C8EAE98),
        ("item_b0", 0x8C8E251C, 0x8C8ED6E8), ("item_b1", 0x8C8E200C, 0x8C8ED620), ("item_c", 0x8C8E71FC, 0x8C8ED7B0)]


def export(game, out_dir):
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "PLAYER.AFS"))
    blob = ninja.Blob(arc.read(16), BASE)
    objs = ninja.find_objects(blob)
    pictures = extract.Pictures(os.path.join(game, "DATA_BE", "JETRADIO"))
    png, alpha = pictures.get("PLAYER.AFS", 17, 0)
    builder = glb.Builder()
    image = builder.image(("PLAYER.AFS", 17, 0), png)
    material = builder.material(image, (1.0, 1.0, 1.0, 1.0), True, alpha)
    counts = []
    for n, (name, address, spin) in enumerate(CANS):
        nodes, prims = ninja.read_tree(blob, objs, address)
        g = {"positions": [], "uvs": [], "colors": [], "indices": []}
        worlds = ninja.world_matrices(nodes)
        for p in prims:
            if not p.indices or p.volume:
                continue
            start = len(g["positions"])
            for pos, uv, col, owner in zip(p.positions, p.uvs, p.colors, p.owners):
                g["positions"].append(ninja.transform_point(worlds[owner], pos))
                g["uvs"].append(uv)
                g["colors"].append(extract._color(col, p.diffuse, True, p.alpha))
            g["indices"] += [start + i for i in p.indices]
        g["material"] = material
        mesh = builder.mesh(name, [g])
        node = builder.add_node(name, mesh=mesh)
        m = motion.read(blob, spin, 1)
        angles = m.entries[0]["ang"]
        quats = []
        last = None
        for a in angles:
            q = ninja.quaternion(ninja.rotation_matrix([v * TURN for v in a], nodes[0][0].flags))
            if last is not None and sum(x * y for x, y in zip(q, last)) < 0:
                q = tuple(-x for x in q)
            quats.append(q)
            last = q
        # the game starts again at the first frame after the last, so the loop is as long as the motion
        quats.append(quats[0] if sum(x * y for x, y in zip(quats[0], quats[-1])) >= 0 else tuple(-x for x in quats[0]))
        builder.add_animation("spin%d" % n, [(node, "rotation", quats)], FPS)
        counts.append((name, len(g["indices"]) // 3, m.frames))
    path = os.path.join(out_dir, "models", "items.glb")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    builder.save(path)
    return path, counts


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    path, counts = export(game, out_dir)
    for name, tris, frames in counts:
        print("%s: %d triangles, %d frames" % (name, tris, frames))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
