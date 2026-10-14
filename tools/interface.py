"""Export the menu screens: title, garage, loading and the in-game display.

    python tools/interface.py [--game DIR] [--exe DIR] [--out DIR]

Writes, under the assets folder:

    models/title.glb, models/loading.glb, models/garage.glb    the 3D parts, as node hierarchies with animations
    ui/<screen>_<n>.png                                         texture sheets of the 2D parts
    screens.json                                                what goes where (see below)

Where each piece is used comes from the code that draws the screen, which is described in docs/screens.md. The
addresses of the tables that code reads are collected as constants here.
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract
import glb
import ninja
import scene
import texbind

# --- garage (see docs/screens.md) ----------------------------------------------------------------------------
GARAGE_BASE = 0x8C800000
GARAGE_HOST = 0x20800000
GARAGE_ROOM_LIST = 0x82D62650        # patch array: texture list of the room
GARAGE_OBJECTS = 0x82D7CDFC          # per character: slot of its tree
GARAGE_PLACEMENTS = 0x82D7CDC0       # slot of its object record (where it stands)
GARAGE_LISTS = 0x82D7CD48            # patch array: texture list of the character
GARAGE_IDLE_A = 0x82D7CEB0           # slots of the two idle motions
GARAGE_IDLE_B = 0x82D7CEEC
GARAGE_CAMERA_POSITION = 0x82CEB368  # per selection slot: slot of an object record (camera position)
GARAGE_CAMERA_TARGET = 0x82CEB3A4
GARAGE_ORDER = 0x82CEB3E0            # per character: its selection slot
GARAGE_PLATES = 0x82CEB2F0           # per character: slot of its name plate sprite
GARAGE_TAGS = 0x82CEB32C             # per character: slot of its small name tag sprite
GARAGE_SHEET_LIST = 0x82D62890       # patch array: the six garage sheets
CHARACTERS = 15

# --- title ---------------------------------------------------------------------------------------------------
TITLE_BASE = 0x8CF00000
TITLE_TREES = (0x04, 0x08, 0x0C, 0x10)
TITLE_MOTIONS = (0x14, 0x18, 0x1C, 0x20)
TITLE_CAMERA_PATH = 0x00
TITLE_CAMERA_SETUP = 0x24
TITLE_TREE_LIST = 0x82D8FF6C          # patch array used for the trees
TITLE_SHEET_LIST = 0x82D8FF4C         # record used for the sprites

# --- loading -------------------------------------------------------------------------------------------------
LOADING_BASE = 0x8CF70000
LOADING_FOV = 0x3C71
LOADING_DISTANCE = 80.0


def sheet_files(sc, header, name, out_dir):
    """Write the textures a list header is bound to; returns {slot: path relative to the assets folder}."""
    slots = sc.bindings.choose(header, "")
    files = {}
    os.makedirs(os.path.join(out_dir, "ui"), exist_ok=True)
    for slot, bound in sorted(slots.items()):
        png, _ = sc.png(bound[:3])
        rel = "ui/%s_%d.png" % (name, slot)
        with open(os.path.join(out_dir, rel), "wb") as f:
            f.write(png)
        files[slot] = rel
    return files


def sprite_json(s, sheets):
    sheet = sheets.get(s["texture"])
    return {"sheet": sheet, "x": s["x"], "y": s["y"], "w": s["w"], "h": s["h"], "pivot": s["pivot"],
            "uv": s["uv"], "colors": s["colors"], "attributes": s["attributes"], "header": s["header"]}


def export_garage(game, bindings, pictures, out_dir):
    sc = scene.Scene(game, bindings, pictures, "E_GARAGE.AFS", 1, GARAGE_BASE, scene.LANGUAGE)

    def slot_value(address):
        if not GARAGE_HOST <= address < GARAGE_HOST + 0x1000:
            return 0
        return sc.blob.u32(GARAGE_BASE + (address - GARAGE_HOST))

    def table(va, n=CHARACTERS):
        return [slot_value(sc.exe(va + 4 * i)) for i in range(n)]

    def record(p):
        if not p or not sc.blob.has(p, 4):
            return None
        pos = sc.blob.f32s(p + 8, 3)
        rot = struct.unpack_from(">3i", sc.data, p + 0x14 - GARAGE_BASE)
        return list(pos), [a * scene.TURN for a in rot]

    slots_of = lambda patch: bindings.choose(sc.exe(patch), "GARAGE")
    builder = glb.Builder()
    info = {"characters": [], "cameras": [], "plates": [], "tags": []}

    sc.add_tree(builder, sc.head(0), slots_of(GARAGE_ROOM_LIST), "room")

    objects, places = table(GARAGE_OBJECTS), table(GARAGE_PLACEMENTS)
    for i in range(CHARACTERS):
        spot = record(places[i])
        if not objects[i] or objects[i] not in sc.objs or spot is None:
            continue
        pos, ang = spot
        rest = ninja.quaternion(ninja.rotation_matrix(ang, 0))
        order = sc.add_tree(builder, objects[i], slots_of(sc.exe(GARAGE_LISTS + 4 * i)), "char%02d" % i, pos, rest)
        idles = []
        for label, va in (("a", GARAGE_IDLE_A), ("b", GARAGE_IDLE_B)):
            m = sc.motion_at(slot_value(sc.exe(va + 4 * i)), len(order))
            if m:
                name = "char%02d_%s" % (i, label)
                sc.animate(builder, name, order, m)
                idles.append({"name": name, "frames": m.frames})
        info["characters"].append({"id": i, "node": "char%02d" % i, "position": pos, "angles": ang,
                                   "slot": sc.exe(GARAGE_ORDER + 4 * i), "idle": idles})
    for i in range(CHARACTERS):
        a = record(table(GARAGE_CAMERA_POSITION)[i])
        b = record(table(GARAGE_CAMERA_TARGET)[i])
        info["cameras"].append({"position": a[0] if a else None, "target": b[0] if b else None})

    sheets = sheet_files(sc, sc.exe(GARAGE_SHEET_LIST), "garage", out_dir)
    for key, va in (("plates", GARAGE_PLATES), ("tags", GARAGE_TAGS)):
        for i in range(CHARACTERS):
            s = sc.sprite(slot_value(sc.exe(va + 4 * i)))
            info[key].append(sprite_json(s, sheets) if s else None)
    info["sprites"] = [sprite_json(s, sheets) for s in sc.sprites()]
    info["sheets"] = sheets

    paths = []
    for off in range(0x10, 0x4C0, 4):
        c = sc.camera_at(sc.head(off))
        if c and len(c["position"]) == c["frames"]:
            c["slot"] = off
            paths.append(c)
    info["paths"] = paths
    path = os.path.join(out_dir, "models", "garage.glb")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    builder.save(path)
    return info


def export_title(game, bindings, pictures, out_dir):
    sc = scene.Scene(game, bindings, pictures, "E_TITLE.AFS", 0, TITLE_BASE, scene.LANGUAGE)
    builder = glb.Builder()
    header = sc.exe(TITLE_TREE_LIST)
    slots = {}
    for pack in ("TITLE", "SEGALOGO"):
        slots.update(bindings.choose(header, pack))
    info = {"trees": []}
    for n, (t, m) in enumerate(zip(TITLE_TREES, TITLE_MOTIONS)):
        root = sc.head(t)
        order = sc.add_tree(builder, root, slots, "t%d" % n)
        mot = sc.motion_at(sc.head(m), len(order))
        frames = 0
        if mot:
            sc.animate(builder, "t%d" % n, order, mot)
            frames = mot.frames
        info["trees"].append({"node": "t%d" % n, "animation": "t%d" % n if mot else None, "frames": frames})
    info["camera"] = sc.camera_at(sc.head(TITLE_CAMERA_PATH))
    setup = sc.head(TITLE_CAMERA_SETUP)
    info["setup"] = {"position": list(sc.blob.f32s(setup, 3)), "angle": sc.blob.u32(setup + 0x1C) * scene.TURN,
                     "near": sc.blob.f32(setup + 0x20), "far": sc.blob.f32(setup + 0x24)}
    sheets = sheet_files(sc, sc.exe(TITLE_SHEET_LIST), "title", out_dir)
    info["sprites"] = [sprite_json(s, sheets) for s in sc.sprites()]
    info["sheets"] = sheets
    builder.save(os.path.join(out_dir, "models", "title.glb"))
    return info


def export_loading(game, bindings, pictures, out_dir):
    sc = scene.Scene(game, bindings, pictures, "E_LOAD.AFS", 0, LOADING_BASE, scene.LANGUAGE)
    builder = glb.Builder()
    info = {"trees": [], "fov": LOADING_FOV * scene.TURN, "distance": LOADING_DISTANCE}
    for n, (t, m) in enumerate(((0x00, 0x04), (0x08, 0x0C))):
        order = sc.add_tree(builder, sc.head(t), {}, "l%d" % n)
        mot = sc.motion_at(sc.head(m), len(order))
        if mot:
            sc.animate(builder, "l%d" % n, order, mot)
        info["trees"].append({"node": "l%d" % n, "animation": "l%d" % n if mot else None,
                              "frames": mot.frames if mot else 0})
    builder.save(os.path.join(out_dir, "models", "loading.glb"))
    return info


def export_hud(game, bindings, pictures, out_dir):
    sc = scene.Scene(game, bindings, pictures, "E_GAME.AFS", 0, 0x8C980000, scene.LANGUAGE)
    header = [h for h, s in bindings.slots.items() if any(c[0] == "GAME.AFS" for cs in s.values() for c in cs)]
    sheets = sheet_files(sc, header[0], "game", out_dir) if header else {}
    return {"sprites": [sprite_json(s, sheets) for s in sc.sprites()], "sheets": sheets}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    bindings = texbind.Bindings(exe, game)
    pictures = extract.Pictures(os.path.join(game, "DATA_BE", "JETRADIO"))
    os.makedirs(os.path.join(out_dir, "models"), exist_ok=True)
    screens = {}
    for name, fn in (("garage", export_garage), ("title", export_title), ("loading", export_loading),
                     ("hud", export_hud)):
        screens[name] = fn(game, bindings, pictures, out_dir)
        print("%s: done" % name)
    with open(os.path.join(out_dir, "screens.json"), "w") as f:
        json.dump(screens, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
