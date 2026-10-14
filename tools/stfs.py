"""List and unpack an Xbox 360 STFS package (the container used for arcade titles).

    python tools/stfs.py PACKAGE                          # header and file list
    python tools/stfs.py PACKAGE --extract DIR            # write all files under DIR
    python tools/stfs.py PACKAGE --extract DIR --only GLOB    # only matching paths (repeatable)

Standard library only.
"""
import fnmatch
import os
import struct
import sys

BLOCK = 0x1000
HASHES_PER_L0 = 0xAA
HASHES_PER_L1 = 0x70E4
ENTRY_SIZE = 0x40


class StfsError(Exception):
    pass


class Entry:
    def __init__(self, raw, index):
        flags = raw[0x28]
        self.index = index
        self.name = raw[:flags & 0x3F].decode("ascii", "replace")
        self.consecutive = bool(flags & 0x40)
        self.is_dir = bool(flags & 0x80)
        self.blocks = int.from_bytes(raw[0x29:0x2C], "little")
        self.start = int.from_bytes(raw[0x2F:0x32], "little")
        self.parent = struct.unpack_from(">h", raw, 0x32)[0]
        self.size = struct.unpack_from(">I", raw, 0x34)[0]
        self.path = self.name


class Stfs:
    def __init__(self, path):
        self.file = open(path, "rb")
        head = self.file.read(0x2000)
        self.magic = head[:4]
        if self.magic not in (b"LIVE", b"PIRS", b"CON "):
            raise StfsError("not an STFS package")
        self.content_type, = struct.unpack_from(">I", head, 0x344)
        self.media_id, = struct.unpack_from(">I", head, 0x354)
        self.title_id, = struct.unpack_from(">I", head, 0x360)
        self.header_size, = struct.unpack_from(">I", head, 0x340)
        self.display_name = self._text(head, 0x411)
        self.title_name = self._text(head, 0x1691)

        # volume descriptor
        vd = 0x379
        self.block_separation = head[vd + 2]
        self.table_blocks, = struct.unpack_from("<H", head, vd + 3)
        self.table_start = int.from_bytes(head[vd + 5:vd + 8], "little")
        self.allocated, self.free = struct.unpack_from(">II", head, vd + 0x1C)

        # read-only packages keep one copy of each hash table, read-write ones two
        self.copies = 1 if self.block_separation & 1 else 2
        self.data_start = (self.header_size + 0xFFF) & ~0xFFF
        self.entries = self._read_entries()

    @staticmethod
    def _text(head, offset):
        return head[offset:offset + 0x80].decode("utf-16-be", "replace").split("\0")[0]

    # Data blocks are interleaved with hash tables: one level 0 table per 0xAA blocks,
    # one level 1 table per 0x70E4, then a single level 2 table.
    def _data_position(self, n):
        c = self.copies
        pos = (((n + HASHES_PER_L0) // HASHES_PER_L0) * c) + n
        if n >= HASHES_PER_L0:
            pos += ((n + HASHES_PER_L1) // HASHES_PER_L1) * c
        if n >= HASHES_PER_L1:
            pos += c
        return pos

    def _hash_position(self, n):
        c = self.copies
        if n < HASHES_PER_L0:
            return 0
        step = 0xAB if c == 1 else 0x1AC
        pos = (n // HASHES_PER_L0) * step + ((n // HASHES_PER_L1) + 1) * c
        if n >= HASHES_PER_L1:
            pos += c
        return pos

    def read_block(self, n):
        self.file.seek(self.data_start + self._data_position(n) * BLOCK)
        return self.file.read(BLOCK)

    def next_block(self, n):
        self.file.seek(self.data_start + self._hash_position(n) * BLOCK + (n % HASHES_PER_L0) * 0x18)
        record = self.file.read(0x18)
        return int.from_bytes(record[0x15:0x18], "big")

    def block_chain(self, start, count, consecutive):
        blocks = []
        n = start
        for _ in range(count):
            blocks.append(n)
            n = n + 1 if consecutive else self.next_block(n)
        return blocks

    def _read_entries(self):
        data = b"".join(self.read_block(n) for n in self.block_chain(self.table_start, self.table_blocks, False))
        entries = []
        for i in range(len(data) // ENTRY_SIZE):
            raw = data[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
            if raw[0x28] & 0x3F == 0:
                break
            entries.append(Entry(raw, i))
        for e in entries:
            parts = [e.name]
            parent = e.parent
            while 0 <= parent < len(entries) and len(parts) < 64:
                parts.append(entries[parent].name)
                parent = entries[parent].parent
            e.path = "/".join(reversed(parts))
        return entries

    def files(self):
        return [e for e in self.entries if not e.is_dir]

    def extract(self, entry, root):
        root = os.path.abspath(root)
        dest = os.path.abspath(os.path.join(root, *entry.path.split("/")))
        if os.path.commonpath([root, dest]) != root:
            raise StfsError("unsafe path in package: %r" % entry.path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        remaining = entry.size
        with open(dest, "wb") as out:
            for n in self.block_chain(entry.start, entry.blocks, entry.consecutive):
                if remaining <= 0:
                    break
                out.write(self.read_block(n)[:remaining])
                remaining -= BLOCK
        return dest


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out_dir = None
    patterns = []
    args = argv[1:]
    while args:
        flag = args.pop(0)
        if flag not in ("--extract", "--only") or not args:
            raise SystemExit("usage: stfs.py PACKAGE [--extract DIR [--only GLOB ...]]")
        value = args.pop(0)
        if flag == "--extract":
            out_dir = value
        else:
            patterns.append(value)

    pkg = Stfs(argv[0])
    print("magic         %s" % pkg.magic.decode("ascii"))
    print("title         %s (%s)" % (pkg.title_name, pkg.display_name))
    print("ids           title %08X, media %08X, content type %08X" % (pkg.title_id, pkg.media_id, pkg.content_type))
    print("layout        %s, header 0x%X" % ("read-only" if pkg.copies == 1 else "read-write", pkg.header_size))
    print("blocks        %d used, %d free" % (pkg.allocated, pkg.free))
    print("file table    %d blocks, %d entries" % (pkg.table_blocks, len(pkg.entries)))
    total = 0
    for e in pkg.entries:
        if e.is_dir:
            print("  %12s  %s/" % ("<dir>", e.path))
        else:
            total += e.size
            print("  %12d  %s" % (e.size, e.path))
    print("total         %d bytes (%.1f MiB)" % (total, total / 1048576.0))

    if out_dir:
        count = 0
        for e in pkg.files():
            if patterns and not any(fnmatch.fnmatch(e.path, p) for p in patterns):
                continue
            pkg.extract(e, out_dir)
            count += 1
        # keeps the engine editor from importing the extracted files
        open(os.path.join(out_dir, ".gdignore"), "a").close()
        print("extracted     %d files to %s" % (count, out_dir))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except StfsError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
