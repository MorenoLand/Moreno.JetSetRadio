"""Read the one-shot sound banks (`SOSB`) of SND_SE.AFS and write their sounds as WAV files.

    python tools/sosb.py [--game DIR] [--archive SND_SE.AFS] [--member N] [--out DIR]
    python tools/sosb.py --export [--game DIR] [--exe DIR] [--out DIR]

A bank is little endian and starts with

    char[4]  "SOSB"
    u32      version (2)
    u32      size
    u32      count
    u32[count]   offset of each sound's record (from the start of the bank)

and a record holds, besides other fields,

    +0x04  u16  bits 0-2 high bits of the sample offset, bits 7-8 format (0 16-bit, 1 8-bit, 2 4-bit ADPCM),
                bit 9 looping
    +0x06  u16  low 16 bits of the sample offset
    +0x08  u16  loop start (samples)
    +0x0A  u16  loop end
    +0x10  u16  pitch: bits 0-9 fraction, bits 11-14 octave (bit 14 set: below the base rate of 44100)
    +0x17  u8   level, low four bits, 3 dB steps below full
    +0x34  u16  length in samples

The ADPCM is the usual 4-bit kind of the sound chip of the original machine: low nibble first, a step that
starts at 127 and is multiplied by 230 230 230 230 307 409 512 614 over 256 after each nibble.

`--export` writes the common bank and the banks of the characters to assets/audio/sfx/ (identical sounds once)
and assets/audio/sfx.json. The executable has a table of 78 pointers at 0x82D79938, one per sound list, in the
order the game numbers them: list 0 is the common bank, the first bank of each character (16 sounds, loaded
as bank 1) and the second one (15 sounds, bank 2) follow. Sounds 0 to 9 and 14 are the same in all of them.
"""
import os
import struct
import sys
import wave

DIFF = (1, 3, 5, 7, 9, 11, 13, 15, -1, -3, -5, -7, -9, -11, -13, -15)
STEP = (230, 230, 230, 230, 307, 409, 512, 614)


