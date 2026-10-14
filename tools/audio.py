"""Extract the game's music and sound effects as Ogg Vorbis files.

    python tools/audio.py [--game DIR] [--out DIR] [--only music|sounds|voices]

The HD port keeps the soundtrack in CUSTOM/MUSIC.ARC and the sound effects in CUSTOM/SOUNDS.ARC (see arc.py); the
members are plain Ogg Vorbis. They are written to assets/audio/music and assets/audio/sounds, and assets/audio.json
lists each with its length in seconds.

The first five members of E_SND_SE.AFS are Ogg streams the game loads into its streaming voices (voice 0 is what the
title screen plays when START is pressed); they are written to assets/audio/voices/voice_<n>.ogg.
"""
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import arc


def seconds(data):
    """Length of an Ogg Vorbis stream from its sample rate and the last page's granule position."""
    start = data.find(b"\x01vorbis")
    if start < 0:
        return 0.0
    rate = struct.unpack_from("<I", data, start + 12)[0]
    last = data.rfind(b"OggS")
    if last < 0 or rate == 0:
        return 0.0
    granule = struct.unpack_from("<q", data, last + 6)[0]
    return granule / rate if granule > 0 else 0.0


def export(path, out_dir, label):
    container = arc.Container(path)
    os.makedirs(out_dir, exist_ok=True)
    listing = []
    for i, (name, _, size) in enumerate(container.entries):
        data = container.read(i)
        file_name = os.path.basename(name.replace("\\", "/")).lower()
        if "/" in name:
            # sound effects are filed by folder; keep the folder in the name so equal names do not collide
            file_name = name.replace("\\", "/").lower().split("/", 1)[1].replace("/", "_")
        with open(os.path.join(out_dir, file_name), "wb") as f:
            f.write(data)
        listing.append({"name": file_name, "source": name, "seconds": round(seconds(data), 2), "bytes": size})
    return listing


def export_voices(game, out_dir):
    path = os.path.join(game, "DATA_BE", "JETRADIO", "E_SND_SE.AFS")
    if not os.path.exists(path):
        return []
    archive = afs.Archive(path)
    os.makedirs(out_dir, exist_ok=True)
    listing = []
    for i in range(5):
        data = archive.read(i)
        if data[:4] != b"OggS":
            continue
        name = "voice_%d.ogg" % i
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(data)
        listing.append({"name": name, "source": "E_SND_SE.AFS #%d" % i, "seconds": round(seconds(data), 2), "bytes": len(data)})
    return listing


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    out = argv[argv.index("--out") + 1] if "--out" in argv else "assets"
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    result = {}
    jobs = (("music", "MUSIC.ARC"), ("sounds", "SOUNDS.ARC"))
    for kind, archive in jobs:
        if only and only != kind:
            continue
        path = os.path.join(game, "CUSTOM", archive)
        if not os.path.exists(path):
            continue
        listing = export(path, os.path.join(out, "audio", kind), kind)
        result[kind] = listing
        print("%s: %d files, %.0f minutes" % (kind, len(listing), sum(e["seconds"] for e in listing) / 60.0))
    if not only or only == "voices":
        voices = export_voices(game, os.path.join(out, "audio", "voices"))
        if voices:
            result["voices"] = voices
            print("voices: %d files" % len(voices))
    if "music" in result:
        # the radio mixes of the songs (names ending in _R or _R1 ...), for the stages
        names = [e["name"] for e in result["music"]]
        result["playlist"] = [n for n in names if re.match(r"^[a-z]+_r[0-9]?\.ogg$", n)]
    if result:
        existing = {}
        index = os.path.join(out, "audio.json")
        if only and os.path.exists(index):
            with open(index) as f:
                existing = json.load(f)
        existing.update(result)
        with open(index, "w") as f:
            json.dump(existing, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
