"""Read where mission sets put vehicles.

    python tools/mission.py [--exe build/exe] [--game build/xbla] [--stage 1]

The game keeps its mission data in two archives. MISSIONDATA.AFS holds one script per mission (tag JMDc); its word at
+0x10 names the MISSIONSET.AFS member (tag JMSc) the mission uses. A set is a chain of blocks (next pointer at +0x50);
the pointer at +0x34 of a block leads to a table with one entry per sector of the stage, and each entry to a
null-terminated array of pointers to spawn records:

    word 0      vehicle type (an index into the stage's vehicle tables)
    words 1..3  position (floats)
    words 4..6  rotation (integers, 65536 per turn)
    word 9      filled in by the game with the vehicle it created

Which stage a set belongs to is not stored next to it. A set is given to the stage whose placed objects lie close
to nearly all of its spawn records; sets that fit two stages equally well are left out.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_BASE = 0x8CDE0000
SET_BASE = 0x8CDE6000
IMAGE_BASE = 0x82000000

# Executable tables that turn a vehicle type into a model: (high detail model table, texture list table, entries).
# Every stage has a few more tables behind these (low detail model, a second set); stage 2 uses one model for all.
VEHICLE_TABLES = {
    "1": (0x82D7EBC0, 0x82D7EC50, 18),
    "3": (0x82CD02D8, 0x82CDCC18, 13),
    "5": (0x82C9EA50, 0x82CA5C60, 18),
    "6": (0x82C93A18, 0x82C9CEF0, 18),
}
SINGLE_VEHICLE = {"2": (0x82D7FD64, 0x82D80094)}


def vehicle_model(image, stage, kind):
    """(object address in the host form, list header) for a vehicle type, or None."""
    def u32(a):
        return struct.unpack_from(">I", image, a - IMAGE_BASE)[0]
    if stage in SINGLE_VEHICLE:
        model, lists = SINGLE_VEHICLE[stage]
        return u32(model), u32(lists)
    if stage not in VEHICLE_TABLES:
        return None
    model, lists, count = VEHICLE_TABLES[stage]
    if not 0 <= kind < count:
        return None
    return u32(model + 4 * kind), u32(lists + 4 * kind)


# Executable tables that turn a character type into a model: (model table, list table, entries). The game picks the
# set from the stage; the entries of a character are the objects of the people blob that is loaded with the stage.
PEOPLE_TABLES = {
    "1": (0x82D92A68, 0x82D92B40, 30),
    "2": (0x82D92C30, 0x82D92D10, 56),
    "3": (0x82D92E80, 0x82D92F70, 60),
    "5": (0x82D930D0, 0x82D93118, 18),
    "6": (0x82D930D0, 0x82D93118, 18),
}


def people(image, stage):
    """[(type, object pointer, list pointer)] of the characters of a stage."""
    def u32(a):
        return struct.unpack_from(">I", image, a - IMAGE_BASE)[0]
    if stage not in PEOPLE_TABLES:
        return []
    models, lists, count = PEOPLE_TABLES[stage]
    out = []
    for t in range(count):
        o = u32(models + 4 * t)
        if 0x20000000 <= o < 0x22000000:
            out.append((t, o, u32(lists + 4 * t)))
    return out


class Spawn:
    __slots__ = ("kind", "pos", "rot", "sector", "mission")

    def __init__(self, kind, pos, rot, sector, mission):
        self.kind = kind
        self.pos = pos
        self.rot = rot
        self.sector = sector
        self.mission = mission


def set_of(data):
    """MISSIONSET member named by a mission data member, or None."""
    if data[:4] != b"JMDc":
        return None
    value = struct.unpack_from(">I", data, 0x10)[0]
    return value if value < 0x100 else None


def spawns(data, mission):
    """Spawn records of every block of a set member."""
    n = len(data)
    if data[:4] != b"JMSc":
        return []

    def u(o):
        return struct.unpack_from(">I", data, o)[0]

    def off(p):
        o = p - SET_BASE
        return o if 0 <= o < n else None

    out = []
    o = 0
    seen_blocks = set()
    while o is not None and o not in seen_blocks and len(seen_blocks) < 32:
        seen_blocks.add(o)
        table = off(u(o + 0x34)) if u(o + 0x34) else None
        if table is not None:
            for sector in range(72):
                if table + 4 * sector + 4 > n:
                    break
                w = u(table + 4 * sector)
                a = off(w) if w else None
                if a is None:
                    continue
                count = 0
                while a + 4 <= n and count < 200:
                    e = u(a)
                    if e == 0:
                        break
                    eo = off(e)
                    if eo is None or eo + 40 > n:
                        break
                    kind, = struct.unpack_from(">i", data, eo)
                    pos = struct.unpack_from(">3f", data, eo + 4)
                    rot = struct.unpack_from(">3i", data, eo + 16)
                    out.append(Spawn(kind, pos, rot, sector, mission))
                    a += 4
                    count += 1
        nx = u(o + 0x50)
        o = off(nx) if nx else None
    return out


def _grid(points):
    grid = {}
    for x, z in points:
        grid.setdefault((int(x // 100), int(z // 100)), []).append((x, z))
    return grid


def _near(grid, x, z, radius=100.0):
    cx, cz = int(x // 100), int(z // 100)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for px, pz in grid.get((cx + i, cz + j), ()):
                if (px - x) ** 2 + (pz - z) ** 2 <= radius * radius:
                    return True
    return False


_cache = {}


def assign_sets(image, game):
    """{stage: [(set member, [Spawn, ...])]} from how well the spawn records fit the placed objects of each stage."""
    key = (id(image), game)
    if key in _cache:
        return _cache[key]
    import afs
    import layout
    root = os.path.join(game, "DATA_BE", "JETRADIO")
    grids = {}
    for stage, (name, member) in layout.STAGE_ARCHIVES.items():
        data = afs.Archive(os.path.join(root, name)).read(member)
        grids[stage] = _grid([(p.pos[0], p.pos[2]) for p in layout.read(stage, image, data)])
    sets = afs.Archive(os.path.join(root, "MISSIONSET.AFS"))
    out = {stage: [] for stage in grids}
    for m in range(len(sets.members)):
        found = spawns(sets.read(m), m)
        if not found:
            continue
        scores = sorted(((sum(1 for sp in found if _near(g, sp.pos[0], sp.pos[2])) / len(found), st)
                         for st, g in grids.items()), reverse=True)
        best, stage = scores[0]
        runner = scores[1][0] if len(scores) > 1 else 0.0
        if best >= 0.8 and runner <= best - 0.1:
            out[stage].append((m, found))
    _cache[key] = out
    return out


def stage_spawns(image, stage, game):
    """Distinct vehicle spawn records over the mission sets that belong to a stage."""
    seen = {}
    for _, found in assign_sets(image, game).get(stage, []):
        for sp in found:
            key = (sp.kind, round(sp.pos[0]), round(sp.pos[2]), sp.rot[1])
            seen.setdefault(key, sp)
    return list(seen.values())


def cans(image, game, field=0x38, size=16):
    """{stage: [(x, y, z, kind), ...]} the spray cans of each stage.

    A set block holds a table (+0x38) of sector entries; each entry leads to a null-terminated array of pointers to
    16-byte records `{x, y, z, kind}`. The game creates one pickup task (size 0xD0, `0x82383588`) per record: kind 0
    is the small yellow can, which comes back after a minute, any other kind the larger teal one, which is taken for
    good. Every mission set of a stage has its own cans; the positions of all of them are joined here.
    """
    import afs
    sets = assign_sets(image, game)
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "MISSIONSET.AFS"))
    out = {}
    for stage, items in sets.items():
        found = {}
        for member, _ in items:
            data = arc.read(member)
            n = len(data)
            if data[:4] != b"JMSc":
                continue

            def u(o):
                return struct.unpack_from(">I", data, o)[0]

            def off(p):
                o = p - SET_BASE
                return o if 0 <= o < n else None

            o = 0
            seen_blocks = set()
            while o is not None and o not in seen_blocks and len(seen_blocks) < 32:
                seen_blocks.add(o)
                table = off(u(o + field)) if u(o + field) else None
                for sector in range(72 if table is not None else 0):
                    if table + 4 * sector + 4 > n:
                        break
                    w = u(table + 4 * sector)
                    a = off(w) if w else None
                    if a is None:
                        continue
                    count = 0
                    while a + 4 <= n and count < 200:
                        e = u(a)
                        if e == 0:
                            break
                        eo = off(e)
                        if eo is None or eo + size > n:
                            break
                        x, y, z = struct.unpack_from(">3f", data, eo)
                        kind = u(eo + 12)
                        if max(abs(x), abs(y), abs(z)) < 1e5 and kind < 8:
                            found.setdefault((round(x, 1), round(y, 1), round(z, 1)), kind)
                        a += 4
                        count += 1
                nx = u(o + 0x50)
                o = off(nx) if nx else None
        out[stage] = [(x, y, z, kind) for (x, y, z), kind in sorted(found.items())]
    return out


def start_candidates(image, game):
    """{stage: [(position, look at), ...]} where the missions of a stage begin, the most shared place first.

    A mission data block holds two points: its start position at +0x70 and what the camera looks at, at +0xA4.
    Missions of one stage begin in a few places; places closer than 60 units count as one.
    """
    import afs
    sets = assign_sets(image, game)
    stage_of = {m: st for st, items in sets.items() for m, _ in items}
    data = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "MISSIONDATA.AFS"))
    found = {}
    for member in range(len(data.members)):
        blob = data.read(member)
        off = 0
        seen = set()
        while off is not None and 0 <= off < len(blob) - 0x100 and off not in seen and blob[off:off + 4] == b"JMDc":
            seen.add(off)
            stage = stage_of.get(struct.unpack_from(">I", blob, off + 0x10)[0])
            pos = struct.unpack_from(">3f", blob, off + 0x70)
            look = struct.unpack_from(">3f", blob, off + 0xA4)
            if stage and all(abs(v) < 1e5 for v in pos + look):
                found.setdefault(stage, []).append((pos, look))
            nxt = struct.unpack_from(">I", blob, off + 0xEC)[0]
            off = nxt - DATA_BASE if nxt else None

    def near(a, b):
        return sum((a[i] - b[i]) ** 2 for i in range(3)) <= 60.0 ** 2

    out = {}
    for stage, items in found.items():
        ranked = sorted(range(len(items)), key=lambda i: (-sum(1 for o in items if near(items[i][0], o[0])), i))
        chosen = []
        for i in ranked:
            if not any(near(items[i][0], c[0]) for c in chosen):
                chosen.append(items[i])
        out[stage] = chosen
    return out


def starts(image, game):
    """{stage: (position, look at)}: the place most missions of a stage begin at."""
    return {stage: items[0] for stage, items in start_candidates(image, game).items()}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    exe = argv[argv.index("--exe") + 1] if "--exe" in argv else "build/exe"
    game = argv[argv.index("--game") + 1] if "--game" in argv else "build/xbla"
    wanted = argv[argv.index("--stage") + 1] if "--stage" in argv else None
    image = open(os.path.join(exe, "image.bin"), "rb").read()
    assigned = assign_sets(image, game)
    for stage in ("1", "2", "3", "5", "6"):
        if wanted and stage != wanted:
            continue
        found = stage_spawns(image, stage, game)
        kinds = {}
        for sp in found:
            kinds[sp.kind] = kinds.get(sp.kind, 0) + 1
        print("stage %s: sets %s, %d vehicle spawn points, types %s" %
              (stage, [m for m, _ in assigned[stage]], len(found), dict(sorted(kinds.items()))))
    for stage, (pos, look) in sorted(starts(image, game).items()):
        print("stage %s starts at (%.0f %.0f %.0f) looking at (%.0f %.0f %.0f)" % ((stage,) + tuple(pos) + tuple(look)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


def lane_points(image, game):
    """{stage: [[(x, y, z), ...], ...]} the point lists of the table at +0x1C of the set blocks.

    The table is a run of shape descriptors and points; the points come in chains whose neighbours are close together.
    A point list is read as the floats of the table that follow each other within `LANE_LINK` units.
    """
    import afs
    sets = assign_sets(image, game)
    arc = afs.Archive(os.path.join(game, "DATA_BE", "JETRADIO", "MISSIONSET.AFS"))
    out = {}
    for stage, items in sets.items():
        chains = {}
        for member, _ in items:
            data = arc.read(member)
            n = len(data)
            if data[:4] != b"JMSc":
                continue
            o = 0
            seen = set()
            while o is not None and o not in seen and len(seen) < 32:
                seen.add(o)
                fields = [struct.unpack_from(">I", data, o + k)[0] - SET_BASE for k in (0x10, 0x14, 0x18, 0x1C, 0x24, 0x28, 0x2C, 0x30)]
                start = struct.unpack_from(">I", data, o + 0x1C)[0] - SET_BASE
                if 0 < start < n:
                    later = [v for v in fields if start < v < n]
                    end = min(later) if later else min(n, start + 0x8000)
                    chain = []
                    p = start
                    while p + 12 <= end:
                        x, y, z = struct.unpack_from(">3f", data, p)
                        ok = max(abs(x), abs(z)) < 4000 and -400 < y < 1500 and (abs(x) + abs(z)) > 1.0
                        if ok and (not chain or sum((a - b) ** 2 for a, b in zip((x, y, z), chain[-1])) < 200.0 ** 2):
                            chain.append((x, y, z))
                            p += 12
                            continue
                        if len(chain) >= 3:
                            chains[tuple(chain)] = chain
                        chain = []
                        p += 4
                    if len(chain) >= 3:
                        chains[tuple(chain)] = chain
                nx = struct.unpack_from(">I", data, o + 0x50)[0]
                o = nx - SET_BASE if 0 <= nx - SET_BASE < n else None
        out[stage] = list(chains.values())
    return out
