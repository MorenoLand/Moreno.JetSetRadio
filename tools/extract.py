"""Convert game data from the unpacked package into files the engine project loads.

    python tools/extract.py [--stage NAME ...] [--game DIR] [--exe DIR] [--out DIR] [--flip-z]

--game   the unpacked package (default build/xbla)
--exe    the folder written by xex.py and manifest.py (default build/exe)
--out    the assets folder (default assets)
--stage  stage geometry to export as assets/models/stage<NAME>.glb: 1 2 3 5 6 last (default: 1 2 3 5 6)
--flip-z mirror the geometry on the Z axis
"""
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import glb
import layout
import mission
import ninja
import pvr
import spots
import traffic
import texbind

# stem, label, exported by default (the last stage is a boss arena that the placement tables do not cover)
STAGES = [("1", "Stage 1", True), ("2", "Stage 2", True), ("3", "Stage 3", True), ("5", "Stage 5", True),
          ("6", "Stage 6", True), ("last", "Last stage", False)]
STAGE_BASE = 0x8CB00000
BACKDROP_EXTENT = 3000.0   # trees larger than this are exported as a separate node

# Texture lists of the sky trees. Each stage's set-up routine calls one function (FUN_82403DD8 of the retail image)
# with up to three sky objects and, for each, the list that textures it; the tables the lists of other objects
# come from do not cover them (the guess for the dome of stage 1 was a car). Stage 5 and the shell of stage 1 are
# filled in at run time or untextured, and keep what the tables give.
SKY_LISTS = {
    "1": {0x8CCE2EBC: 0x82CB6328},
    "2": {0x8CC93634: 0x82CC6108, 0x8CC93454: 0x82CC6100},
    "3": {0x8CCC5AF4: 0x82CD6D90, 0x8CCC7B98: 0x82CD6D90},
    "6": {0x8CC3D9B8: 0x82C9C698},
}


class Pictures:
    """Decoded texture images of the packs, as PNG bytes, loaded as they are asked for."""

    def __init__(self, root):
        self.root = root
        self._members = {}
        self._pictures = {}

    def get(self, pack, member, index):
        key = (pack, member, index)
        if key not in self._pictures:
            if (pack, member) not in self._members:
                data = afs.Archive(os.path.join(self.root, pack)).read(member)
                self._members[(pack, member)] = (data, list(pvr.locate(data)))
            data, found = self._members[(pack, member)]
            _, gbix, pvrt, end = found[index]
            pixel, fmt = data[pvrt + 8], data[pvrt + 9]
            w = int.from_bytes(data[pvrt + 12:pvrt + 14], "little")
            h = int.from_bytes(data[pvrt + 14:pvrt + 16], "little")
            rgba = pvr.decode(pixel, fmt, w, h, data[pvrt + 16:end])
            alpha = any(rgba[i] != 255 for i in range(3, len(rgba), 4))
            self._pictures[key] = (pvr.png_bytes(w, h, rgba), alpha)
        return self._pictures[key]


# objects that react when the skater hits them: roots (host addresses) of stage objects, by stage; each placement
# becomes a node `prop_<root>_<n>` of its own so that the game can tip and wobble it
DYNAMIC_PROPS = {
    "1": {0x8CC6BBA4: "pole", 0x8CC79224: "cone"},
}


# flat facade cards of the far skyline that float in the air (every corner above 20 units): the PC release has none of them.
# stage -> {(pack, member, picture index)}
FLOATING_CARDS = {
    "1": {("STAGE1TXP_ALL.AFS", 0, 74), ("STAGE1TXP_ALL.AFS", 0, 77), ("STAGE1TXP_ALL.AFS", 0, 126)},
}


def _quat(m):
    # rotation part of a row-major 4x4 matrix as a quaternion (x, y, z, w)
    r = [row[:3] for row in m[:3]]
    t = r[0][0] + r[1][1] + r[2][2]
    if t > 0:
        k = math.sqrt(t + 1.0) * 2.0
        return ((r[2][1] - r[1][2]) / k, (r[0][2] - r[2][0]) / k, (r[1][0] - r[0][1]) / k, 0.25 * k)
    if r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        k = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2.0
        return (0.25 * k, (r[0][1] + r[1][0]) / k, (r[0][2] + r[2][0]) / k, (r[2][1] - r[1][2]) / k)
    if r[1][1] > r[2][2]:
        k = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2.0
        return ((r[0][1] + r[1][0]) / k, 0.25 * k, (r[1][2] + r[2][1]) / k, (r[0][2] - r[2][0]) / k)
    k = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2.0
    return ((r[0][2] + r[2][0]) / k, (r[1][2] + r[2][1]) / k, 0.25 * k, (r[1][0] - r[0][1]) / k)


