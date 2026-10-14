"""Find which pack texture goes into which slot of a texture list.

    python tools/texbind.py [--exe build/exe] [--game build/xbla] [--list 82CB5808]

For every pack it loads, the executable carries a descriptor. Two layouts exist:

  type 1  pairs of (patch array, address). A patch array holds (list header, slot) entries and the address
          is where one texture of the pack sits in memory once the pack is loaded.
  type 0  pairs of (record, address array). A record is (list header, count); the addresses fill the
          slots of that list in order.

Models refer to textures by slot, so this table is what turns a texture id into an image.

The address of a pack is not the destination of its load record, so the base is found by trying every
texture start of the member and keeping the one under which the most entries land on a texture.
"""
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import pvr

BASE = 0x82000000
IMAGE_END = 0x83400000
MEMORY = (0x8C000000, 0x8E000000)


class Bindings:
    def __init__(self, exe_dir, game_dir):
        self.image = open(os.path.join(exe_dir, "image.bin"), "rb").read()
        self.root = os.path.join(game_dir, "DATA_BE", "JETRADIO")
        self.names = {}
        with open(os.path.join(exe_dir, "partitions.tsv")) as f:
            for row in csv.DictReader(f, delimiter="\t"):
                self.names.setdefault(int(row["partition"]), row["name"])
        self.records = []
        self.raw = {}            # pack -> members loaded as plain data (type 2)
        with open(os.path.join(exe_dir, "load_lists.tsv")) as f:
            for row in csv.DictReader(f, delimiter="\t"):
                if row["type"] in ("0", "1") and int(row["descriptor"], 16):
                    self.records.append(row)
                elif row["type"] == "2":
                    name = self.names.get(int(row["partition"]))
                    if name and int(row["member"]) not in self.raw.setdefault(name, []):
                        self.raw[name].append(int(row["member"]))
        self._offsets = {}
        self._weights = {}
        self.slots = {}          # list header -> slot -> [(pack, member, texture index, global index)]
        self._resolve()

    def u32(self, va):
        return struct.unpack_from(">I", self.image, va - BASE)[0]

    def descriptor(self, va, kind):
        """[(address, [(list header, slot), ...]), ...] of one descriptor."""
        if kind == "0":
            return self._descriptor_lists(va)
        pairs = []
        while len(pairs) < 4096:
            info, addr = self.u32(va), self.u32(va + 4)
            if info == 0 and addr == 0:
                break
            if not (BASE <= info < IMAGE_END and MEMORY[0] <= addr < MEMORY[1]):
                break
            entries = []
            at = info
            while len(entries) < 64:
                header, slot = self.u32(at), self.u32(at + 4)
                if header == 0:
                    break
                entries.append((header, slot))
                at += 8
            pairs.append((addr, entries))
            va += 8
        return pairs

    def _descriptor_lists(self, va):
        merged = {}
        order = []
        while len(order) < 4096:
            record, addresses = self.u32(va), self.u32(va + 4)
            if not (BASE <= record < IMAGE_END and BASE <= addresses < IMAGE_END):
                break
            header, count = self.u32(record), self.u32(record + 4)
            if not (BASE <= header < IMAGE_END) or count > 256:
                break
            for slot in range(count):
                addr = self.u32(addresses + 4 * slot)
                if not MEMORY[0] <= addr < MEMORY[1]:
                    continue
                if addr not in merged:
                    merged[addr] = []
                    order.append(addr)
                merged[addr].append((header, slot))
            va += 8
        return [(a, merged[a]) for a in order]

    def textures(self, pack, member):
        """[(offset, global index)] of the textures of an archive member."""
        key = (pack, member)
        if key not in self._offsets:
            path = os.path.join(self.root, pack)
            found = []
            if os.path.exists(path):
                data = afs.Archive(path).read(member)
                found = [(q, g) for q, g, _, _ in pvr.locate(data)]
            self._offsets[key] = found
        return self._offsets[key]

    def _resolve(self):
        seen = set()
        for row in self.records:
            pack = self.names.get(int(row["partition"]))
            member = int(row["member"])
            desc = int(row["descriptor"], 16)
            if pack is None or (desc, pack, member) in seen:
                continue
            seen.add((desc, pack, member))
            pairs = self.descriptor(desc, row["type"])
            textures = self.textures(pack, member)
            if not pairs or not textures:
                continue
            starts = {o: i for i, (o, _) in enumerate(textures)}
            best, base = -1, None
            for o, _ in textures:
                candidate = pairs[0][0] - o
                hits = sum(1 for a, _ in pairs if a - candidate in starts)
                if hits > best:
                    best, base = hits, candidate
            if best < len(pairs):
                continue
            for addr, entries in pairs:
                index = starts[addr - base]
                for header, slot in entries:
                    self.slots.setdefault(header, {}).setdefault(slot, [])
                    item = (pack, member, index, textures[index][1])
                    if item not in self.slots[header][slot]:
                        self.slots[header][slot].append(item)

    def object_lists(self, objects):
        """object address -> list header, for the objects of one stage.

        The executable holds, per stage, arrays of object pointers (host form 0x20xxxxxx) that are
        followed by an array of list header pointers of the same length, so entry i of the second
        array is the texture list of object i. The distance between the two arrays is found per
        run of pointers by taking the one under which most entries land on a list header.
        """
        host = {0x20000000 | (a & 0x01FFFFFF): a for a in objects}
        n = len(self.image) // 4
        words = struct.unpack(">%dI" % n, self.image[:n * 4])
        headers = set(self.slots)
        spots = [i for i, w in enumerate(words) if w in host]
        runs, run = [], []
        for i in spots:
            if run and i - run[-1] > 16:
                runs.append(run)
                run = []
            run.append(i)
        if run:
            runs.append(run)
        result = {}
        for run in runs:
            votes = {}
            for i in run:
                for d in range(1, 1024):
                    if i + d < n and words[i + d] in headers:
                        votes[d] = votes.get(d, 0) + 1
            if not votes:
                continue
            d, count = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))
            if count * 2 < len(run):
                continue
            for i in run:
                if words[i + d] in headers:
                    result.setdefault(host[words[i]], words[i + d])
        return result

    def header(self, pointer):
        """The list header a list-table entry stands for.

        Most entries are the header itself. In the stages loaded with type 0 records the entry is the
        record `(list header, count, addresses ...)`, so the header is its first word.
        """
        if pointer in self.slots or not BASE <= pointer < IMAGE_END:
            return pointer
        first = self.u32(pointer)
        return first if first in self.slots else pointer

    def main_list(self, prefix):
        """The list header patched by the packs whose name starts with prefix, with most slots."""
        best = None
        for header, slots in self.slots.items():
            n = sum(1 for cands in slots.values() if any(c[0].startswith(prefix) for c in cands))
            if best is None or (n, -header) > best[0]:
                best = ((n, -header), header)
        return best[1] if best else None

    def choose(self, header, prefix):
        """slot -> (pack, member, texture index, global index), one candidate per slot.

        When several packs of a stage patch the same slot (the area packs replace each other),
        the pack that fills the most slots over all lists of the stage wins, so one area is
        picked consistently.
        """
        weight = self._weights.get(prefix)
        if weight is None:
            weight = {}
            for slots in self.slots.values():
                for cands in slots.values():
                    for c in cands:
                        if c[0].startswith(prefix):
                            weight[c[0]] = weight.get(c[0], 0) + 1
            self._weights[prefix] = weight
        out = {}
        for slot, cands in self.slots.get(header, {}).items():
            cands = [c for c in cands if c[0].startswith(prefix)]
            if cands:
                out[slot] = max(cands, key=lambda c: (weight[c[0]], -c[1], -c[2]))
        return out


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    b = Bindings(exe, game)
    if "--list" in argv:
        headers = [int(argv[argv.index("--list") + 1], 16)]
    else:
        headers = sorted(b.slots, key=lambda h: (-len(b.slots[h]), h))[:12]
    for h in headers:
        slots = b.slots.get(h, {})
        print("list %08X: %d slots" % (h, len(slots)))
        for slot in sorted(slots):
            print("  %2d  %s" % (slot, "; ".join("%s #%d tex %d gbix %X" % (p.replace(".AFS", ""), m, i, g)
                                                for p, m, i, g in slots[slot])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
