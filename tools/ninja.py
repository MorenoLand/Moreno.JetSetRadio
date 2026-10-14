"""Read Ninja object trees and chunk models from pointer blobs.

A blob is a data block that was meant to be loaded at a fixed Dreamcast address (base). Pointers inside it are absolute
addresses; `p - base` is the offset in the blob. Formats are described in docs/formats.md.
"""
import math
import struct

VERTEX_SIZES = {34: 12, 35: 16, 41: 24, 42: 28}
STRIP_TYPES = (64, 65, 66)
VOLUME_TYPES = (56, 57, 58)


class Blob:
    def __init__(self, data, base):
        self.data = data
        self.base = base
        self.size = len(data)

    def has(self, p, align=4):
        return self.base <= p < self.base + self.size and (p - self.base) % align == 0

    def u16(self, p):
        return struct.unpack_from(">H", self.data, p - self.base)[0]

    def s16(self, p):
        return struct.unpack_from(">h", self.data, p - self.base)[0]

    def u32(self, p):
        return struct.unpack_from(">I", self.data, p - self.base)[0]

    def s32(self, p):
        return struct.unpack_from(">i", self.data, p - self.base)[0]

    def f32(self, p):
        return struct.unpack_from(">f", self.data, p - self.base)[0]

    def f32s(self, p, n):
        return struct.unpack_from(">%df" % n, self.data, p - self.base)


class Obj:
    __slots__ = ("addr", "flags", "model", "pos", "rot", "scale", "child", "sibling")


def _finite(v, limit):
    return not (math.isnan(v) or math.isinf(v)) and abs(v) < limit


def read_object(blob, p):
    """Return an Obj if the 0x34 bytes at p look like an object record, else None."""
    if p - blob.base + 0x34 > blob.size:
        return None
    flags, model = struct.unpack_from(">II", blob.data, p - blob.base)
    child, sibling = struct.unpack_from(">II", blob.data, p - blob.base + 0x2C)
    if flags & ~0x1FF:
        return None
    for ptr in (model, child, sibling):
        if ptr and not blob.has(ptr):
            return None
    if not (model or child):
        return None
    pos = blob.f32s(p + 8, 3)
    scale = blob.f32s(p + 0x20, 3)
    if not all(_finite(v, 1e5) for v in pos):
        return None
    if not all(_finite(v, 1e3) for v in scale) or all(v == 0 for v in scale):
        return None
    o = Obj()
    o.addr = p
    o.flags = flags
    o.model = model
    o.pos = pos
    o.rot = struct.unpack_from(">iii", blob.data, p - blob.base + 0x14)
    o.scale = scale
    o.child = child
    o.sibling = sibling
    return o


def find_objects(blob):
    out = {}
    for off in range(0, blob.size - 0x34, 4):
        o = read_object(blob, blob.base + off)
        if o:
            out[o.addr] = o
    return out


def find_roots(objs):
    """Objects that no other object lists as a child or sibling."""
    referenced = set()
    for o in objs.values():
        if o.child:
            referenced.add(o.child)
        if o.sibling:
            referenced.add(o.sibling)
    return [a for a in sorted(objs) if a not in referenced]


class Primitive:
    """Triangles that share a texture and render state."""

    def __init__(self, texture, diffuse, double_sided, alpha):
        self.texture = texture
        self.diffuse = diffuse
        self.double_sided = double_sided
        self.alpha = alpha
        self.positions = []
        self.normals = []
        self.uvs = []
        self.colors = []
        self.indices = []
        self.owners = []        # index of the object that wrote each vertex (read_tree), else None
        self.volume = False     # a collision volume (chunk types 56 to 58) rather than something that is drawn


def parse_vertices(blob, p):
    """Read a vertex list. Returns {index: (position, normal or None, color or None)} or None if malformed."""
    verts = {}
    steps = 0
    while blob.has(p, 4) and steps < 4096:
        steps += 1
        w = blob.u32(p)
        t = w & 0xFF
        if t == 0xFF:
            return verts
        if t not in VERTEX_SIZES or not blob.has(p + 4, 4):
            return None
        size = w >> 16
        w1 = blob.u32(p + 4)
        count, first = w1 >> 16, w1 & 0xFFFF
        per = VERTEX_SIZES[t]
        if size == 0 or (size - 1) * 4 != count * per or not blob.has(p + 4 + size * 4, 4) and p + 4 + size * 4 > blob.base + blob.size:
            return None
        q = p + 8
        for i in range(count):
            pos = blob.f32s(q, 3)
            normal = color = None
            if t in (41, 42):
                normal = blob.f32s(q + 12, 3)
            if t == 35:
                color = blob.u32(q + 12)
            elif t == 42:
                color = blob.u32(q + 24)
            verts[first + i] = (pos, normal, color)
            q += per
        p += 4 + size * 4
    return None


