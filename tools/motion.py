"""Read the game's object motions.

A motion is a header of

    u16 flags        0x0011 (position and angle keys), 0x0015 adds scale keys
    u16 frames       number of frames
    u32 table        pointer to the key table

and a key table of one 16-byte entry per object of the tree the motion is meant for, in tree order:

    u32 mask         0x01 position keys, 0x10 angle keys, 0x04 scale keys
    u32 position     frames * 3 floats
    u32 angles       frames * 3 s16, 65536 per turn
    u32 scale        frames * 3 floats

A channel that is missing keeps the value of the object. The key data of a motion sits before its table and
the table sits right before the header. Pointers are whatever the blob holds: offsets for the character
containers, absolute addresses for the scene blobs.

Camera motions of the scenes are a different, plainer layout (`read_camera`):

    u32 data         pointer to four channel pointers, then four key counts
    u32 frames
    u16 type         0x01C1: position, target, roll, field of view
    u16 interpolation

with 16-byte keys {frame, x, y, z} for position and target and 8-byte keys {frame, angle} for roll and view.
"""
import struct


class Motion:
    """Frames, and per object a dict with optional "pos", "ang" and "scl" lists of one tuple per frame."""

    def __init__(self, frames, flags, entries):
        self.frames = frames
        self.flags = flags
        self.entries = entries


def read(blob, ptr, objects):
    """The object motion at ptr for a tree of `objects` objects, or None if it does not look like one."""
    if not blob.has(ptr, 4) or ptr - blob.base + 8 > blob.size:
        return None
    flags, frames, table = struct.unpack_from(">HHI", blob.data, ptr - blob.base)
    if flags not in (0x11, 0x15) or frames == 0 or not blob.has(table, 4):
        return None
    if table - blob.base + objects * 16 > blob.size:
        return None
    entries = []
    for i in range(objects):
        mask, pos, ang, scl = struct.unpack_from(">4I", blob.data, table - blob.base + i * 16)
        entry = {}
        if mask & 0x01 and blob.has(pos, 4) and pos - blob.base + frames * 12 <= blob.size:
            entry["pos"] = [blob.f32s(pos + f * 12, 3) for f in range(frames)]
        if mask & 0x10 and blob.has(ang, 2) and ang - blob.base + frames * 6 <= blob.size:
            entry["ang"] = [struct.unpack_from(">3h", blob.data, ang - blob.base + f * 6) for f in range(frames)]
        if mask & 0x04 and blob.has(scl, 4) and scl - blob.base + frames * 12 <= blob.size:
            entry["scl"] = [blob.f32s(scl + f * 12, 3) for f in range(frames)]
        entries.append(entry)
    return Motion(frames, flags, entries)


class Camera:
    """A camera path: per frame position and target, with roll and field of view keys (BAMS, 65536 per turn)."""

    def __init__(self, frames, position, target, roll, fov):
        self.frames = frames
        self.position = position      # [(frame, (x, y, z))]
        self.target = target
        self.roll = roll              # [(frame, angle)]
        self.fov = fov


def read_camera(blob, ptr):
    """The camera motion record at ptr, or None."""
    if not blob.has(ptr, 4) or ptr - blob.base + 12 > blob.size:
        return None
    data, frames, kind, interp = struct.unpack_from(">IIHH", blob.data, ptr - blob.base)
    if kind != 0x01C1 or not blob.has(data, 4) or data - blob.base + 32 > blob.size:
        return None
    pointers = struct.unpack_from(">4I", blob.data, data - blob.base)
    counts = struct.unpack_from(">4I", blob.data, data - blob.base + 16)
    if frames > 4000:
        return None

    def vec(p, n):
        if n > 4000 or not blob.has(p, 4) or p - blob.base + 16 * n > blob.size:
            return None
        return [(struct.unpack_from(">I", blob.data, p - blob.base + 16 * i)[0], blob.f32s(p + 16 * i + 4, 3))
                for i in range(n)]

    def ang(p):
        # the count word of these two channels is not reliable; the keys run to the last frame
        out = []
        while blob.has(p, 4) and p - blob.base + 8 * (len(out) + 1) <= blob.size and len(out) < 4000:
            key = struct.unpack_from(">Ii", blob.data, p - blob.base + 8 * len(out))
            if out and key[0] <= out[-1][0]:
                break
            out.append(key)
            if key[0] >= frames - 1:
                break
        return out

    position, target = vec(pointers[0], counts[0]), vec(pointers[1], counts[1])
    if position is None or target is None:
        return None
    return Camera(frames, position, target, ang(pointers[2]), ang(pointers[3]))
