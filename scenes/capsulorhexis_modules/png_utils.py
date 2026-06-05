import math
import struct
import zlib

from .math_utils import clamp, clamp01, mix

def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_png(path, width, height, pixel_fn, channels=4):
    if width < 1 or height < 1:
        raise ValueError(f"PNG dimensions must be positive, got {width}x{height}")
    color_type = 6 if channels == 4 else 2
    rows = []
    x_scale = max(1, width - 1)
    y_scale = max(1, height - 1)
    for y in range(height):
        row = bytearray()
        for x in range(width):
            pixel = pixel_fn(x / x_scale, y / y_scale)
            for channel in pixel[:channels]:
                row.append(int(clamp01(channel) * 255.0 + 0.5))
        rows.append(b"\x00" + bytes(row))

    payload = b"".join(rows)
    encoded = zlib.compress(payload, 9)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
        + png_chunk(b"IDAT", encoded)
        + png_chunk(b"IEND", b"")
    )
    with open(path, "wb") as handle:
        handle.write(png)


def radial_uv(u, v):
    x = u * 2.0 - 1.0
    y = v * 2.0 - 1.0
    radius = math.sqrt(x * x + y * y)
    angle = math.atan2(y, x)
    return x, y, radius, angle


def paeth_predictor(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgba(path):
    with open(path, "rb") as handle:
        data = handle.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG file: {path}")

    offset = 8
    width = height = bit_depth = color_type = None
    compressed = []

    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length

        if kind == b"IHDR":
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or compression != 0 or filtering != 0 or interlace != 0:
                raise ValueError(f"Unsupported PNG encoding: {path}")
            if color_type not in (2, 6):
                raise ValueError(f"Unsupported PNG color type {color_type}: {path}")
        elif kind == b"IDAT":
            compressed.append(payload)
        elif kind == b"IEND":
            break

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(b"".join(compressed))
    rows = []
    previous = bytearray(stride)
    source = 0

    for _row_index in range(height):
        filter_type = raw[source]
        source += 1
        current = bytearray(raw[source : source + stride])
        source += stride

        for index, value in enumerate(current):
            left = current[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                current[index] = (value + left) & 0xFF
            elif filter_type == 2:
                current[index] = (value + up) & 0xFF
            elif filter_type == 3:
                current[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                current[index] = (value + paeth_predictor(left, up, upper_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"Unsupported PNG filter {filter_type}: {path}")

        rows.append(current)
        previous = current

    pixels = []
    for row in rows:
        rgba_row = []
        for x in range(width):
            base = x * channels
            if channels == 4:
                rgba_row.append((row[base], row[base + 1], row[base + 2], row[base + 3]))
            else:
                rgba_row.append((row[base], row[base + 1], row[base + 2], 255))
        pixels.append(rgba_row)

    return {"width": width, "height": height, "pixels": pixels}


def sample_png(image, x, y):
    width = image["width"]
    height = image["height"]
    x = clamp(x, 0.0, width - 1.0)
    y = clamp(y, 0.0, height - 1.0)
    x0 = int(math.floor(x))
    y0 = int(math.floor(y))
    x1 = min(width - 1, x0 + 1)
    y1 = min(height - 1, y0 + 1)
    tx = x - x0
    ty = y - y0

    def mix_pixel(a, b, t):
        return tuple(mix(a[index], b[index], t) for index in range(4))

    top = mix_pixel(image["pixels"][y0][x0], image["pixels"][y0][x1], tx)
    bottom = mix_pixel(image["pixels"][y1][x0], image["pixels"][y1][x1], tx)
    return [channel / 255.0 for channel in mix_pixel(top, bottom, ty)]
