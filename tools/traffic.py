"""Read the moving traffic of a stage.

    python tools/traffic.py [--game build/xbla] [--exe build/exe]

Vehicles that drive are not placed by sector records (those are parked, see mission.py). A mission script (MISSIONDATA
`JMDc`, pointer at +0x5C, records of 8 words) has the command 9, which the executable answers with `FUN_8238D6C8`
(stage 1) and the task class `FUN_82378BB8`; its update is `FUN_823786F8`:

    word 0  9
    word 2  vehicle type, 0 to 8 (models `0x82D7D27C`, lists `0x82D7D72C`)
    word 3  route, an index into the table at `0x82D7EBA0` of motions
    word 4  where on the route it starts, in ten thousandths of its frames
    word 5  speed in percent: that many hundredths of a frame of the route per update
    word 7  filled in by the game with the task

A route is a motion (`{mdata, frames, type, interpolation}`, type 3: position and angle keys of one object); the vehicle
is put where the motion is at its frame and the frame goes on by speed / 100 each update; at the end it starts again.
Keys are 16 bytes: u32 frame and three values (floats for the position, integers of 65536 per turn for the angle).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import afs
import layout

BLOB_BASE = 0x8CB00000
TABLES = {
    # stage: (model table, list table, number of types, route table)
    "1": (0x82D7D27C, 0x82D7D72C, 9, 0x82D7EBA0),
}
MISSION_BASE = 0x8CDE0000


def _dc(p):
    return 0x8C000000 | (p & 0x01FFFFFF) if 0x20000000 <= p < 0x22000000 else p


def read(image, game, stage="1", mission=0):
    if stage not in TABLES:
        return None
    models, lists, count, routes = TABLES[stage]
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    name, member = layout.STAGE_ARCHIVES[stage]
    data = afs.Archive(os.path.join(root, name)).read(member)

    def u(va):
        return struct.unpack_from(">I", image, va - 0x82000000)[0]

    def b(a):
        return struct.unpack_from(">I", data, a - BLOB_BASE)[0]

    def f(a):
        return struct.unpack_from(">f", data, a - BLOB_BASE)[0]

    script = afs.Archive(os.path.join(root, "MISSIONDATA.AFS")).read(mission)
    if script[:4] != b"JMDc":
        return None
    o = struct.unpack_from(">I", script, 0x5C)[0] - MISSION_BASE
    cars = []
    used = set()
    while 0 <= o and o + 32 <= len(script):
        w = struct.unpack_from(">8I", script, o)
        if w[0] == 0:
            break
        if w[0] == 9 and w[2] < count:
            cars.append({"type": w[2], "route": w[3], "phase": w[4] / 10000.0, "speed": w[5] / 100.0})
            used.add(w[3])
        o += 32
    paths = {}
    for k in sorted(used):
        p = _dc(u(routes + 4 * k))
        if not (BLOB_BASE <= p < BLOB_BASE + len(data)):
            continue
        mdata, frames = b(p), b(p + 4)
        pos_keys, ang_keys, n_pos, n_ang = (b(mdata + 4 * j) for j in range(4))
        pos = [[b(pos_keys + 16 * i)] + [f(pos_keys + 16 * i + 4 + 4 * j) for j in range(3)] for i in range(n_pos)]
        ang = [[b(ang_keys + 16 * i)] + [struct.unpack_from(">i", data, ang_keys + 16 * i + 4 + 4 * j - BLOB_BASE)[0]
                                         for j in range(3)] for i in range(n_ang)]
        paths[str(k)] = {"frames": frames, "pos": pos, "ang": ang}
    return {"cars": cars, "paths": paths}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    image = open(os.path.join(exe, "image.bin"), "rb").read()
    info = read(image, game)
    print("%d cars on %d routes" % (len(info["cars"]), len(info["paths"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
