"""Export the characters of PLAYER.AFS as glTF files with their motions.

    python tools/skaters.py [--game DIR] [--exe DIR] [--out DIR] [--only ID]

Each character becomes assets/models/skaters/<name>.glb: the first object tree as a node hierarchy (one mesh per
object) and one animation per motion, named m000, m001 ... A listing is written to assets/skaters.json.
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import glb
import ninja
import play
import pvr
import rig

FPS = 30.0
TURN = 2.0 * math.pi / 65536.0

# Character ids, as the garage and the game number them. The names are the English roster of the executable
# (a table of 15 string pointers at 0x82D846D8; the last five are "???"); the last six ids are the rivals.
SKATERS = ["beat", "gum", "tab", "combo", "slate", "piranha", "cube", "mew", "yoyo", "garam",
           "rival10", "love_shockers", "noise_tank", "goji", "pots", "poison_jam"]
LABELS = ["BEAT", "GUM", "TAB", "COMBO", "SLATE", "PIRANHA", "CUBE", "MEW", "YO-YO", "GARAM",
          "RIVAL", "LOVE SHOCKERS", "NOISE TANK", "GOJI", "POTS", "POISON JAM"]
PLAYER_PARTITION = "4"


def members(exe_dir):
    """PLAY container member of each character id.

    The executable loads a character with a list of two records, the textures (`PTEX`, type 7) and the models
    (`PLAY`, type 6), both at 0x20800000 and 0x20801000. The lists of the 16 characters come one after the
    other, in character id order.
    """
    found = []
    with open(os.path.join(exe_dir, "load_lists.tsv"), newline="") as f:
        rows = csv.DictReader(f, delimiter="\t")
        for row in rows:
            if row["partition"] == PLAYER_PARTITION and row["type"] == "6" and row["destination"] == "20801000":
                found.append(int(row["member"]))
            if len(found) == 16:
                break
    return found


def export(arc, member, name, out_dir):
    c = play.Character(arc.read(member), arc.read(member + 1))
    nodes = ninja.tree_nodes(c.objects, c.trees[0])
    motions = c.motions(len(nodes))
    slots = c.slots(0)
    builder = glb.Builder()
    pngs = {}

    def texture_for(texture):
        idx = slots.get(texture)
        if idx is None:
            return None
        if idx not in pngs:
            _, w, h, rgba = c.image(idx)
            pngs[idx] = (idx, pvr.png_bytes(w, h, rgba), any(rgba[i] != 255 for i in range(3, len(rgba), 4)))
        return pngs[idx]

    order = rig.add_skinned_tree(builder, c.blob, c.objects, c.trees[0], texture_for, name)
    index = {o.addr: node for o, node in order}
    # a channel a motion leaves out keeps the object's own value; every animation says so, because the player
    # keeps whatever the previous one set on a joint it does not key
    rest = []
    for o, _ in nodes:
        angles = [0.0] * 3 if o.flags & 0x02 else [a * TURN for a in o.rot]
        rest.append(((0.0, 0.0, 0.0) if o.flags & 0x01 else tuple(o.pos),
                     ninja.quaternion(ninja.rotation_matrix(angles, o.flags)),
                     (1.0, 1.0, 1.0) if o.flags & 0x04 else tuple(o.scale)))
    for k, m in enumerate(motions):
        channels = []
        for n, (o, _) in enumerate(nodes):
            entry = m.entries[n]
            node = index[o.addr]
            if "pos" not in entry:
                channels.append((node, "translation", [rest[n][0]]))
            if "ang" not in entry:
                channels.append((node, "rotation", [rest[n][1]]))
            if "scl" not in entry:
                channels.append((node, "scale", [rest[n][2]]))
            if "pos" in entry:
                channels.append((node, "translation", [tuple(v) for v in entry["pos"]]))
            if "ang" in entry:
                quats = []
                last = None
                for a in entry["ang"]:
                    q = ninja.quaternion(ninja.rotation_matrix([v * TURN for v in a], o.flags))
                    if last is not None and sum(x * y for x, y in zip(q, last)) < 0:
                        q = tuple(-x for x in q)
                    quats.append(q)
                    last = q
                channels.append((node, "rotation", quats))
            if "scl" in entry:
                channels.append((node, "scale", [tuple(v) for v in entry["scl"]]))
        if channels:
            builder.add_animation("m%03d" % k, channels, FPS)
    path = os.path.join(out_dir, "models", "skaters", "%s.glb" % name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    builder.save(path)
    return path, len(nodes), len(motions), [m.frames for m in motions]


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    only = int(argv[argv.index("--only") + 1]) if "--only" in argv else None
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "PLAYER.AFS"))
    listing = []
    for n, member in enumerate(members(exe)):
        if only is not None and n != only:
            continue
        name = SKATERS[n]
        path, objects, count, frames = export(arc, member, name, out_dir)
        print("%-10s member %2d: %d objects, %d motions -> %s" % (name, member, objects, count, path))
        listing.append({"id": n, "name": name, "label": LABELS[n], "file": "models/skaters/%s.glb" % name,
                        "motions": frames})
    if only is None:
        with open(os.path.join(out_dir, "skaters.json"), "w") as f:
            json.dump({"skaters": listing}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
