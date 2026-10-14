"""Write binary glTF (.glb) files from triangle primitives and PNG images."""
import json
import struct


def _pad(b, byte=b"\0"):
    return b + byte * ((4 - len(b) % 4) % 4)


class Builder:
    def __init__(self):
        self.blob = bytearray()
        self.views = []
        self.accessors = []
        self.images = []
        self.textures = []
        self.materials = []
        self.meshes = []
        self.nodes = []
        self.animations = []
        self.skins = []
        self._children = set()
        self._image_index = {}
        self._material_index = {}

    def _view(self, data, target=None):
        offset = len(self.blob)
        self.blob += _pad(bytes(data))
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target:
            view["target"] = target
        self.views.append(view)
        return len(self.views) - 1

    def _accessor(self, view, component, count, kind, minimum=None, maximum=None, normalized=False):
        acc = {"bufferView": view, "componentType": component, "count": count, "type": kind}
        if minimum is not None:
            acc["min"] = minimum
            acc["max"] = maximum
        if normalized:
            acc["normalized"] = True
        self.accessors.append(acc)
        return len(self.accessors) - 1

    def image(self, key, png_bytes):
        if key not in self._image_index:
            view = self._view(png_bytes)
            self.images.append({"bufferView": view, "mimeType": "image/png"})
            self.textures.append({"source": len(self.images) - 1, "sampler": 0})
            self._image_index[key] = len(self.textures) - 1
        return self._image_index[key]

    def material(self, texture_index, color, double_sided, mask, blend=False, unlit=True):
        key = (texture_index, color, double_sided, mask, blend, unlit)
        if key not in self._material_index:
            m = {"pbrMetallicRoughness": {"baseColorFactor": list(color), "metallicFactor": 0.0, "roughnessFactor": 1.0},
                 "doubleSided": double_sided}
            if unlit:
                m["extensions"] = {"KHR_materials_unlit": {}}
            if texture_index is not None:
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": texture_index}
            if blend:
                m["alphaMode"] = "BLEND"
            elif mask:
                m["alphaMode"] = "MASK"
                m["alphaCutoff"] = 0.5
            self.materials.append(m)
            self._material_index[key] = len(self.materials) - 1
        return self._material_index[key]

    def add_mesh(self, name, primitives, limit=200):
        """primitives: list of dicts with positions, uvs, colors (or None), indices, material.

        An engine mesh holds at most 256 surfaces, so a long list is written as several meshes
        named name, name_1, name_2 ...
        """
        for n, start in enumerate(range(0, max(len(primitives), 1), limit)):
            self._add_mesh(name if n == 0 else "%s_%d" % (name, n), primitives[start:start + limit])

    def _add_mesh(self, name, primitives):
        self.nodes.append({"name": name, "mesh": self.mesh(name, primitives)})

    def mesh(self, name, primitives):
        """Write a mesh without a node. Returns its index for add_node."""
        prims = []
        for p in primitives:
            pos = p["positions"]
            xs = [v[0] for v in pos]
            ys = [v[1] for v in pos]
            zs = [v[2] for v in pos]
            data = bytearray()
            for v in pos:
                data += struct.pack("<3f", *v)
            attrs = {"POSITION": self._accessor(self._view(data, 34962), 5126, len(pos), "VEC3",
                                                [min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])}
            data = bytearray()
            for u, v in p["uvs"]:
                data += struct.pack("<2f", u, v)
            attrs["TEXCOORD_0"] = self._accessor(self._view(data, 34962), 5126, len(pos), "VEC2")
            if p.get("normals") is not None:
                data = bytearray()
                for nrm in p["normals"]:
                    data += struct.pack("<3f", *nrm)
                attrs["NORMAL"] = self._accessor(self._view(data, 34962), 5126, len(pos), "VEC3")
            if p.get("colors") is not None:
                data = bytearray()
                for c in p["colors"]:
                    data += struct.pack("<4B", *c)
                attrs["COLOR_0"] = self._accessor(self._view(data, 34962), 5121, len(pos), "VEC4", normalized=True)
            if p.get("joints") is not None:
                # every vertex follows one joint; the stitching strips between parts then stretch with the motion
                data = bytearray()
                for j in p["joints"]:
                    data += struct.pack("<4H", j, 0, 0, 0)
                attrs["JOINTS_0"] = self._accessor(self._view(data, 34962), 5123, len(pos), "VEC4")
                data = struct.pack("<4f", 1.0, 0.0, 0.0, 0.0) * len(pos)
                attrs["WEIGHTS_0"] = self._accessor(self._view(data, 34962), 5126, len(pos), "VEC4")
            idx = p["indices"]
            data = struct.pack("<%dI" % len(idx), *idx)
            index_acc = self._accessor(self._view(data, 34963), 5125, len(idx), "SCALAR")
            prims.append({"attributes": attrs, "indices": index_acc, "material": p["material"], "mode": 4})
        self.meshes.append({"name": name, "primitives": prims})
        return len(self.meshes) - 1

    def skin(self, joints, inverse_bind):
        """A skin over the given node indices; inverse_bind is a 4x4 row-major matrix per joint."""
        data = bytearray()
        for m in inverse_bind:
            for col in range(4):
                for row in range(4):
                    data += struct.pack("<f", m[row][col])
        acc = self._accessor(self._view(data), 5126, len(joints), "MAT4")
        self.skins.append({"joints": list(joints), "inverseBindMatrices": acc})
        return len(self.skins) - 1

    def add_node(self, name, mesh=None, parent=None, translation=None, rotation=None, scale=None, skin=None):
        """A node of a hierarchy. Returns its index; nodes without a parent are the roots of the scene."""
        node = {"name": name}
        if mesh is not None:
            node["mesh"] = mesh
        if skin is not None:
            node["skin"] = skin
        if translation is not None:
            node["translation"] = [float(v) for v in translation]
        if rotation is not None:
            node["rotation"] = [float(v) for v in rotation]
        if scale is not None:
            node["scale"] = [float(v) for v in scale]
        self.nodes.append(node)
        index = len(self.nodes) - 1
        if parent is not None:
            self.nodes[parent].setdefault("children", []).append(index)
            self._children.add(index)
        return index

    def add_animation(self, name, channels, fps):
        """channels: list of (node index, "translation" | "rotation" | "scale", values), one value per frame.

        A channel with a single value holds it for the whole animation.
        """
        frames = max(len(v) for _, _, v in channels)
        times = bytearray()
        for f in range(frames):
            times += struct.pack("<f", f / fps)
        time_acc = self._accessor(self._view(times), 5126, frames, "SCALAR", [0.0], [(frames - 1) / fps])
        hold_acc = None
        samplers, targets = [], []
        for node, path, values in channels:
            data = bytearray()
            width = 4 if path == "rotation" else 3
            held = len(values) == 1 and frames > 1
            for v in (list(values) * 2 if held else values):
                data += struct.pack("<%df" % width, *v)
            acc = self._accessor(self._view(data), 5126, 2 if held else len(values), "VEC4" if width == 4 else "VEC3")
            if held:
                if hold_acc is None:
                    hold = struct.pack("<2f", 0.0, (frames - 1) / fps)
                    hold_acc = self._accessor(self._view(hold), 5126, 2, "SCALAR", [0.0], [(frames - 1) / fps])
                samplers.append({"input": hold_acc, "output": acc, "interpolation": "LINEAR"})
            elif len(values) != frames:
                continue
            else:
                samplers.append({"input": time_acc, "output": acc, "interpolation": "LINEAR"})
            targets.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path}})
        self.animations.append({"name": name, "samplers": samplers, "channels": targets})

    def save(self, path):
        doc = {
            "asset": {"version": "2.0", "generator": "jetset tools/glb.py"},
            "scene": 0,
            "scenes": [{"nodes": [i for i in range(len(self.nodes)) if i not in self._children]}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "buffers": [{"byteLength": len(self.blob)}],
            "bufferViews": self.views,
            "accessors": self.accessors,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        }
        if any("extensions" in m for m in self.materials):
            doc["extensionsUsed"] = ["KHR_materials_unlit"]
        if self.animations:
            doc["animations"] = self.animations
        if self.skins:
            doc["skins"] = self.skins
        if self.images:
            doc["images"] = self.images
            doc["textures"] = self.textures
        js = _pad(json.dumps(doc, separators=(",", ":")).encode("utf-8"), b" ")
        bin_chunk = _pad(bytes(self.blob))
        total = 12 + 8 + len(js) + 8 + len(bin_chunk)
        with open(path, "wb") as f:
            f.write(struct.pack("<4sII", b"glTF", 2, total))
            f.write(struct.pack("<I4s", len(js), b"JSON"))
            f.write(js)
            f.write(struct.pack("<I4s", len(bin_chunk), b"BIN\0"))
            f.write(bin_chunk)
