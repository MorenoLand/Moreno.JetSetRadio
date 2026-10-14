"""Unpack an Xbox 360 XEX2 executable.

    python tools/xex.py default.xex [--out DIR]

Decrypts and decompresses the executable and checks the result. With --out the
memory image and its tables are written to DIR:

    image.bin       the image as loaded in memory
    functions.tsv   function table: address, size, prolog length
    imports.tsv     import slots and thunks: address, kind, library, ordinal
    xex_info.json   headers, sections, import libraries and check results

Only the standard library is used. The exit code is 0 when all checks pass.
"""
import hashlib
import json
import os
import struct
import sys
import time

# Fixed keys that wrap the per-file AES key in an XEX2 file.
RETAIL_KEY = bytes.fromhex("20b185a59d28fdc340583fbb0896bf91")
DEVKIT_KEY = bytes(16)


class XexError(Exception):
    pass


# --- AES-128 (decryption only) ------------------------------------------------

def _gmul(a, b):
    r = 0
    while b:
        if b & 1:
            r ^= a
        a <<= 1
        if a & 0x100:
            a ^= 0x11B
        b >>= 1
    return r


def _make_aes_tables():
    # S-box from the multiplicative inverse and the affine transform.
    sbox = [0] * 256
    p = q = 1
    while True:
        p = (p ^ (p << 1) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1) | (q >> 7)) ^ ((q << 2) | (q >> 6)) ^ ((q << 3) | (q >> 5)) ^ ((q << 4) | (q >> 4))
        sbox[p] = (x ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    td0 = [(_gmul(inv[x], 14) << 24) | (_gmul(inv[x], 9) << 16) | (_gmul(inv[x], 13) << 8) | _gmul(inv[x], 11)
           for x in range(256)]
    rot = lambda w, n: ((w >> n) | (w << (32 - n))) & 0xFFFFFFFF
    return sbox, inv, td0, [rot(w, 8) for w in td0], [rot(w, 16) for w in td0], [rot(w, 24) for w in td0]


SBOX, INV_SBOX, TD0, TD1, TD2, TD3 = _make_aes_tables()


class Aes128:
    def __init__(self, key):
        w = list(struct.unpack(">4I", key))
        rcon = 1
        for i in range(4, 44):
            t = w[i - 1]
            if i % 4 == 0:
                t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
                t = (SBOX[t >> 24] << 24) | (SBOX[(t >> 16) & 255] << 16) | (SBOX[(t >> 8) & 255] << 8) | SBOX[t & 255]
                t ^= rcon << 24
                rcon = _gmul(rcon, 2)
            w.append(w[i - 4] ^ t)
        # round keys in reverse order, middle ones through InvMixColumns
        rk = []
        for r in range(10, -1, -1):
            rk.extend(w[r * 4:r * 4 + 4])
        for i in range(4, 40):
            t = rk[i]
            rk[i] = TD0[SBOX[t >> 24]] ^ TD1[SBOX[(t >> 16) & 255]] ^ TD2[SBOX[(t >> 8) & 255]] ^ TD3[SBOX[t & 255]]
        self.rk = rk

    def _block(self, s0, s1, s2, s3):
        rk = self.rk
        s0 ^= rk[0]
        s1 ^= rk[1]
        s2 ^= rk[2]
        s3 ^= rk[3]
        for k in range(4, 40, 4):
            t0 = TD0[s0 >> 24] ^ TD1[(s3 >> 16) & 255] ^ TD2[(s2 >> 8) & 255] ^ TD3[s1 & 255] ^ rk[k]
            t1 = TD0[s1 >> 24] ^ TD1[(s0 >> 16) & 255] ^ TD2[(s3 >> 8) & 255] ^ TD3[s2 & 255] ^ rk[k + 1]
            t2 = TD0[s2 >> 24] ^ TD1[(s1 >> 16) & 255] ^ TD2[(s0 >> 8) & 255] ^ TD3[s3 & 255] ^ rk[k + 2]
            t3 = TD0[s3 >> 24] ^ TD1[(s2 >> 16) & 255] ^ TD2[(s1 >> 8) & 255] ^ TD3[s0 & 255] ^ rk[k + 3]
            s0, s1, s2, s3 = t0, t1, t2, t3
        iv = INV_SBOX
        return (((iv[s0 >> 24] << 24) | (iv[(s3 >> 16) & 255] << 16) | (iv[(s2 >> 8) & 255] << 8) | iv[s1 & 255]) ^ rk[40],
                ((iv[s1 >> 24] << 24) | (iv[(s0 >> 16) & 255] << 16) | (iv[(s3 >> 8) & 255] << 8) | iv[s2 & 255]) ^ rk[41],
                ((iv[s2 >> 24] << 24) | (iv[(s1 >> 16) & 255] << 16) | (iv[(s0 >> 8) & 255] << 8) | iv[s3 & 255]) ^ rk[42],
                ((iv[s3 >> 24] << 24) | (iv[(s2 >> 16) & 255] << 16) | (iv[(s1 >> 8) & 255] << 8) | iv[s0 & 255]) ^ rk[43])

    def decrypt_block(self, data):
        return struct.pack(">4I", *self._block(*struct.unpack(">4I", data)))

    def decrypt_cbc(self, data, iv=bytes(16)):
        if len(data) % 16:
            raise XexError("data is not a multiple of 16 bytes")
        words = struct.unpack(">%dI" % (len(data) // 4), data)
        out = []
        prev = struct.unpack(">4I", iv)
        for i in range(0, len(words), 4):
            cur = words[i:i + 4]
            plain = self._block(*cur)
            out.extend(a ^ b for a, b in zip(plain, prev))
            prev = cur
        return struct.pack(">%dI" % len(out), *out)


# --- LZX ----------------------------------------------------------------------

POSITION_SLOTS = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}
FRAME_SIZE = 0x8000


def _position_tables():
    extra, base = [], []
    pos = 0
    for slot in range(52):
        e = 0 if slot < 4 else min((slot - 2) // 2, 17)
        extra.append(e)
        base.append(pos)
        pos += 1 << e
    return extra, base


EXTRA_BITS, POSITION_BASE = _position_tables()


def _huffman_table(lengths):
    """Lookup table over 16 bits: (symbol << 5) | code length, or 0 for an unused code."""
    table = [0] * 65536
    by_length = [[] for _ in range(17)]
    for sym, n in enumerate(lengths):
        if n:
            by_length[n].append(sym)
    code = 0
    for n in range(1, 17):
        for sym in by_length[n]:
            start = code << (16 - n)
            end = start + (1 << (16 - n))
            if end > 65536:
                raise XexError("over-subscribed Huffman code")
            table[start:end] = [(sym << 5) | n] * (end - start)
            code += 1
        code <<= 1
    return table


class _Reader:
    """Bits are taken most significant first from little-endian 16-bit words."""

    def __init__(self, data):
        self.data = data + bytes(8)
        self.pos = 0
        self.buf = 0
        self.count = 0

    def _fill(self, n):
        while self.count < n:
            if self.pos + 2 > len(self.data):
                raise XexError("LZX input ended early")
            self.buf = (self.buf << 16) | self.data[self.pos] | (self.data[self.pos + 1] << 8)
            self.pos += 2
            self.count += 16

    def bits(self, n):
        if n == 0:
            return 0
        self._fill(n)
        self.count -= n
        value = self.buf >> self.count
        self.buf &= (1 << self.count) - 1
        return value

    def symbol(self, table):
        self._fill(16)
        entry = table[(self.buf >> (self.count - 16)) & 0xFFFF]
        length = entry & 31
        if not length:
            raise XexError("invalid Huffman code")
        self.count -= length
        self.buf &= (1 << self.count) - 1
        return entry >> 5

    def drop_padding(self):
        # after an uncompressed block header: finish the current word, or skip a whole word
        word = (self.pos >> 1) - ((self.count + 15) >> 4)
        self.pos = (word + 1) * 2
        self.buf = self.count = 0

    def u32(self):
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def raw(self, n):
        if self.pos + n > len(self.data) - 8:
            raise XexError("LZX input ended early")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def skip_byte(self):
        self.pos += 1
        self.buf = self.count = 0


class LzxDecoder:
    """Decodes a stream of 32 KiB frames into one flat output buffer."""

    def __init__(self, window_bits, out_size):
        if window_bits not in POSITION_SLOTS:
            raise XexError("unsupported LZX window of 2^%d bytes" % window_bits)
        self.main_size = 256 + POSITION_SLOTS[window_bits] * 8
        self.out = bytearray(out_size)
        self.pos = 0
        self.main_lengths = [0] * self.main_size
        self.length_lengths = [0] * 249
        self.rep = [1, 1, 1]
        self.started = False
        self.block_type = 0
        self.block_size = 0
        self.block_left = 0
        self.main_table = self.length_table = self.aligned_table = None

    def _read_lengths(self, r, lengths, first, last):
        pretree = _huffman_table([r.bits(4) for _ in range(20)])
        i = first
        while i < last:
            code = r.symbol(pretree)
            if code == 17:
                run, value = r.bits(4) + 4, 0
            elif code == 18:
                run, value = r.bits(5) + 20, 0
            elif code == 19:
                run = r.bits(1) + 4
                value = (lengths[i] - r.symbol(pretree)) % 17
            else:
                run, value = 1, (lengths[i] - code) % 17
            if i + run > last:
                raise XexError("code length run overruns the tree")
            lengths[i:i + run] = [value] * run
            i += run

    def _start_block(self, r):
        if self.block_type == 3 and self.block_size & 1:
            r.skip_byte()
        self.block_type = r.bits(3)
        high = r.bits(16)
        self.block_size = self.block_left = (high << 8) | r.bits(8)
        if self.block_type in (1, 2):
            if self.block_type == 2:
                self.aligned_table = _huffman_table([r.bits(3) for _ in range(8)])
            self._read_lengths(r, self.main_lengths, 0, 256)
            self._read_lengths(r, self.main_lengths, 256, self.main_size)
            self.main_table = _huffman_table(self.main_lengths)
            self._read_lengths(r, self.length_lengths, 0, 249)
            self.length_table = _huffman_table(self.length_lengths)
        elif self.block_type == 3:
            r.drop_padding()
            self.rep = [r.u32(), r.u32(), r.u32()]
        else:
            raise XexError("bad LZX block type %d" % self.block_type)

    def _match_offset(self, r, slot):
        rep = self.rep
        if slot == 0:
            return rep[0]
        if slot == 1:
            rep[0], rep[1] = rep[1], rep[0]
            return rep[0]
        if slot == 2:
            rep[0], rep[2] = rep[2], rep[0]
            return rep[0]
        if slot == 3:
            offset = 1
        else:
            nbits = EXTRA_BITS[slot]
            offset = POSITION_BASE[slot] - 2
            if self.block_type == 2 and nbits >= 3:
                if nbits > 3:
                    offset += r.bits(nbits - 3) << 3
                offset += r.symbol(self.aligned_table)
            else:
                offset += r.bits(nbits)
        rep[2], rep[1], rep[0] = rep[1], rep[0], offset
        return offset

    def decode_frame(self, chunk, size):
        out = self.out
        pos = self.pos
        end = pos + size
        if end > len(out):
            raise XexError("more frames than the image holds")
        r = _Reader(bytes(chunk))
        if not self.started:
            if r.bits(1) and (r.bits(16) << 16 | r.bits(16)):
                raise XexError("x86 call translation is not supported")
            self.started = True
        while pos < end:
            if self.block_left == 0:
                self._start_block(r)
            run_end = pos + min(self.block_left, end - pos)
            start = pos
            if self.block_type == 3:
                out[pos:run_end] = r.raw(run_end - pos)
                pos = run_end
            else:
                main, lengths = self.main_table, self.length_table
                while pos < run_end:
                    sym = r.symbol(main)
                    if sym < 256:
                        out[pos] = sym
                        pos += 1
                        continue
                    sym -= 256
                    length = sym & 7
                    if length == 7:
                        length += r.symbol(lengths)
                    length += 2
                    offset = self._match_offset(r, sym >> 3)
                    src = pos - offset
                    if src < 0 or pos + length > end:
                        raise XexError("bad match at image offset %d" % pos)
                    if offset >= length:
                        out[pos:pos + length] = out[src:src + length]
                    else:
                        pattern = bytes(out[src:pos])
                        out[pos:pos + length] = (pattern * (length // offset + 1))[:length]
                    pos += length
            self.block_left -= pos - start
            if self.block_left < 0:
                raise XexError("a match ran past its block")
        self.pos = pos


# --- XEX2 ---------------------------------------------------------------------

OPTIONAL_HEADERS = {
    0x000003FF: "file_format_info", 0x00010100: "entry_point", 0x00010201: "image_base",
    0x000103FF: "import_libraries", 0x000183FF: "original_pe_name", 0x000200FF: "static_libraries",
    0x00020104: "tls_info", 0x00020200: "default_stack_size", 0x00030000: "system_flags",
    0x00040006: "execution_id", 0x00040310: "game_ratings",
}
KIND = {0: "slot", 1: "thunk"}


class Xex:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.raw = f.read()
        raw = self.raw
        if raw[:4] != b"XEX2":
            raise XexError("not an XEX2 file")
        self.module_flags, self.pe_offset, _, self.sec_offset, count = struct.unpack_from(">5I", raw, 4)
        self.headers = dict(struct.unpack_from(">II", raw, 0x18 + i * 8) for i in range(count))

        info = self.headers.get(0x3FF)
        if info is None:
            raise XexError("no file format info")
        _, self.encryption, self.compression = struct.unpack_from(">IHH", raw, info)
        if self.compression == 2:
            self.window_size, self.first_size = struct.unpack_from(">II", raw, info + 8)
            self.first_hash = raw[info + 16:info + 36]

        s = self.sec_offset
        self.image_size = struct.unpack_from(">I", raw, s + 4)[0]
        self.image_flags, self.load_address = struct.unpack_from(">II", raw, s + 0x10C)
        self.media_id = raw[s + 0x140:s + 0x150]
        self.file_key = raw[s + 0x150:s + 0x160]
        self.region, self.media_types = struct.unpack_from(">II", raw, s + 0x178)
        npages = struct.unpack_from(">I", raw, s + 0x180)[0]
        self.pages = [struct.unpack_from(">I", raw, s + 0x184 + i * 24)[0] for i in range(npages)]
        self.page_size = 0x1000 if self.image_flags & 2 else 0x10000
        self.entry_point = self.headers.get(0x10100, 0)

    def header_data(self, key):
        value = self.headers.get(key)
        if value is None:
            return None
        if key & 0xFF == 0xFF:
            size = struct.unpack_from(">I", self.raw, value)[0]
            return self.raw[value:value + size]
        return self.raw[value:value + (key & 0xFF) * 4]

    def pe_name(self):
        data = self.header_data(0x183FF)
        return data[4:].split(b"\0")[0].decode("latin1") if data else None

    def import_libraries(self):
        data = self.header_data(0x103FF)
        if not data:
            return []
        _, names_size, count = struct.unpack_from(">III", data, 0)
        names = [n.decode("latin1") for n in data[12:12 + names_size].split(b"\0") if n]
        libraries = []
        off = 12 + names_size
        for _ in range(count):
            size = struct.unpack_from(">I", data, off)[0]
            index, n = struct.unpack_from(">HH", data, off + 0x24)
            libraries.append({"name": names[index], "records": list(struct.unpack_from(">%dI" % n, data, off + 0x28))})
            off += size
        return libraries

    def decrypt(self):
        payload = self.raw[self.pe_offset:]
        if self.encryption == 0:
            return payload, "none"
        if self.compression != 2:
            raise XexError("only the normal LZX compression is handled")
        for name, key in (("retail", RETAIL_KEY), ("devkit", DEVKIT_KEY)):
            cipher = Aes128(Aes128(key).decrypt_block(self.file_key))
            first = cipher.decrypt_cbc(payload[:self.first_size])
            if hashlib.sha1(first).digest() == self.first_hash:
                return cipher.decrypt_cbc(payload), name
        raise XexError("no known key decrypts the first block")

    def decompress(self, payload, progress=None):
        """Walk the block chain; each block starts with the size and SHA-1 of the next one."""
        if self.compression != 2:
            raise XexError("only the normal LZX compression is handled")
        window_bits = self.window_size.bit_length() - 1
        decoder = LzxDecoder(window_bits, self.image_size)
        size, digest = self.first_size, self.first_hash
        at = blocks = chunks = bad = 0
        while size:
            block = payload[at:at + size]
            if len(block) != size:
                raise XexError("block %d runs past the end of the file" % blocks)
            if hashlib.sha1(block).digest() != digest:
                bad += 1
            next_size = struct.unpack_from(">I", block, 0)[0]
            next_digest = block[4:24]
            q = 24
            while q + 2 <= len(block):
                n = (block[q] << 8) | block[q + 1]
                q += 2
                if n == 0:
                    break
                chunk = block[q:q + n]
                if len(chunk) != n:
                    raise XexError("chunk runs past its block")
                decoder.decode_frame(chunk, min(FRAME_SIZE, self.image_size - decoder.pos))
                chunks += 1
                q += n
            at += size
            blocks += 1
            size, digest = next_size, next_digest
            if progress:
                progress(decoder.pos, self.image_size)
        if decoder.pos != self.image_size:
            raise XexError("decoded %d bytes, expected %d" % (decoder.pos, self.image_size))
        return bytes(decoder.out), {"blocks": blocks, "chunks": chunks, "block_hash_failures": bad}

    def page_runs(self):
        runs = []
        for info in self.pages:
            kind, count = info & 0xF, info >> 4
            if runs and runs[-1][0] == kind:
                runs[-1][1] += count
            else:
                runs.append([kind, count])
        return runs


# --- checks on the unpacked image ---------------------------------------------

def parse_pe(image):
    if image[:2] != b"MZ":
        return {"error": "no DOS header"}
    lfanew = struct.unpack_from("<I", image, 0x3C)[0]
    if image[lfanew:lfanew + 4] != b"PE\0\0":
        return {"error": "no PE header"}
    machine, count, _, _, _, opt_size = struct.unpack_from("<HHIIIH", image, lfanew + 4)
    opt = lfanew + 24
    entry, = struct.unpack_from("<I", image, opt + 16)
    image_base, = struct.unpack_from("<I", image, opt + 28)
    sections = []
    at = opt + opt_size
    for _ in range(count):
        name = image[at:at + 8].split(b"\0")[0].decode("latin1")
        vsize, vaddr = struct.unpack_from("<II", image, at + 8)
        flags = struct.unpack_from("<I", image, at + 36)[0]
        sections.append({"name": name, "rva": vaddr, "size": vsize, "execute": bool(flags & 0x20000000),
                         "write": bool(flags & 0x80000000)})
        at += 40
    return {"machine": "0x%04X" % machine, "image_base": "0x%08X" % image_base, "entry_rva": entry,
            "sections": sections}


def check_page_types(xex, pe):
    """Page types are 1 code, 2 data, 3 read-only; each section's pages should carry the matching one."""
    kinds = []
    for info in xex.pages:
        kinds.extend([info & 0xF] * (info >> 4))
    checked = bad = 0
    for sec in pe.get("sections", []):
        want = 1 if sec["execute"] else 2 if sec["write"] else 3
        first = sec["rva"] // xex.page_size
        last = (sec["rva"] + max(sec["size"], 1) - 1) // xex.page_size
        for page in range(first, min(last, len(kinds) - 1) + 1):
            checked += 1
            if kinds[page] != want:
                # a page shared with the neighbouring section may carry its type
                shared = any(o is not sec and o["rva"] // xex.page_size <= page <= (o["rva"] + max(o["size"], 1) - 1)
                             // xex.page_size and kinds[page] == (1 if o["execute"] else 2 if o["write"] else 3)
                             for o in pe["sections"])
                if not shared:
                    bad += 1
    return {"checked": checked, "mismatched": bad}


def read_function_table(image, pe, base):
    """The .pdata section: 8-byte entries of begin address and flags (length in words in bits 8..29)."""
    sec = next((s for s in pe.get("sections", []) if s["name"] == ".pdata"), None)
    if sec is None:
        return {"present": False}, []
    code = [(s["rva"], s["rva"] + s["size"]) for s in pe["sections"] if s["execute"]]
    functions = []
    padding = outside = unordered = 0
    previous = ends = measured = 0
    for i in range(sec["size"] // 8):
        begin, flags = struct.unpack_from(">II", image, sec["rva"] + i * 8)
        if begin == 0 and flags == 0:
            padding += 1
            continue
        rva = begin - base
        length = ((flags >> 8) & 0x3FFFFF) * 4
        if not any(lo <= rva < hi for lo, hi in code):
            outside += 1
            continue
        if begin <= previous:
            unordered += 1
        previous = begin
        functions.append((begin, length, flags & 0xFF))
        if length >= 4 and rva + length <= len(image):
            measured += 1
            last = struct.unpack_from(">I", image, rva + length - 4)[0]
            if last in (0x4E800020, 0x4E800420) or ((last >> 26) == 18 and not last & 1):
                ends += 1
    stats = {"present": True, "entries": sec["size"] // 8, "padding": padding, "outside_code": outside,
             "unordered": unordered, "functions": len(functions), "measured": measured,
             "end_in_return_or_branch": ends, "ratio": round(ends / measured, 4) if measured else 0.0}
    return stats, functions


def read_imports(image, libraries, base):
    """Each record holds kind (0 slot, 1 thunk), library index and ordinal before the loader patches it."""
    rows = []
    for lib in libraries:
        for addr in lib["records"]:
            value = struct.unpack_from(">I", image, addr - base)[0]
            rows.append((addr, KIND.get(value >> 24, "kind%d" % (value >> 24)), lib["name"], value & 0xFFFF))
    return sorted(rows)


def self_test():
    key = bytes(range(16))
    cipher = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    assert Aes128(key).decrypt_block(cipher) == plain, "AES self test failed"


# --- command line -------------------------------------------------------------

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else None
    self_test()
    started = time.time()

    xex = Xex(argv[0])
    print("module     %s, image %d bytes at 0x%08X, entry 0x%08X" %
          (xex.pe_name(), xex.image_size, xex.load_address, xex.entry_point))
    payload, key = xex.decrypt()
    print("decrypted  %d bytes, %s key" % (len(payload), key))

    last = [started]

    def progress(done, total):
        if time.time() - last[0] > 10:
            last[0] = time.time()
            print("  %5.1f%%" % (100.0 * done / total), flush=True)

    image, stats = xex.decompress(payload, progress)
    print("unpacked   %d bytes, %d blocks, %d chunks, %d block hash failures" %
          (len(image), stats["blocks"], stats["chunks"], stats["block_hash_failures"]))

    pe = parse_pe(image)
    for sec in pe.get("sections", []):
        print("  %-9s rva 0x%08X size 0x%07X %s%s" %
              (sec["name"], sec["rva"], sec["size"], "x" if sec["execute"] else "-", "w" if sec["write"] else "-"))
    types = check_page_types(xex, pe)
    print("pages      %d section pages checked, %d with the wrong type" % (types["checked"], types["mismatched"]))
    table, functions = read_function_table(image, pe, xex.load_address)
    if table["present"]:
        print("functions  %d, %.1f%% of %d end in a return or branch, %d outside code, %d out of order" %
              (table["functions"], 100 * table["ratio"], table["measured"], table["outside_code"], table["unordered"]))
    libraries = xex.import_libraries()
    imports = read_imports(image, libraries, xex.load_address) if "error" not in pe else []
    for lib in libraries:
        print("imports    %-14s %d records" % (lib["name"], len(lib["records"])))

    ok = (stats["block_hash_failures"] == 0 and "error" not in pe and types["mismatched"] == 0 and
          table["present"] and table["ratio"] >= 0.95 and table["outside_code"] == 0 and
          table["unordered"] <= 0.001 * max(table["functions"], 1))
    sha256 = hashlib.sha256(image).hexdigest()
    print("sha256     %s" % sha256)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "image.bin"), "wb") as f:
            f.write(image)
        with open(os.path.join(out_dir, "functions.tsv"), "w") as f:
            f.write("address\tsize\tprolog\n")
            for begin, length, prolog in functions:
                f.write("%08X\t%d\t%d\n" % (begin, length, prolog))
        with open(os.path.join(out_dir, "imports.tsv"), "w") as f:
            f.write("address\tkind\tlibrary\tordinal\n")
            for addr, kind, lib, ordinal in imports:
                f.write("%08X\t%s\t%s\t%d\n" % (addr, kind, lib, ordinal))
        info = {
            "pe_name": xex.pe_name(), "load_address": "0x%08X" % xex.load_address,
            "entry_point": "0x%08X" % xex.entry_point, "image_size": xex.image_size,
            "page_size": xex.page_size, "media_id": xex.media_id.hex(), "key": key,
            "headers": {"0x%08X" % k: {"name": OPTIONAL_HEADERS.get(k, ""), "value": "0x%08X" % v}
                        for k, v in sorted(xex.headers.items())},
            "pe": pe,
            "page_runs": [{"type": k, "pages": n} for k, n in xex.page_runs()],
            "imports": {lib["name"]: len(lib["records"]) for lib in libraries},
            "checks": {"blocks": stats["blocks"], "chunks": stats["chunks"],
                       "block_hash_failures": stats["block_hash_failures"], "page_types": types,
                       "function_table": table, "page_digests": "not checked", "passed": ok},
            "sha256": sha256,
        }
        with open(os.path.join(out_dir, "xex_info.json"), "w") as f:
            json.dump(info, f, indent=1)
        print("wrote      %s" % out_dir)
    print("result     %s (%.0f s)" % ("ok" if ok else "FAILED", time.time() - started))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except XexError as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)
