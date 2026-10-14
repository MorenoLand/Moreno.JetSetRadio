"""Copy the loose pictures and videos of the PC release into assets/.

    python tools/pcdata.py PC_DIR [--out DIR]

PC_DIR is the folder of the PC release (the one with CUSTOM and DATA). The pictures of CUSTOM/IMAGES.ARC (the
legal screens, the logos, the menu and the in-game display art) are written to assets/images/ under their own names
(the console folders PS3/ and PSVITA/ are left out), the videos of DATA/VIDEOS to assets/videos/, and
assets/images.json lists the pictures with their sizes.
"""
import json
import os
import shutil
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arc


def png_size(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


LANGUAGES = ["en", "es", "jp", "it", "fr", "de", "jp2", "jp3"]


def read_strings(path):
    """CUSTOM/STRINGS.STR: u16 languages, u16 strings, then per string 20 bytes (a big endian 24 bit offset, a pad byte, eight u16 lengths in
    characters with the terminator, one per language); the text is UTF-16LE, a language after the other, starting one
    byte after the offset."""
    d = open(path, "rb").read()
    langs, count = struct.unpack_from("<HH", d, 0)
    out = []
    for i in range(count):
        o = 4 + 20 * i
        offset = int.from_bytes(d[o:o + 3], "big") + 1
        lens = struct.unpack_from("<%dH" % langs, d, o + 4)
        texts = []
        p = offset
        for n in lens:
            texts.append(d[p:p + 2 * n].decode("utf-16le", errors="replace").rstrip("\0"))
            p += 2 * n
        out.append(texts)
    return out


def notice(pc, images):
    """The notice about graffiti (picture of the crossed out figures and the text) cut out of the English logo pack of the
    original console game, member 3, second texture of U_SEGALOGO.AFS, a 1024 x 1024 sheet with the notice at the top
    left. Written as images/notice.png."""
    path = os.path.join(pc, "DATA", "JETRADIO", "U_SEGALOGO.AFS")
    if not os.path.exists(path):
        return False
    import afs
    import pvr
    data = afs.Archive(path).read(3)
    found = list(pvr.locate(data))
    if len(found) < 2:
        return False
    _, gbix, pvrt, end = found[1]
    pixel, fmt = data[pvrt + 8], data[pvrt + 9]
    w = int.from_bytes(data[pvrt + 12:pvrt + 14], "little")
    h = int.from_bytes(data[pvrt + 14:pvrt + 16], "little")
    rgba = pvr.decode(pixel, fmt, w, h, data[pvrt + 16:end])
    x0, y0, x1, y1 = 8, 8, 632, 456
    out = bytearray()
    for y in range(y0, y1):
        out += rgba[(y * w + x0) * 4:(y * w + x1) * 4]
    pvr.write_png(os.path.join(images, "notice.png"), x1 - x0, y1 - y0, bytes(out))
    return True


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    pc = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    images = os.path.join(out, "images")
    os.makedirs(images, exist_ok=True)
    c = arc.Container(os.path.join(pc, "CUSTOM", "IMAGES.ARC"))
    listing = {}
    for i, (name, offset, size) in enumerate(c.entries):
        if "/" in name and name.split("/")[0] in ("PS3", "PSVITA", "ANDROID"):
            continue
        if name.startswith("JAP_INSTRUCTIONS"):
            continue
        data = c.read(i)
        path = os.path.join(images, name.replace("/", "_"))
        with open(path, "wb") as f:
            f.write(data)
        listing[name] = {"file": "images/" + name.replace("/", "_"), "size": png_size(data)}
    with open(os.path.join(out, "images.json"), "w") as f:
        json.dump(listing, f, indent=1)
    notice(pc, images)
    strings = read_strings(os.path.join(pc, "CUSTOM", "STRINGS.STR"))
    with open(os.path.join(out, "strings.json"), "w", encoding="utf-8") as f:
        json.dump({"languages": LANGUAGES, "strings": strings}, f, ensure_ascii=False)
    videos = os.path.join(pc, "DATA", "VIDEOS")
    if os.path.isdir(videos):
        dest = os.path.join(out, "videos")
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(videos):
            shutil.copyfile(os.path.join(videos, name), os.path.join(dest, name))
    print("%d pictures, %d videos" % (len(listing), len(os.listdir(os.path.join(out, "videos"))) if os.path.isdir(os.path.join(out, "videos")) else 0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
