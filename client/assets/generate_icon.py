"""Generate workbay.ico with pure stdlib (no Pillow).

Draws a rust rounded square with an amber 'W' plate stripe, at 16/32/48/
256 px, and packs the images into a single .ico file by hand.
"""

import os
import struct

RUST = (0x2B, 0x62, 0xD9)     # BGR of #d9622b
RUST_DARK = (0x1E, 0x4A, 0xA6)
AMBER = (0x26, 0xA5, 0xE0)    # BGR of #e0a526
DARK = (0x1A, 0x17, 0x15)


def make_image(size):
    """Return (bgra_rows_bottom_up, and_mask) for one icon size."""
    pixels = [[(0, 0, 0, 0)] * size for _ in range(size)]
    radius = max(2, size // 6)
    for y in range(size):
        for x in range(size):
            # rounded-rect membership
            inside = True
            for cx, cy in ((radius, radius), (size - 1 - radius, radius),
                           (radius, size - 1 - radius),
                           (size - 1 - radius, size - 1 - radius)):
                if ((x < radius and y < radius and (cx, cy) == (radius, radius))
                        or (x >= size - radius and y < radius
                            and cx == size - 1 - radius and cy == radius)
                        or (x < radius and y >= size - radius
                            and cx == radius and cy == size - 1 - radius)
                        or (x >= size - radius and y >= size - radius
                            and cx == size - 1 - radius
                            and cy == size - 1 - radius)):
                    if (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                        inside = False
            if not inside:
                continue
            shade = RUST if y < size * 0.55 else RUST_DARK
            pixels[y][x] = (*shade, 255)

    # amber plate stripe with a dark W
    top = int(size * 0.40)
    bottom = int(size * 0.72)
    margin = max(2, size // 8)
    for y in range(top, bottom):
        for x in range(margin, size - margin):
            if pixels[y][x][3]:
                pixels[y][x] = (*AMBER, 255)
    # simple W strokes
    height = bottom - top
    if height >= 4:
        for step in range(height):
            y = top + step
            frac = step / max(1, height - 1)
            span = size - 2 * margin
            for anchor in (0.15, 0.5, 0.85):
                x = int(margin + span * (anchor - 0.12 + 0.24 * frac)) \
                    if anchor != 0.5 else \
                    int(margin + span * (anchor + 0.12 - 0.24 * frac))
                for dx in range(max(1, size // 24)):
                    px = x + dx
                    if margin <= px < size - margin and pixels[y][px][3]:
                        pixels[y][px] = (*DARK, 255)

    row_bytes = b""
    for y in range(size - 1, -1, -1):  # BMP rows are bottom-up
        for x in range(size):
            b_, g_, r_, a_ = pixels[y][x]
            row_bytes += struct.pack("<4B", b_, g_, r_, a_)

    mask_row_len = ((size + 31) // 32) * 4
    mask = b""
    for y in range(size - 1, -1, -1):
        bits = bytearray(mask_row_len)
        for x in range(size):
            if pixels[y][x][3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bytes(bits)
    return row_bytes, mask


def build_ico(path, sizes=(16, 32, 48, 256)):
    entries = []
    blobs = []
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        xor, mask = make_image(size)
        header = struct.pack(
            "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
            len(xor) + len(mask), 0, 0, 0, 0,
        )
        blob = header + xor + mask
        entries.append(struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0, size if size < 256 else 0,
            0, 0, 1, 32, len(blob), offset,
        ))
        blobs.append(blob)
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(sizes)))
        for entry in entries:
            f.write(entry)
        for blob in blobs:
            f.write(blob)


if __name__ == "__main__":
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "workbay.ico")
    build_ico(target)
    print("Wrote", target)
