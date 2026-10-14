"""Shared reading of the menu scenes (title, loading, garage, ...).

Each scene is one data block loaded at a fixed address with a table of pointers at its start (the "head"). What
a head entry is - an object tree, a motion, a camera path, a sprite - is not recorded in the block; the code that
draws the scene knows. This module reads the entry kinds:

    object tree     a chain of 0x34-byte object records (see ninja.py)
    motion          {u16 flags, u16 frames, u32 key table} (see motion.py)
    camera path     {u32 data, u32 frames, u16 0x01C1, u16 interpolation}
    sprite          a header {u32 pointer to element, u32 count 1, ... 1.0 x 6 ...} that points to an element of

                    u32  texture << 16 | attributes
                    f32  x, y, width, height       in a 640 x 480 screen
                    f32  0 (unused)
                    f32  pivot x, pivot y          0.5 = centred
                    u32  colour * 4                ARGB, one per corner
                    f32  u0, v0, u1, v1            texture rectangle, 0..1
"""
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import motion
import ninja
import rig
import texbind

FPS = 30.0
TURN = 2.0 * math.pi / 65536.0
LANGUAGE = "E_"


class Scene:
    def __init__(self, game, bindings, pictures, archive, member, base, prefix):
        self.game = game
        self.bindings = bindings
        self.pictures = pictures
        self.prefix = prefix
        root = os.path.join(game, "DATA_BE", "JETRADIO")
        self.data = afs.Archive(os.path.join(root, archive)).read(member)
        self.blob = ninja.Blob(self.data, base)
        self.base = base
        self.objs = ninja.find_objects(self.blob)
        self.models = {}
        for o in self.objs.values():
            if o.model and o.model not in self.models:
                self.models[o.model] = ninja.read_model(self.blob, o.model)

    # --- the head table ------------------------------------------------------------------------------------

    def head(self, offset):
        return self.blob.u32(self.base + offset)

    def exe(self, va):
        return struct.unpack_from(">I", self.bindings.image, va - texbind.BASE)[0]

    # --- sprites -------------------------------------------------------------------------------------------

    def sprite(self, header):
        """The sprite whose header is at `header`, or None."""
        b = self.blob
        if not b.has(header, 4) or header - self.base + 0x40 > b.size:
            return None
        element, count = struct.unpack_from(">II", self.data, header - self.base)
        if not b.has(element, 4) or count != 1 or element - self.base + 0x40 > b.size:
            return None
        ones = struct.unpack_from(">6f", self.data, header - self.base + 0x18)
        if not all(abs(v - 1.0) < 1e-6 for v in ones):
            return None
        flags = struct.unpack_from(">I", self.data, element - self.base)[0]
        x, y, w, h = struct.unpack_from(">4f", self.data, element - self.base + 4)
        pivot = struct.unpack_from(">2f", self.data, element - self.base + 0x18)
        colors = struct.unpack_from(">4I", self.data, element - self.base + 0x20)
        uv = struct.unpack_from(">4f", self.data, element - self.base + 0x30)
        if not all(-1.0 <= v <= 2.0 for v in uv):
            return None
        return {"header": header, "element": element, "texture": flags >> 16, "attributes": flags & 0xFFFF,
                "x": x, "y": y, "w": w, "h": h, "pivot": list(pivot), "colors": list(colors), "uv": list(uv)}

    def sprites(self):
        """Every sprite header of the block, in address order."""
        found = []
        for off in range(0, self.blob.size - 0x40, 4):
            s = self.sprite(self.base + off)
            if s:
                found.append(s)
        return found

    # --- trees ---------------------------------------------------------------------------------------------

    def png(self, bound):
        """(png bytes, has alpha) of a bound texture (pack, member, index), taking the language variant."""
        pack, member, index = bound
        localized = self.prefix + pack
        path = os.path.join(self.game, "DATA_BE", "JETRADIO", localized)
        return self.pictures.get(localized if os.path.exists(path) else pack, member, index)

    def add_tree(self, builder, root, slots, name, translation=None, rotation=None):
        """Write the tree at root as a skinned mesh over a joint hierarchy. Returns [(object, node)] in tree order."""

        def texture_for(texture):
            bound = slots.get(texture)
            if bound is None:
                return None
            png, alpha = self.png(bound[:3])
            return bound[:3], png, alpha

        return rig.add_skinned_tree(builder, self.blob, self.objs, root, texture_for, name, translation, rotation)

    def animate(self, builder, label, order, m):
        """Add the object motion m as an animation of the nodes of `order`."""
        channels = []
        for n, (o, node) in enumerate(order):
            entry = m.entries[n] if n < len(m.entries) else {}
            if "pos" in entry:
                channels.append((node, "translation", [tuple(v) for v in entry["pos"]]))
            if "ang" in entry:
                quats, last = [], None
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
            builder.add_animation(label, channels, FPS)
        return len(channels)

    def motion_at(self, ptr, objects):
        return motion.read(self.blob, ptr, objects) if ptr else None

    def camera_at(self, ptr):
        c = motion.read_camera(self.blob, ptr) if ptr else None
        if c is None:
            return None
        return {"frames": c.frames,
                "position": [list(v) for _, v in c.position], "target": [list(v) for _, v in c.target],
                "roll": [a * TURN for _, a in c.roll], "fov": [a * TURN for _, a in c.fov],
                "roll_frames": [f for f, _ in c.roll], "fov_frames": [f for f, _ in c.fov]}