NO_TEXTURE = -1


def _material_color(word):
    """0xAARRGGBB from a material colour of a polygon list.

    The list is made of 16-bit units, so a 32-bit colour (bytes B G R A in the original) arrives with its
    halves exchanged inside each unit: the big-endian word reads 0xGGBBAARR.
    """
    g, b, a, r = (word >> 24) & 0xFF, (word >> 16) & 0xFF, (word >> 8) & 0xFF, word & 0xFF
    return (a << 24) | (r << 16) | (g << 8) | b


def parse_polygons(blob, p, verts, prims):
    """Walk a polygon list, appending triangles to prims (a dict keyed by render state)."""
    texture = NO_TEXTURE
    diffuse = 0xFFFFFFFF
    steps = 0
    while blob.has(p, 2) and steps < 100000:
        steps += 1
        head = blob.u16(p)
        t = head & 0xFF
        flags = head >> 8
        if t == 0xFF:
            return True
        if t < 8:
            p += 2
        elif t < 16:
            texture = blob.u16(p + 2) & 0x1FFF
            p += 4
        elif t < 32 or 56 <= t <= 58 or 64 <= t <= 75:
            size = blob.u16(p + 2)
            if 16 <= t < 24 and (t - 16) & 1:
                diffuse = _material_color(blob.u32(p + 4))
            if t in STRIP_TYPES:
                _strips(blob, p, t, flags, texture, diffuse, verts, prims)
            elif t in VOLUME_TYPES:
                _volumes(blob, p, t, verts, prims)
            p += 4 + size * 2
        else:
            return False
    return False


def _strips(blob, p, t, flags, texture, diffuse, verts, prims):
    count_word = blob.u16(p + 4)
    n = count_word & 0x3FFF
    user = count_word >> 14
    scale = 1.0 / 256.0 if t == 65 else 1.0 / 1024.0
    if t == 64:
        texture = NO_TEXTURE        # strips without texture coordinates are not textured
    key = (texture, diffuse, bool(flags & 0x10), bool(flags & 0x08))
    prim = prims.get(key)
    if prim is None:
        prim = prims[key] = Primitive(texture, diffuse, key[2], key[3])
    q = p + 6
    for _ in range(n):
        length = blob.s16(q)
        q += 2
        reverse = length < 0
        length = abs(length)
        strip = []
        for _ in range(length):
            idx = blob.u16(q)
            q += 2
            u = v = 0.0
            if t != 64:
                u = blob.s16(q) * scale
                v = blob.s16(q + 2) * scale
                q += 4
            q += user * 2
            strip.append((idx, u, v))
        for i in range(length - 2):
            a, b, c = strip[i], strip[i + 1], strip[i + 2]
            if (i & 1) ^ (1 if reverse else 0):
                a, b = b, a
            tri = []
            ok = True
            for idx, u, v in (a, b, c):
                vert = verts.get(idx)
                if vert is None:
                    ok = False
                    break
                tri.append((vert, u, v))
            if not ok:
                continue
            for vert, u, v in tri:
                pos, normal, color = vert[:3]
                prim.indices.append(len(prim.positions))
                prim.positions.append(pos)
                prim.normals.append(normal)
                prim.uvs.append((u, v))
                prim.colors.append(color)
                prim.owners.append(vert[3] if len(vert) > 3 else None)