def decode_adpcm(data, samples):
    pred = 0
    step = 0x7F
    out = []
    for byte in data[:(samples + 1) // 2]:
        for nibble in (byte & 0xF, byte >> 4):
            x = DIFF[nibble] * step
            pred += int(x / 8)
            pred = max(-0x8000, min(0x7FFF, pred))
            step = max(0x7F, min(0x6000, (STEP[nibble & 7] * step) >> 8))
            out.append(pred)
    return out[:samples]


def sample_rate(pitch):
    octave = (pitch >> 11) & 0xF
    value = ((pitch & 0x3FF) | 0x400) * 44100
    if octave & 8:
        value >>= 16 - octave
    else:
        value <<= octave
    return value >> 10


class Sound:
    def __init__(self, index, flags, offset, loop_start, loop_end, pitch, level, length, pcm):
        self.index = index
        self.format = (flags >> 7) & 3
        self.looping = bool(flags & 0x200)
        self.offset = offset
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.rate = sample_rate(pitch)
        self.level = level
        self.length = length
        self.pcm = pcm


def read_bank(data):
    """The sounds of a bank as a list of Sound."""
    if data[:4] != b"SOSB":
        raise ValueError("not a sound bank")
    count = struct.unpack_from("<I", data, 12)[0]
    sounds = []
    for i in range(count):
        rec = struct.unpack_from("<I", data, 16 + 4 * i)[0]
        flags, low, loop_start, loop_end = struct.unpack_from("<4H", data, rec + 4)
        pitch = struct.unpack_from("<H", data, rec + 0x10)[0]
        level = data[rec + 0x17] & 0xF
        length = struct.unpack_from("<H", data, rec + 0x34)[0]
        offset = ((flags & 7) << 16) + low
        fmt = (flags >> 7) & 3
        if fmt == 0:
            raw = data[offset:offset + 2 * length]
            pcm = list(struct.unpack("<%dh" % (len(raw) // 2), raw))
        elif fmt == 1:
            pcm = [(b - 256 if b > 127 else b) << 8 for b in data[offset:offset + length]]
        elif fmt == 2:
            pcm = decode_adpcm(data[offset:offset + (length + 1) // 2], length)
        else:
            pcm = []
        sounds.append(Sound(i, flags, offset, loop_start, loop_end, pitch, level, length, pcm))
    return sounds


def write_wav(path, sound):
    gain = 10.0 ** (-3.0 * (15 - sound.level) / 20.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(max(sound.rate, 1000))
        w.writeframes(struct.pack("<%dh" % len(sound.pcm), *[int(max(-32768, min(32767, v * gain))) for v in sound.pcm]))


LIST_TABLE = 0x82D79938
LISTS = 78


def export(game, exe, out_dir, archive="E_SND_SE.AFS"):
    import hashlib
    import json
    import afs
    import manifest
    img = manifest.Image(os.path.join(exe, "image.bin"))
    by_address = dict(manifest.read_load_lists(img))
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", archive))
    # the sound list numbers: 0 is the common bank; the first banks of the characters (flag 1) and the second
    # ones (flag 2) follow in the order of the characters; the other lists (members above 35) are for areas
    first, second = [], []
    common = None
    for k in range(LISTS):
        records = by_address.get(img.u32(LIST_TABLE + 4 * k), [])
        sosb = [r for r in records if manifest.tag_text(r[6]) == "SOSB"]
        if not sosb:
            continue
        member, bank = sosb[0][1], sosb[0][7] >> 24
        if k == 0:
            common = member
        elif 6 <= member <= 35 and bank == 1:
            first.append(member)
        elif 6 <= member <= 35 and bank == 2:
            second.append(member)
    characters = [{"voice": a, "effects": b} for a, b in zip(first, second)]
    members = sorted({common} | {m for c in characters for m in c.values()})
    os.makedirs(os.path.join(out_dir, "audio", "sfx"), exist_ok=True)
    files = {}
    listing = {}
    for member in members:
        sounds = read_bank(arc.read(member))
        for s in sounds:
            if s.length <= 8 or not s.pcm:
                continue
            key = hashlib.sha1(struct.pack("<%dh" % len(s.pcm), *s.pcm) + struct.pack("<I", s.rate)).hexdigest()[:10]
            name = "sfx_%s.wav" % key
            if name not in files:
                files[name] = {"file": name, "seconds": round(s.length / max(s.rate, 1), 2), "looping": s.looping,
                               "uses": []}
                write_wav(os.path.join(out_dir, "audio", "sfx", name), s)
            files[name]["uses"].append([member, s.index])
    result = {"archive": archive, "common": common, "characters": characters, "sounds": list(files.values())}
    with open(os.path.join(out_dir, "audio", "sfx.json"), "w") as f:
        json.dump(result, f, indent=1)
    return len(files), len(members)


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    if "--export" in argv:
        game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
        exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
        out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        files, banks = export(game, exe, out)
        print("%d sounds from %d banks -> %s" % (files, banks, os.path.join(out, "audio", "sfx")))
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    name = argv[argv.index("--archive") + 1] if "--archive" in argv else "SND_SE.AFS"
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    only = int(argv[argv.index("--member") + 1]) if "--member" in argv else None
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import afs
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", name))
    for member in range(len(arc)):
        if only is not None and member != only:
            continue
        data = arc.read(member)
        if data[:4] != b"SOSB":
            continue
        sounds = read_bank(data)
        print("member %d: %d sounds" % (member, len(sounds)))
        for s in sounds:
            print("   %2d  format %d  %5d samples  %5d Hz  %5.2f s  loop %s %d..%d  level %d" %
                  (s.index, s.format, s.length, s.rate, s.length / max(s.rate, 1), "yes" if s.looping else "no ",
                   s.loop_start, s.loop_end, s.level))
            if out:
                os.makedirs(os.path.join(out, "%02d" % member), exist_ok=True)
                write_wav(os.path.join(out, "%02d" % member, "%02d.wav" % s.index), s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
