"""Read-only Terraria 1.4.4 world header fields used to describe evaluation fixtures."""
from pathlib import Path
import struct

MIN_VERSION = 279  # Terraria 1.4.4.9; earlier layouts omit fields read below.


class _Reader:
    def __init__(self, data, offset=0):
        self.data, self.offset = data, offset

    def take(self, fmt):
        values = struct.unpack_from("<" + fmt, self.data, self.offset)
        self.offset += struct.calcsize("<" + fmt)
        return values if len(values) > 1 else values[0]

    def string(self):
        length = shift = 0
        while True:
            byte = self.take("B")
            length |= (byte & 0x7F) << shift
            shift += 7
            if byte < 0x80:
                break
        text = self.data[self.offset:self.offset + length].decode("utf-8")
        self.offset += length
        return text


def read_header(path):
    data = Path(path).read_bytes()
    r = _Reader(data)
    version = r.take("i")
    if data[4:11] != b"relogic" or version < MIN_VERSION:
        raise ValueError(f"unsupported world file (version {version})")
    r.offset = 11 + 1 + 4 + 8  # magic, file type, revision, favorites
    sections = r.take("h")
    header_at = r.take("i")
    r.offset = header_at
    name, seed = r.string(), r.string()
    r.take("Q"); r.offset += 16  # world-gen version, GUID
    world_id = r.take("i")
    r.take("4i")  # world bounds in pixels
    height, width = r.take("2i")
    game_mode = r.take("i")
    special = dict(zip(("drunk", "get_good", "tenth_anniversary", "dont_starve", "not_the_bees",
                        "remix", "no_traps", "zenith"), r.take("8?")))
    r.take("q"); r.take("B")  # creation time, moon type
    r.take("3i"); r.take("4i"); r.take("3i"); r.take("4i")  # tree/cave background splits and styles
    r.take("3i")  # ice, jungle, hell background styles
    spawn_x, spawn_y = r.take("2i")
    surface, rock = r.take("2d")
    r.take("d"); r.take("?"); r.take("i"); r.take("?"); r.take("?")  # time, day, moon phase, blood moon, eclipse
    r.take("2i")  # dungeon position
    crimson = r.take("?")
    return {"file_version": version, "sections": sections, "name": name, "seed": seed, "world_id": world_id,
            "width_tiles": width, "height_tiles": height, "game_mode": game_mode,
            "special_seed_flags": [k for k, v in special.items() if v],
            "spawn_tile": [spawn_x, spawn_y], "surface_tile": surface, "rock_layer_tile": rock,
            "evil": "crimson" if crimson else "corruption"}