def _volumes(blob, p, t, verts, prims):
    """Collision volumes: polygons of vertex indices with user words, as triangles of one Primitive.

    The chunk has a word `userWords << 14 | polygon count`. Type 56 holds triangles (3 indices), 57 quads (4
    indices in strip order), 58 strips (a signed length, the indices, then `userWords` for each polygon after
    the first).
    """
    count_word = blob.u16(p + 4)
    n = count_word & 0x3FFF
    user = count_word >> 14
    prim = prims.get(("volume",))
    if prim is None:
        prim = prims[("volume",)] = Primitive(NO_TEXTURE, 0xFFFFFFFF, True, False)
        prim.volume = True
    q = p + 6
    end = p + 4 + blob.u16(p + 2) * 2
    triangles = []
    for _ in range(n):
        if q >= end:
            break
        if t == 56:
            idx = [blob.u16(q + 2 * i) for i in range(3)]
            q += 6 + 2 * user
            triangles.append(tuple(idx))
        elif t == 57:
            idx = [blob.u16(q + 2 * i) for i in range(4)]
            q += 8 + 2 * user
            triangles.append((idx[0], idx[1], idx[2]))
            triangles.append((idx[2], idx[1], idx[3]))
        else:
            length = blob.s16(q)
            q += 2
            reverse = length < 0
            length = abs(length)
            strip = [blob.u16(q + 2 * i) for i in range(length)]
            q += 2 * length + 2 * user * max(length - 2, 0)
            for i in range(length - 2):
                a, b, c = strip[i], strip[i + 1], strip[i + 2]
                if (i & 1) ^ (1 if reverse else 0):
                    a, b = b, a
                triangles.append((a, b, c))
    for tri in triangles:
        pts = [verts.get(i) for i in tri]
        if any(v is None for v in pts):
            continue
        for v in pts:
            prim.indices.append(len(prim.positions))
            prim.positions.append(v[0])
            prim.normals.append(None)
            prim.uvs.append((0.0, 0.0))
            prim.colors.append(None)
            prim.owners.append(v[3] if len(v) > 3 else None)


def read_model(blob, p):
    """Return a list of Primitive for the model at p, or None if its lists do not parse."""
    if not blob.has(p, 4) or p - blob.base + 0x18 > blob.size:
        return None
    vlist, plist = blob.u32(p), blob.u32(p + 4)
    if not (vlist and plist and blob.has(vlist, 4) and blob.has(plist, 2)):
        return None
    verts = parse_vertices(blob, vlist)
    if not verts:
        return None
    prims = {}
    if not parse_polygons(blob, plist, verts, prims):
        return None
    return list(prims.values())


def read_tree(blob, objs, root):
    """Read a whole object tree, with the vertices objects share.

    The game keeps the vertices of the objects it has drawn in a buffer indexed by the numbers of the vertex lists,
    and the strips of an object may refer to vertices an earlier object of the tree wrote there: that is how the
    limbs of a character are joined to the body. Objects are drawn parent first, children before siblings.

    Returns (nodes, prims): nodes is [(object, parent address or None)] as tree_nodes gives it, prims a list of
    Primitive whose `owners` hold, for each vertex, the index of the node that wrote it. Positions are in the
    local space of that node.
    """
    nodes = tree_nodes(objs, root)
    index = {o.addr: i for i, (o, _) in enumerate(nodes)}
    cache = {}
    prims = []
    for i, (o, _) in enumerate(nodes):
        if not o.model or not blob.has(o.model, 4) or o.model - blob.base + 0x18 > blob.size:
            continue
        vlist, plist = blob.u32(o.model), blob.u32(o.model + 4)
        if not (vlist and plist and blob.has(vlist, 4) and blob.has(plist, 2)):
            continue
        verts = parse_vertices(blob, vlist)
        if not verts:
            continue
        for k, (pos, normal, color) in verts.items():
            cache[k] = (pos, normal, color, i)
        found = {}
        if parse_polygons(blob, plist, cache, found):
            prims.extend(found.values())
    return nodes, prims


def world_matrices(nodes, matrix=None):
    """World matrix of each node of tree_nodes' list, parents first."""
    worlds = []
    index = {}
    for i, (o, parent) in enumerate(nodes):
        base = worlds[index[parent]] if parent is not None else (matrix or _ident())
        worlds.append(_mat_mul(base, local_matrix(o)))
        index[o.addr] = i
    return worlds


# --- transforms -------------------------------------------------------------------------------------------------

