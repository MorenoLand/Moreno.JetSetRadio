"""Read the character containers of PLAYER.AFS.

    python tools/play.py [--game build/xbla] [--member 0]

A character is two members: a `PLAY` container with the models and motions, and the `PTEX` container that follows it
with the textures. Both start with `{tag, offset of table A, offset of table B}` and hold offsets relative to the start
of the member in place of pointers.

PLAY table A is a list of `{kind, offset}` pairs ended by kind 0:

    1  an object tree (five of them: the same figure in different states)
    2  a second object tree
    3  an array of 176 motion offsets, for the first tree
    4  three motion offsets, for the second tree
    5  an object-like structure
    6  a larger structure
    7  a list of items

Motions (kind 3, 176 of them with the flag word 0x0011; the three of kind 4 have 0x0015 and belong to the second tree)
are laid out as

    table      one 16-byte entry per object of the first tree, in tree order:
                   u32 mask, u32 position keys, u32 angle keys, u32 scale keys
               mask 0x01 position keys (three floats per frame), 0x10 angle keys (three s16 per frame, 65536 per turn),
               0x04 scale keys (three floats per frame); a missing channel keeps the object's own value
    header     u16 flags, u16 number of frames, u32 pointer to the table (the table sits right before the header)

PTEX table A is a list of records `{list header, count, address * count}`: the textures of one list, as offsets into the
member. The first tree of a PLAY container uses the first list, the second tree the second list and so on.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import motion
import ninja
import pvr


MOTIONS = 176      # entries of the motion array of the first tree


class Character:
    def __init__(self, play, ptex):
        self.play = play
        self.ptex = ptex
        self.blob = ninja.Blob(play, 0)
        self.objects = ninja.find_objects(self.blob)
        a = struct.unpack_from(">I", play, 4)[0]
        self.table = []
        o = a
        while o + 8 <= len(play):
            kind, off = struct.unpack_from(">II", play, o)
            if kind == 0:
                break
            self.table.append((kind, off))
            o += 8
        self.trees = [off for kind, off in self.table if kind == 1]
        self.extra_trees = [off for kind, off in self.table if kind == 2]
        self.lists = self._lists()
        self._textures = list(pvr.locate(ptex))

    def _lists(self):
        data = self.ptex
        a = struct.unpack_from(">I", data, 4)[0]
        out = []
        o = a
        # table A holds pairs (record offset, address array offset); read each record
        seen = []
        while o + 4 <= len(data):
            rec = struct.unpack_from(">I", data, o)[0]
            if rec == 0 or rec + 8 > len(data) or rec in seen:
                break
            seen.append(rec)
            o += 8
        for rec in seen:
            header, count = struct.unpack_from(">II", data, rec)
            if count > 16:
                continue
            addresses = list(struct.unpack_from(">%dI" % count, data, rec + 8))
            out.append(addresses)
        return out

    def motions(self, objects):
        """Decode the first tree's motions. `objects` is the number of objects of that tree."""
        data = self.play
        start = next((off for kind, off in self.table if kind == 3), None)
        out = []
        if start is None:
            return out
        o = start
        while o + 4 <= len(data) and len(out) < MOTIONS:
            ptr = struct.unpack_from(">I", data, o)[0]
            o += 4
            m = motion.read(self.blob, ptr, objects) if ptr else None
            if m is None:
                break
            out.append(m)
        return out

    def texture_at(self, offset):
        for i, (q, gbix, pvrt, end) in enumerate(self._textures):
            if q == offset:
                return i
        return None

    def image(self, index):
        q, gbix, pvrt, end = self._textures[index]
        pixel, fmt = self.ptex[pvrt + 8], self.ptex[pvrt + 9]
        w, h = struct.unpack_from("<HH", self.ptex, pvrt + 12)
        return gbix, w, h, pvr.decode(pixel, fmt, w, h, self.ptex[pvrt + 16:end])

    def slots(self, tree_number):
        """slot -> texture index of the PTEX container for the n-th tree."""
        if tree_number >= len(self.lists):
            return {}
        out = {}
        for slot, address in enumerate(self.lists[tree_number]):
            idx = self.texture_at(address)
            if idx is not None:
                out[slot] = idx
        return out


def load(game, member):
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "PLAYER.AFS"))
    return Character(arc.read(member), arc.read(member + 1))


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    only = int(argv[argv.index("--member") + 1]) if "--member" in argv else None
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "PLAYER.AFS"))
    for m in range(len(arc.members)):
        d = arc.read(m)
        if d[:4] != b"YALP" or (only is not None and m != only):
            continue
        c = Character(d, arc.read(m + 1))
        print("member %2d: %d trees %s, %d extra, %d lists %s, %d textures" % (
            m, len(c.trees), [hex(t) for t in c.trees][:3], len(c.extra_trees), len(c.lists),
            [len(l) for l in c.lists], len(c._textures)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
