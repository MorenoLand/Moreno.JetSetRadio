"""Write an object tree as a skinned glTF mesh.

The vertices of a tree follow the object that wrote them (see ninja.read_tree), and the strips that join the
parts of a body refer to vertices of neighbouring objects. As a skin with one joint per vertex they stretch the
same way when the joints move.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract
import ninja

TURN = 6.283185307179586 / 65536.0


def add_skinned_tree(builder, blob, objs, root, texture_for, name, translation=None, rotation=None):
    """Add the tree at root to the builder.

    texture_for(texture id) returns (key, png bytes, has alpha) or None for an untextured polygon.
    translation and rotation, when given, replace the position and angles of the root object.
    Returns [(object, node index)] in tree order, the joints of the skin.
    """
    nodes, prims = ninja.read_tree(blob, objs, root)
    worlds = ninja.world_matrices(nodes)
    index = {}
    order = []
    for n, (o, parent) in enumerate(nodes):
        angles = [0.0] * 3 if o.flags & 0x02 else [a * TURN for a in o.rot]
        rest = ninja.quaternion(ninja.rotation_matrix(angles, o.flags))
        pos = (0.0, 0.0, 0.0) if o.flags & 0x01 else o.pos
        scale = (1.0, 1.0, 1.0) if o.flags & 0x04 else o.scale
        if parent is None:
            node = builder.add_node(name, None, None, translation if translation is not None else pos,
                                    rotation if rotation is not None else rest, scale)
        else:
            node = builder.add_node("%s_part%02d" % (name, n), None, index[parent], pos, rest, scale)
        index[o.addr] = node
        order.append((o, node))

    groups = {}
    for p in prims:
        if not p.indices or p.volume:
            continue
        found = texture_for(p.texture) if p.texture >= 0 else None
        key = (found[0] if found else None, p.double_sided)
        g = groups.setdefault(key, {"positions": [], "uvs": [], "colors": [], "indices": [], "joints": [],
                                    "normals": [], "found": found})
        base = len(g["positions"])
        for pos, nrm, uv, col, owner in zip(p.positions, p.normals, p.uvs, p.colors, p.owners):
            g["positions"].append(ninja.transform_point(worlds[owner], pos))
            g["normals"].append(ninja.transform_normal(worlds[owner], nrm) if nrm is not None else None)
            g["uvs"].append(uv)
            g["colors"].append(extract._color(col, p.diffuse, found is not None, p.alpha))
            g["joints"].append(owner)
        g["indices"] += [base + i for i in p.indices]
    out = []
    for (key, double), g in groups.items():
        image, mask = None, False
        if g["found"]:
            _, png, mask = g["found"]
            image = builder.image(key, png)
        lit = all(n is not None for n in g["normals"])
        out.append({"positions": g["positions"], "uvs": g["uvs"], "colors": g["colors"], "indices": g["indices"],
                    "joints": g["joints"], "normals": g["normals"] if lit else None,
                    "material": builder.material(image, (1.0, 1.0, 1.0, 1.0), double, mask, False, unlit=not lit)})
    if out:
        mesh = builder.mesh("%s_body" % name, out)
        skin = builder.skin([n for _, n in order], [ninja.inverse_affine(w) for w in worlds])
        builder.add_node("%s_skin" % name, mesh, None, skin=skin)
    return order