def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _ident():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def local_matrix(o):
    m = _ident()
    if not o.flags & 0x01:
        m[0][3], m[1][3], m[2][3] = o.pos
    ang = [0.0, 0.0, 0.0]
    if not o.flags & 0x02:
        ang = [a * (2.0 * math.pi / 65536.0) for a in o.rot]
    sx, sy, sz = (1.0, 1.0, 1.0) if o.flags & 0x04 else o.scale

    def rot(axis, a):
        c, s = math.cos(a), math.sin(a)
        r = _ident()
        if axis == 0:
            r[1][1], r[1][2], r[2][1], r[2][2] = c, -s, s, c
        elif axis == 1:
            r[0][0], r[0][2], r[2][0], r[2][2] = c, s, -s, c
        else:
            r[0][0], r[0][1], r[1][0], r[1][1] = c, -s, s, c
        return r

    # the game's matrix routines: Z, Y, X by default, Y, X, Z with flag 0x20 (each applied after the previous)
    order = (1, 0, 2) if o.flags & 0x20 else (2, 1, 0)
    for axis in order:
        if ang[axis]:
            m = _mat_mul(m, rot(axis, ang[axis]))
    scale = _ident()
    scale[0][0], scale[1][1], scale[2][2] = sx, sy, sz
    return _mat_mul(m, scale)


def rotation_matrix(angles, flags):
    """Rotation of three angles in radians, in the order the game applies them for the object flags."""
    m = _ident()

    def rot(axis, a):
        c, s = math.cos(a), math.sin(a)
        r = _ident()
        if axis == 0:
            r[1][1], r[1][2], r[2][1], r[2][2] = c, -s, s, c
        elif axis == 1:
            r[0][0], r[0][2], r[2][0], r[2][2] = c, s, -s, c
        else:
            r[0][0], r[0][1], r[1][0], r[1][1] = c, -s, s, c
        return r

    for axis in ((1, 0, 2) if flags & 0x20 else (2, 1, 0)):
        if angles[axis]:
            m = _mat_mul(m, rot(axis, angles[axis]))
    return m


def quaternion(m):
    """(x, y, z, w) of a rotation matrix."""
    t = m[0][0] + m[1][1] + m[2][2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        return (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        return ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
    return ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)


def tree_nodes(objs, root):
    """(object, parent address or None) in the order walk_tree visits them."""
    out = []

    def visit(p, parent, depth):
        seen = set()
        while p and p in objs and p not in seen and depth < 64:
            seen.add(p)
            o = objs[p]
            out.append((o, parent))
            if o.child and not o.flags & 0x10:
                visit(o.child, p, depth + 1)
            p = o.sibling

    visit(root, None, 0)
    return out


def transform_point(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def transform_normal(m, n):
    x, y, z = n
    r = (m[0][0] * x + m[0][1] * y + m[0][2] * z,
         m[1][0] * x + m[1][1] * y + m[1][2] * z,
         m[2][0] * x + m[2][1] * y + m[2][2] * z)
    length = math.sqrt(r[0] * r[0] + r[1] * r[1] + r[2] * r[2]) or 1.0
    return (r[0] / length, r[1] / length, r[2] / length)


def walk_tree(blob, objs, root, matrix=None, depth=0, out=None):
    """Yield (object, world matrix) for the tree at root, following child and sibling links."""
    if out is None:
        out = []
    m0 = matrix or _ident()
    seen = set()
    p = root
    while p and p in objs and p not in seen and depth < 64:
        seen.add(p)
        o = objs[p]
        world = _mat_mul(m0, local_matrix(o))
        out.append((o, world))
        if o.child and not o.flags & 0x10:
            walk_tree(blob, objs, o.child, world, depth + 1, out)
        p = o.sibling
    return out


def inverse_affine(m):
    """Inverse of a 4x4 row-major matrix whose last row is 0 0 0 1."""
    a, b, c = m[0][0], m[0][1], m[0][2]
    d, e, f = m[1][0], m[1][1], m[1][2]
    g, h, i = m[2][0], m[2][1], m[2][2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        det = 1e-12
    inv = [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
           [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
           [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]
    t = (m[0][3], m[1][3], m[2][3])
    out = [[0.0] * 4 for _ in range(4)]
    for r in range(3):
        for k in range(3):
            out[r][k] = inv[r][k]
        out[r][3] = -(inv[r][0] * t[0] + inv[r][1] * t[1] + inv[r][2] * t[2])
    out[3][3] = 1.0
    return out
