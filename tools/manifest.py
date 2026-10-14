"""Read the archive partition tables and the load lists from the unpacked executable image.

    python tools/manifest.py build/exe/image.bin --out build/exe

Writes partitions.tsv (one row per language slot and partition) and load_lists.tsv
(one row per load record). The addresses used are those of the retail executable.
"""
import os
import struct
import sys

BASE = 0x82000000
LANGUAGE_TABLES = 0x82D69300   # six pointers to partition tables
SLOTS = 6
PARTITIONS = 82                # rows per table, each {name pointer, member count}
LIST_END = 0x52                # partition field that ends a load list
RECORD_WORDS = 8


class ManifestError(Exception):
    pass


class Image:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.data = f.read()
        self.words = struct.unpack_from(">%dI" % (len(self.data) // 4), self.data, 0)

    def u32(self, va):
        return struct.unpack_from(">I", self.data, va - BASE)[0]

    def string(self, va):
        off = va - BASE
        if not 0 <= off < len(self.data):
            return None
        raw = self.data[off:self.data.index(b"\0", off)]
        if not 0 < len(raw) < 64 or any(c < 32 or c > 126 for c in raw):
            return None
        return raw.decode("ascii")

    def sections(self):
        """Name -> (first word index, end word index) for the PE sections."""
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        count, = struct.unpack_from("<H", self.data, pe + 6)
        opt_size, = struct.unpack_from("<H", self.data, pe + 20)
        out = {}
        at = pe + 24 + opt_size
        for _ in range(count):
            name = self.data[at:at + 8].split(b"\0")[0].decode("latin1")
            size, rva = struct.unpack_from("<II", self.data, at + 8)
            out[name] = (rva // 4, (rva + size) // 4)
            at += 40
        return out


def read_partitions(img):
    tables = [img.u32(LANGUAGE_TABLES + 4 * i) for i in range(SLOTS)]
    rows = []
    for slot, table in enumerate(tables):
        for part in range(PARTITIONS):
            ptr = img.u32(table + part * 8)
            count = img.u32(table + part * 8 + 4)
            name = img.string(ptr)
            if name is None:
                raise ManifestError("unexpected partition table at 0x%08X" % table)
            rows.append((slot, part, name, count))
    return rows


def plausible(w):
    return (w[0] < LIST_END and w[1] < 0x800 and w[5] <= 9 and
            (w[2] == 0 or 0x20000000 <= w[2] < 0x22000000 or 0x8C000000 <= w[2] < 0x8D000000))


def read_load_lists(img):
    """Runs of 8-word records that end with a record starting with LIST_END.

    Each list is found from its terminator and read backwards, so that an all-zero gap
    in front of a list is never taken for part of it.
    """
    words = img.words
    sections = img.sections()
    lists = []
    for name in (".rdata", ".data"):
        if name not in sections:
            raise ManifestError("image has no %s section" % name)
        lo, hi = sections[name]
        for end in range(lo, hi - RECORD_WORDS):
            if words[end] != LIST_END or any(words[end + 1:end + RECORD_WORDS]):
                continue
            first = end
            while first - RECORD_WORDS >= lo:
                rec = words[first - RECORD_WORDS:first]
                if not plausible(rec) or not any(rec):
                    break
                first -= RECORD_WORDS
            if first < end:
                lists.append((BASE + first * 4, [words[k:k + RECORD_WORDS] for k in range(first, end, RECORD_WORDS)]))
    return lists


def dreamcast_base(dest):
    if 0x20000000 <= dest < 0x22000000:
        return 0x8C000000 | (dest & 0x01FFFFFF)
    return dest


def tag_text(word):
    raw = struct.pack(">I", word)
    return raw[::-1].decode("latin1") if word and all(32 <= c < 127 for c in raw) else ""


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    img = Image(argv[0])
    partitions = read_partitions(img)
    lists = read_load_lists(img)
    records = sum(len(r) for _, r in lists)
    print("%d partitions in %d language tables, %d load lists with %d records" %
          (PARTITIONS, SLOTS, len(lists), records))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "partitions.tsv"), "w") as f:
            f.write("slot\tpartition\tname\tmembers\n")
            for row in partitions:
                f.write("%d\t%d\t%s\t%d\n" % row)
        with open(os.path.join(out_dir, "load_lists.tsv"), "w") as f:
            f.write("list\tindex\tpartition\tmember\tdestination\tbase\tdescriptor\tcount\ttype\ttag\tflag\n")
            for address, recs in lists:
                for n, r in enumerate(recs):
                    base = "" if r[2] == 0 else "%08X" % dreamcast_base(r[2])
                    f.write("%08X\t%d\t%d\t%d\t%08X\t%s\t%08X\t%d\t%d\t%s\t%02X\n" %
                            (address, n, r[0], r[1], r[2], base, r[3], r[4], r[5], tag_text(r[6]), r[7] & 0xFF))
        print("wrote partitions.tsv and load_lists.tsv in %s" % out_dir)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ManifestError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
