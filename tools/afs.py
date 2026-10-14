"""Read AFS archives and their .OFS relocation lists.

    python tools/afs.py ARCHIVE                  # list the members
    python tools/afs.py ARCHIVE --extract DIR    # write each member to DIR/<index>.bin
"""
import os
import struct
import sys

SECTOR = 0x800


class AfsError(Exception):
    pass


class Archive:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            head = f.read(8)
            if head[:4] != b"AFS\0":
                raise AfsError("%s is not an AFS archive" % path)
            count = struct.unpack_from("<I", head, 4)[0]
            table = f.read(8 * count)
        self.members = [struct.unpack_from("<II", table, i * 8) for i in range(count)]

    def __len__(self):
        return len(self.members)

    def read(self, index):
        offset, size = self.members[index]
        with open(self.path, "rb") as f:
            f.seek(offset)
            return f.read(size)

    def offset(self, index):
        return self.members[index][0]

    def relocation_list(self):
        """Absolute file offsets of the pointer words, from the sibling .OFS file (empty if none)."""
        ofs = self.path[:-3] + "OFS"
        if not os.path.exists(ofs):
            return []
        with open(ofs, "rb") as f:
            raw = f.read()
        values = struct.unpack("<%dI" % (len(raw) // 4), raw)
        out = []
        for v in values:
            if v == 0:
                break
            out.append(v)
        return out


def main(argv):
    if not argv:
        print(__doc__)
        return 0
    arc = Archive(argv[0])
    if "--extract" in argv:
        out = argv[argv.index("--extract") + 1]
        os.makedirs(out, exist_ok=True)
        for i in range(len(arc)):
            with open(os.path.join(out, "%03d.bin" % i), "wb") as f:
                f.write(arc.read(i))
        print("wrote %d members to %s" % (len(arc), out))
        return 0
    print("%s: %d members, %d relocation entries" % (os.path.basename(argv[0]), len(arc), len(arc.relocation_list())))
    for i, (off, size) in enumerate(arc.members):
        print("  %3d  offset 0x%08X  size %9d" % (i, off, size))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except AfsError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