def export_stage(bindings, pictures, game, out_dir, stem, label, flip_z):
    archive_name = "STAGE%s.AFS" % stem.upper()
    prefix = "STAGE%s" % stem.upper()
    members = bindings.raw.get(archive_name) or [0]
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    data = afs.Archive(os.path.join(root, archive_name)).read(members[0])
    blob = ninja.Blob(data, STAGE_BASE)
    objs = ninja.find_objects(blob)
    models = {}
    for o in objs.values():
        if o.model and o.model not in models:
            models[o.model] = ninja.read_model(blob, o.model)

    valid = [a for a, o in objs.items() if models.get(o.model)]
    object_list = bindings.object_lists(valid)
    for sky_root, sky_list in SKY_LISTS.get(stem, {}).items():
        if sky_root in objs:
            for o, _ in ninja.tree_nodes(objs, sky_root):
                object_list[o.addr] = bindings.header(sky_list)
    fallback = bindings.main_list(prefix)
    chosen = {}

    def slots_for(header):
        if header not in chosen:
            chosen[header] = bindings.choose(header, prefix) if header else {}
        return chosen[header]

    # what to draw: every placement of the stage, plus unplaced trees of backdrop size; stages without a
    # placement table (and trees nobody places) are drawn where they are modelled
    placements = layout.read(stem.upper(), bindings.image, data) if stem.upper() in layout.FAMILIES else []
    instances = []
    placed_roots = set()
    vehicles = 0
    dynamic = DYNAMIC_PROPS.get(stem, {})
    prop_groups = {}
    prop_places = {}
    car_groups = {}
    car_places = {}
    for pl in placements:
        if pl.root in objs:
            placed_roots.add(pl.root)
            if pl.root in dynamic:
                if pl.root not in prop_groups:
                    # a pole is two meshes: the foot that stays and the shaft the game tilts (the second object of
                    # the tree, the one its hit motion moves); other props are one mesh
                    prop_groups[pl.root] = {"base": {}, "tilt": {}} if dynamic[pl.root] == "pole" else {"base": {}}
                    header = bindings.header(pl.list) if pl.list else None
                    if dynamic[pl.root] == "pole":
                        tree_nodes = [o.addr for o, _ in ninja.tree_nodes(objs, pl.root)]
                        instances.append((pl.root, None, header, False, prop_groups[pl.root]["base"],
                                          set(tree_nodes[:1])))
                        instances.append((pl.root, None, header, False, prop_groups[pl.root]["tilt"],
                                          set(tree_nodes[1:])))
                    else:
                        instances.append((pl.root, None, header, False, prop_groups[pl.root]["base"], None))
                prop_places.setdefault(pl.root, []).append(pl)
                continue
            instances.append((pl.root, layout.matrix(pl.pos, pl.rot), bindings.header(pl.list) if pl.list else None, False,
                              None, None))
    if placements:
        # vehicles the missions of the stage put in the world
        for sp in mission.stage_spawns(bindings.image, stem.upper(), game):
            model = mission.vehicle_model(bindings.image, stem.upper(), sp.kind)
            if not model or not model[0]:
                continue
            p = model[0]
            root = 0x8C000000 | (p & 0x01FFFFFF) if 0x20000000 <= p < 0x22000000 else p
            if root in objs:
                header = bindings.header(model[1]) if model[1] else None
                # every vehicle is a node of its own so that the game can drive it (see stage.gd)
                if root not in car_groups:
                    car_groups[root] = {}
                    instances.append((root, None, header, False, car_groups[root], None))
                car_places.setdefault(root, []).append(sp)
                vehicles += 1
    # the vehicle types of the moving traffic (tools/traffic.py): one template each, copied by the game per car
    traffic_groups = {}
    if stem in traffic.TABLES:
        models_at, lists_at, kinds, _ = traffic.TABLES[stem]
        image = bindings.image
        for kind in range(kinds):
            model = struct.unpack_from(">I", image, models_at + 4 * kind - 0x82000000)[0]
            model = 0x8C000000 | (model & 0x01FFFFFF) if 0x20000000 <= model < 0x22000000 else model
            header = struct.unpack_from(">I", image, lists_at + 4 * kind - 0x82000000)[0]
            if model in objs:
                traffic_groups[kind] = {}
                instances.append((model, None, bindings.header(header) if header else None, False,
                                  traffic_groups[kind], None))
    for r in ninja.find_roots(objs):
        if r not in placed_roots:
            instances.append((r, None, None, bool(placements), None, None))

    builder = glb.Builder()
    stage_groups = {}
    backdrop_groups = {}
    zones_geometry = {"positions": [], "indices": []}
    triangles = 0
    unbound = 0
    for r, place, header, only_far, target, node_filter in instances:
        tree = ninja.walk_tree(blob, objs, r, place)
        meshes = [(o.addr, world, [p for p in models.get(o.model) if not p.volume] if models.get(o.model) else None)
                  for o, world in tree if models.get(o.model)]
        # volume chunks (types 56 to 58) of placed objects: large convex columns that tile the stage in sectors. They are
        # kept as a separate file for inspection; they are not walls the skater runs into
        if place is not None:
            for o, world in tree:
                for p in models.get(o.model) or []:
                    if p.volume:
                        base = len(zones_geometry["positions"])
                        zones_geometry["positions"] += [ninja.transform_point(world, v) for v in p.positions]
                        zones_geometry["indices"] += [base + i for i in p.indices]
        meshes = [m for m in meshes if m[2]]
        if node_filter is not None:
            meshes = [m for m in meshes if m[0] in node_filter]
        if not meshes:
            continue
        # the list of the tree is the first one found for any of its objects
        tree_header = header or next((object_list[a] for a, _, _ in meshes if a in object_list), fallback)
        # the largest extent decides whether the tree is stage geometry or the far backdrop
        lo = [1e30] * 3
        hi = [-1e30] * 3
        for _, world, prims in meshes:
            for p in prims:
                for pos in p.positions:
                    q = ninja.transform_point(world, pos)
                    for k in range(3):
                        lo[k] = min(lo[k], q[k])
                        hi[k] = max(hi[k], q[k])
        far = max(hi[k] - lo[k] for k in range(3)) > BACKDROP_EXTENT
        if only_far and not far:
            continue
        groups = target if target is not None else (backdrop_groups if far else stage_groups)
        for addr, world, prims in meshes:
            slots = slots_for(header or object_list.get(addr, tree_header))
            for p in prims:
                bound = slots.get(p.texture) if p.texture >= 0 else None
                if p.texture >= 0 and bound is None:
                    unbound += len(p.indices) // 3
                translucent = p.alpha and (p.diffuse >> 24) < 255
                key = (bound[:3] if bound else None, p.double_sided, translucent)
                g = groups.setdefault(key, {"positions": [], "uvs": [], "colors": [], "indices": []})
                base = len(g["positions"])
                for pos, uv, col in zip(p.positions, p.uvs, p.colors):
                    x, y, z = ninja.transform_point(world, pos)
                    if flip_z:
                        z = -z
                    g["positions"].append((x, y, z))
                    g["uvs"].append(uv)
                    g["colors"].append(_color(col, p.diffuse, bound is not None, p.alpha))
                if flip_z:
                    for i in range(0, len(p.indices), 3):
                        a, b, c = p.indices[i:i + 3]
                        g["indices"] += [base + a, base + c, base + b]
                else:
                    g["indices"] += [base + i for i in p.indices]
                triangles += len(p.indices) // 3
    if os.environ.get("JETSET_DEBUG_GROUPS"):
        import collections as _c
        for key, g in stage_groups.items():
            if key[0] is None:
                cc = _c.Counter(tuple(c) for c in g["colors"])
                print("untextured", key, len(g["indices"]) // 3, cc.most_common(6))
            ys = g["positions"]
            floating = sum(1 for k in range(0, len(g["indices"]), 3)
                           if min(ys[g["indices"][k + m]][1] for m in range(3)) > 20.0)
            print("group", key, len(g["indices"]) // 3, "floating", floating,
                  "x", round(min(v[0] for v in ys)), round(max(v[0] for v in ys)),
                  "z", round(min(v[2] for v in ys)), round(max(v[2] for v in ys)))
    used = set()

    def prims_for(groups):
        out = []
        for (bound, double, blend), g in sorted(groups.items(), key=lambda kv: (kv[0][0] or ("", 0, 0), kv[0][1:])):
            image = None
            mask = False
            if bound:
                png, has_alpha = pictures.get(*bound)
                image = builder.image(bound, png)
                mask = has_alpha
                used.add(bound)
            # cut-out cards (bicycles, leaves, grilles) are seen from both sides; the game does not cull them
            mat = builder.material(image, (1.0, 1.0, 1.0, 1.0), double or mask, mask, blend)
            out.append({"positions": g["positions"], "uvs": g["uvs"], "colors": g["colors"],
                        "indices": g["indices"], "material": mat})
        return out

    cards = FLOATING_CARDS.get(stem, set())
    if cards:
        for key, g in stage_groups.items():
            if key[0] in cards:
                pos = g["positions"]
                keep = []
                for k in range(0, len(g["indices"]), 3):
                    tri = g["indices"][k:k + 3]
                    if min(pos[i][1] for i in tri) > 20.0:
                        continue
                    keep += tri
                g["indices"] = keep
    builder.add_mesh("stage", prims_for(stage_groups))
    for kind, groups in traffic_groups.items():
        builder.add_node("traffic_%d" % kind, mesh=builder.mesh("traffic_%d" % kind, prims_for(groups)))
    for root, groups in car_groups.items():
        mesh = builder.mesh("car_%x" % root, prims_for(groups))
        for n, sp in enumerate(car_places[root]):
            q = _quat(layout.matrix(sp.pos, sp.rot))
            at = list(sp.pos)
            if flip_z:
                at[2] = -at[2]
                q = (-q[0], -q[1], q[2], q[3])
            builder.add_node("car_%d_%x" % (n, root), mesh=mesh, translation=at, rotation=q)
    for root, parts in prop_groups.items():
        kind = dynamic[root]
        base_mesh = builder.mesh("prop_%x" % root, prims_for(parts["base"]))
        tilt_mesh = builder.mesh("prop_%x_tilt" % root, prims_for(parts["tilt"])) if parts.get("tilt") else None
        for n, pl in enumerate(prop_places[root]):
            m = layout.matrix(pl.pos, pl.rot)
            q = _quat(m)
            at = list(pl.pos)
            if flip_z:
                at[2] = -at[2]
                q = (-q[0], -q[1], q[2], q[3])
            if tilt_mesh is None:
                builder.add_node("prop_%s_%d" % (kind, n), mesh=base_mesh, translation=at, rotation=q)
            else:
                parent = builder.add_node("prop_%s_%d" % (kind, n), translation=at, rotation=q)
                builder.add_node("base", mesh=base_mesh, parent=parent)
                builder.add_node("tilt", mesh=tilt_mesh, parent=parent)
    os.makedirs(os.path.join(out_dir, "models"), exist_ok=True)
    path = os.path.join(out_dir, "models", "stage%s.glb" % stem)
    builder.save(path)
    zones_path = os.path.join(out_dir, "models", "stage%s_zones.glb" % stem)
    if zones_geometry["indices"]:
        zones = glb.Builder()
        material = zones.material(None, (1.0, 1.0, 1.0, 1.0), True, False, False)
        zones.add_mesh("zones", [{"positions": zones_geometry["positions"], "uvs": [(0.0, 0.0)] * len(zones_geometry["positions"]),
                                  "colors": None, "indices": zones_geometry["indices"], "material": material}])
        zones.save(zones_path)
    elif os.path.exists(zones_path):
        os.remove(zones_path)
    return path, triangles, len(used), unbound, vehicles


def export_gallery(bindings, pictures, out_dir, file_name, blob, models_of, items, prefix):
    """Lay objects out in a grid, each with its own texture list, and write them as a glTF file.

    blob is a ninja.Blob, items a list of (object address in the host form, list header or None).
    """
    objs = ninja.find_objects(blob)
    rows = []
    widest = 1.0
    trees = {}
    for root, header in items:
        p = 0x8C000000 | (root & 0x01FFFFFF) if 0x20000000 <= root < 0x22000000 else root
        if p not in objs:
            continue
        nodes, prims = ninja.read_tree(blob, objs, p)
        if not prims:
            continue
        worlds = ninja.world_matrices(nodes)
        pts = [ninja.transform_point(worlds[o], v) for pr in prims if not pr.volume
               for v, o in zip(pr.positions, pr.owners)]
        if not pts:
            continue
        xs = [q[0] for q in pts]
        zs = [q[2] for q in pts]
        widest = max(widest, max(xs) - min(xs), max(zs) - min(zs))
        trees[p] = (nodes, prims)
        rows.append((p, header))
    spacing = widest * 1.4
    columns = max(1, int(round(len(rows) ** 0.5 * 1.3)))
    builder = glb.Builder()
    groups = {}
    for n, (p, header) in enumerate(rows):
        place = [[1.0, 0.0, 0.0, (n % columns) * spacing], [0.0, 1.0, 0.0, 0.0],
                 [0.0, 0.0, 1.0, (n // columns) * spacing], [0.0, 0.0, 0.0, 1.0]]
        slots = bindings.choose(bindings.header(header), prefix) if header else {}
        nodes, prims = trees[p]
        worlds = ninja.world_matrices(nodes, place)
        for pr in prims:
            if not pr.indices or pr.volume:
                continue
            bound = slots.get(pr.texture) if pr.texture >= 0 else None
            key = (bound[:3] if bound else None, pr.double_sided, False)
            g = groups.setdefault(key, {"positions": [], "uvs": [], "colors": [], "indices": []})
            base = len(g["positions"])
            for pos, uv, col, owner in zip(pr.positions, pr.uvs, pr.colors, pr.owners):
                g["positions"].append(ninja.transform_point(worlds[owner], pos))
                g["uvs"].append(uv)
                g["colors"].append(_color(col, pr.diffuse, bound is not None, pr.alpha))
            g["indices"] += [base + i for i in pr.indices]
    out = []
    for (bound, double, blend), g in sorted(groups.items(), key=lambda kv: (kv[0][0] or ("", 0, 0))):
        image, mask = None, False
        if bound:
            png, has_alpha = pictures.get(*bound)
            image = builder.image(bound, png)
            mask = has_alpha
        out.append({"positions": g["positions"], "uvs": g["uvs"], "colors": g["colors"], "indices": g["indices"],
                    "material": builder.material(image, (1.0, 1.0, 1.0, 1.0), double, mask, blend)})
    builder.add_mesh("stage", out)
    os.makedirs(os.path.join(out_dir, "models"), exist_ok=True)
    path = os.path.join(out_dir, "models", file_name)
    builder.save(path)
    return path, sum(len(g["indices"]) // 3 for g in groups.values()), len(rows)


def export_cast(bindings, pictures, game, out_dir, stem):
    """Vehicles and people of a stage as two lineups. Returns [(label suffix, file, triangles, count)]."""
    out = []
    stage = stem.upper()
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    if stage in mission.VEHICLE_TABLES or stage in mission.SINGLE_VEHICLE:
        data = afs.Archive(os.path.join(root, "STAGE%s.AFS" % stage)).read(
            (bindings.raw.get("STAGE%s.AFS" % stage) or [0])[0])
        blob = ninja.Blob(data, STAGE_BASE)
        kinds = [0] if stage in mission.SINGLE_VEHICLE else range(mission.VEHICLE_TABLES[stage][2])
        items, seen = [], set()
        for k in kinds:
            model = mission.vehicle_model(bindings.image, stage, k)
            if model and model[0] and model[0] not in seen:
                seen.add(model[0])
                items.append((model[0], model[1]))
        path, tris, n = export_gallery(bindings, pictures, out_dir, "stage%s_vehicles.glb" % stem, blob, None, items,
                                       "STAGE%s" % stage)
        if n and tris >= 20:     # stage 2 has one flat decal only
            out.append(("vehicles", "models/stage%s_vehicles.glb" % stem, tris, n))
        elif os.path.exists(path):
            os.remove(path)
    cast = mission.people(bindings.image, stage)
    if cast:
        arc = afs.Archive(os.path.join(root, "ENEMY.AFS"))
        wanted = {0x8C000000 | (o & 0x01FFFFFF) for _, o, _ in cast}
        for member in range(1, len(arc.members), 2):
            data = arc.read(member)
            blob = ninja.Blob(data, 0x8CAD0000)
            if wanted <= set(ninja.find_objects(blob)):
                items = [(o, l) for _, o, l in cast]
                path, tris, n = export_gallery(bindings, pictures, out_dir, "stage%s_people.glb" % stem, blob, None,
                                               items, "ENEMY")
                if n:
                    out.append(("people", "models/stage%s_people.glb" % stem, tris, n))
                break
    return out


def _color(word, diffuse, textured, use_alpha):
    """Vertex colour as RGBA bytes from the 0xAARRGGBB words of the model.

    A vertex colour is used when the model has one. Otherwise a textured polygon is left white (its
    diffuse is a lighting term that is not applied here) and an untextured one takes the diffuse.
    Alpha only counts when the polygon asks for it.
    """
    if word is not None:
        c = word
    elif textured:
        c = 0xFFFFFFFF if not use_alpha else 0x00FFFFFF | (diffuse & 0xFF000000)
    else:
        c = diffuse
    alpha = (c >> 24) & 0xFF if use_alpha else 255
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF, alpha)


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    flip_z = "--flip-z" in argv
    wanted = []
    i = 0
    while i < len(argv):
        if argv[i] == "--stage":
            wanted.append(argv[i + 1].lower())
            i += 1
        i += 1
    chosen = [s for s in STAGES if (s[0] in wanted if wanted else s[2])]
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, ".gdignore"), "a").close()
    bindings = texbind.Bindings(exe, game)
    pictures = Pictures(os.path.join(game, "DATA_BE", "JETRADIO"))
    index_path = os.path.join(out_dir, "index.json")
    index = []
    if os.path.exists(index_path) and wanted:
        with open(index_path) as f:
            index = [m for m in json.load(f).get("models", [])
                     if m["name"].split(" vehicles")[0].split(" people")[0] not in {s[1] for s in chosen}]
    for stem, label, _ in chosen:
        path, tris, images, unbound, listed = export_stage(bindings, pictures, game, out_dir, stem, label, flip_z)
        print("%s: %d triangles, %d textures, %d vehicles, %d triangles without a texture -> %s" %
              (label, tris, images, listed, unbound, path))
        index.append({"name": label, "file": "models/stage%s.glb" % stem, "triangles": tris})
        for kind, file_name, tris2, n in export_cast(bindings, pictures, game, out_dir, stem):
            print("   %s %s: %d models, %d triangles" % (label, kind, n, tris2))
            index.append({"name": "%s %s" % (label, kind), "file": file_name, "triangles": tris2})
    begin = mission.start_candidates(bindings.image, game)
    cans = mission.cans(bindings.image, game)
    lanes = mission.lane_points(bindings.image, game)
    items_b = mission.cans(bindings.image, game, 0x3C, 20)
    items_c = mission.cans(bindings.image, game, 0x40, 24)
    info = {}
    for stem, label, _ in STAGES:
        entry = {"label": label}
        if stem.upper() in begin:
            pos, look = begin[stem.upper()][0]
            entry["start"] = [round(v, 2) for v in pos]
            entry["look"] = [round(v, 2) for v in look]
            # the other places missions begin at, for when the first has no ground under it
            entry["others"] = [[round(v, 2) for v in p] + [round(v, 2) for v in lk] for p, lk in begin[stem.upper()][1:6]]
        if cans.get(stem.upper()):
            entry["cans"] = [[round(c[0], 1), round(c[1], 1), round(c[2], 1), c[3]] for c in cans[stem.upper()]]
        found_spots = spots.find(game, stem.upper()) if stem.upper() in layout.STAGE_ARCHIVES else []
        if found_spots:
            entry["spots"] = found_spots
        driven = traffic.read(bindings.image, game, stem.upper()) if stem.upper() in traffic.TABLES else None
        if driven:
            entry["traffic"] = driven
        if lanes.get(stem.upper()):
            entry["points"] = [[[round(v, 1) for v in p] for p in chain] for chain in lanes[stem.upper()]]
        for key, table in (("items_b", items_b), ("items_c", items_c)):
            if table.get(stem.upper()):
                entry[key] = [[round(c[0], 1), round(c[1], 1), round(c[2], 1), c[3]] for c in table[stem.upper()]]
        info[stem] = entry
    with open(os.path.join(out_dir, "stages.json"), "w") as f:
        json.dump(info, f, indent=1)
    order = {label: n for n, (_, label, _) in enumerate(STAGES)}
    index.sort(key=lambda m: (order.get(m["name"].split(" vehicles")[0].split(" people")[0], 99),
                              m["name"].endswith("vehicles") + 2 * m["name"].endswith("people")))
    with open(index_path, "w") as f:
        json.dump({"models": index}, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
