"""Export the picture-strip scenes of the story (DEMO30 .. DEMO35): the opening of the game and the chapter starts.

    python tools/comic.py [--game DIR] [--out DIR] [--demo 30]

A scene of this kind is a stack of "pages" lying flat on a grey table, each page a textured quad pair, one camera path
for each page (the same record as in the menu scenes, tag 0x01C1) and a list of subtitles. Member 0 of
DEMOnn.AFS is the data block at 0x8C800000, member 1 holds one picture per page. The block starts with

    u32 end of the subtitle list, u32 pointer to the three page pointers, u32 table of texture lists

and the subtitles are 28-byte records

    u32 0, u32 4 (a text line), u32 page, u32 first frame, u32 text pointer, u32 length in frames, u32 language

with languages 0 Japanese (Shift JIS), 1 English, 2 German, 3 French, 4 Spanish; `$n` breaks a line. The records
that follow (type 13, 16) end the page.

Writes <out>/models/comic_<n>.glb (one node per page) and merges <out>/comic.json.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import extract
import glb
import motion
import ninja

BASE = 0x8C800000
LANGUAGES = ["jp", "en", "de", "fr", "es"]
FPS = 30.0
TURN = 2.0 * 3.141592653589793 / 65536.0


def export(game, out_dir, number):
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    name = "DEMO%02d.AFS" % number
    data = afs.Archive(os.path.join(root, name)).read(0)
    blob = ninja.Blob(data, BASE)
    objs = ninja.find_objects(blob)
    roots = ninja.find_roots(objs)
    pictures = extract.Pictures(root)

    # the cameras in file order are the pages in order
    cameras = []
    for off in range(0, len(data) - 12, 4):
        _, frames, kind, _ = struct.unpack_from(">IIHH", data, off)
        if kind == 0x01C1:
            c = motion.read_camera(blob, BASE + off)
            if c:
                cameras.append((off, c))
    # trees that carry a picture, in file order; a scene with one camera is one page made of all of them
    trees = []
    for r in sorted(roots):
        nodes, prims = ninja.read_tree(blob, objs, r)
        if any(p.indices and getattr(p, "texture", -1) >= 0 for p in prims):
            trees.append((r, nodes, prims))
    if len(cameras) == 1:
        page_trees = [trees]
    else:
        if len(trees) > len(cameras):
            trees = trees[-len(cameras):]
        page_trees = [[t] for t in trees]
    # a table with a backdrop of the same colour as the pages: untextured pieces are drawn dark
    builder = glb.Builder()
    pages = []
    for n, (group, (_, cam)) in enumerate(zip(page_trees, cameras)):
        groups = []
        for r, nodes, prims in group:
            worlds = ninja.world_matrices(nodes)
            for p in prims:
                if not p.indices or p.volume:
                    continue
                g = {"positions": [], "uvs": [], "colors": [], "indices": []}
                for pos, uv, col, owner in zip(p.positions, p.uvs, p.colors, p.owners):
                    g["positions"].append(ninja.transform_point(worlds[owner], pos))
                    g["uvs"].append(uv)
                    g["colors"].append(extract._color(col, p.diffuse, True, p.alpha))
                g["indices"] = list(p.indices)
                textured = getattr(p, "texture", -1) >= 0
                if textured:
                    index = n + p.texture if len(cameras) > 1 else p.texture
                    try:
                        png, alpha = pictures.get(name, 1, index)
                    except IndexError:
                        png, alpha = pictures.get(name, 1, 0)
                    image = builder.image((name, index), png)
                    g["material"] = builder.material(image, (1.0, 1.0, 1.0, 1.0), True, False)
                else:
                    g["colors"] = [(255, 255, 255, 255)] * len(g["positions"])
                    g["material"] = builder.material(None, (0.035, 0.035, 0.035, 1.0), True, False)
                groups.append(g)
        mesh = builder.mesh("page%d" % n, groups)
        builder.add_node("page%d" % n, mesh=mesh)
        pages.append({
            "node": "page%d" % n,
            "frames": cam.frames,
            "position": [[f] + list(v) for f, v in cam.position],
            "target": [[f] + list(v) for f, v in cam.target],
            "roll": [[f, a * TURN] for f, a in cam.roll],
            "fov": [[f, a * TURN] for f, a in cam.fov],
        })
    path = os.path.join(out_dir, "models", "comic_%d.glb" % number)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    builder.save(path)

    # subtitles
    lines = []
    end = struct.unpack_from(">I", data, 0)[0] - BASE
    table = struct.unpack_from(">I", data, 4)[0] - BASE
    o = table
    while o + 28 <= len(data):
        z, k, pg, st, tx, ln, lg = struct.unpack_from(">7I", data, o)
        if z == 0 and k == 4 and pg < 4 and st < 6000 and BASE <= tx < BASE + len(data) and ln < 2000 and lg < 6:
            break
        o += 4
    while o + 28 <= len(data):
        zero, kind, page, start, text, length, lang = struct.unpack_from(">7I", data, o)
        o += 28
        if kind != 4:
            break
        t = text - BASE
        if not (0 <= t < len(data)):
            continue
        raw = data[t:data.index(b"\0", t)]
        s = raw.decode("shift_jis" if lang == 0 else "latin-1", errors="replace").replace("$n", "\n").strip()
        lines.append({"page": page, "lang": LANGUAGES[lang] if lang < len(LANGUAGES) else str(lang),
                      "start": start, "frames": length, "text": s})
    return {"pages": pages, "subtitles": lines}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    numbers = [int(argv[argv.index("--demo") + 1])] if "--demo" in argv else [30]
    path = os.path.join(out, "comic.json")
    result = json.load(open(path)) if os.path.exists(path) else {}
    for n in numbers:
        info = export(game, out, n)
        result[str(n)] = info
        print("DEMO%02d: %d pages, %d subtitle lines" % (n, len(info["pages"]), len(info["subtitles"])))
    with open(path, "w") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
