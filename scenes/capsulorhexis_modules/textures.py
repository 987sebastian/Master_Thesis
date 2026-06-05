import json
import math
import os

from .constants import (
    IMAGE_GENERATED_TEXTURE_FILENAMES,
    IMAGE_GENERATED_TEXTURE_MODE,
    PROCEDURAL_FALLBACK_TEXTURE_FILENAMES,
    REFERENCE_DIR,
    REFERENCE_FRAME_NAMES,
    SIMULATOR_TEXTURE_FILENAMES,
    SIMULATOR_TEXTURE_MODE,
    STABLE_TEXTURE_MODES,
    TEXTURE_DIR,
    TEXTURE_GENERATOR_VERSION,
    TEXTURE_MANIFEST_PATH,
)
from .math_utils import clamp, clamp01, fbm, mix, noise2
from .png_utils import radial_uv, read_png_rgba, sample_png, write_png

def detect_reference_eye(image):
    width = image["width"]
    height = image["height"]
    min_x = width
    min_y = height
    max_x = 0
    max_y = 0

    # Ignore the right-side title card; use the bright circular microscope field.
    for y in range(0, height, 8):
        for x in range(0, int(width * 0.76), 8):
            r, g, b, _a = image["pixels"][y][x]
            if (r + g + b) / 3.0 > 22:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if max_x <= min_x or max_y <= min_y:
        return width * 0.465, height * 0.50, width * 0.29, height * 0.49
    return (min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (max_x - min_x) * 0.5, (max_y - min_y) * 0.5


def load_reference_frames():
    frames = []
    for name in REFERENCE_FRAME_NAMES:
        path = os.path.join(REFERENCE_DIR, name)
        if not os.path.exists(path):
            continue
        image = read_png_rgba(path)
        cx, cy, rx, ry = detect_reference_eye(image)
        frames.append({"name": name, "image": image, "cx": cx, "cy": cy, "rx": rx, "ry": ry})
    return frames


def reference_frame_signature():
    signature = []
    for name in REFERENCE_FRAME_NAMES:
        path = os.path.join(REFERENCE_DIR, name)
        if not os.path.exists(path):
            continue
        stat = os.stat(path)
        signature.append(
            {
                "name": name,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
            }
        )
    return signature


def textures_are_current(textures, reference_signature):
    if not all(os.path.exists(path) for path in textures.values()):
        return False

    try:
        with open(TEXTURE_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except Exception:
        return False

    expected_files = {name: os.path.basename(path) for name, path in textures.items()}
    if manifest.get("generator_version") != TEXTURE_GENERATOR_VERSION:
        return False
    if manifest.get("textures") != expected_files:
        return False
    if manifest.get("mode") in STABLE_TEXTURE_MODES:
        return True
    return manifest.get("reference_signature") == reference_signature


def has_texture_manifest(textures, mode):
    if not all(os.path.exists(path) for path in textures.values()):
        return False
    try:
        with open(TEXTURE_MANIFEST_PATH, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
    except Exception:
        return False
    expected_files = {name: os.path.basename(path) for name, path in textures.items()}
    return manifest.get("mode") == mode and manifest.get("textures") == expected_files


def has_image_generated_texture_manifest(textures):
    return has_texture_manifest(textures, IMAGE_GENERATED_TEXTURE_MODE)


def texture_paths(filenames):
    return {name: os.path.join(TEXTURE_DIR, filename) for name, filename in filenames.items()}


def using_image_generated_textures(textures):
    return all(
        os.path.basename(textures.get(name, "")) == filename
        for name, filename in IMAGE_GENERATED_TEXTURE_FILENAMES.items()
    )


def using_simulator_textures(textures):
    return all(
        os.path.basename(textures.get(name, "")) == filename
        for name, filename in SIMULATOR_TEXTURE_FILENAMES.items()
    )


def using_rich_layered_textures(textures):
    return using_simulator_textures(textures) or using_image_generated_textures(textures)


def resolve_sclera_surface_texture(textures):
    texture = textures.get("sclera")
    if not texture:
        return texture
    if not using_simulator_textures(textures):
        return texture

    candidates = [
        os.path.join(TEXTURE_DIR, IMAGE_GENERATED_TEXTURE_FILENAMES["sclera"]),
        os.path.join(TEXTURE_DIR, PROCEDURAL_FALLBACK_TEXTURE_FILENAMES["sclera"]),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return texture


def missing_texture_files(textures):
    return [
        os.path.basename(path)
        for path in textures.values()
        if not os.path.exists(path)
    ]


def log_texture_decision(message):
    print(f"texture assets: {message}")


def write_texture_manifest(textures, reference_signature, mode):
    manifest = {
        "generator_version": TEXTURE_GENERATOR_VERSION,
        "mode": mode,
        "reference_signature": reference_signature,
        "textures": {name: os.path.basename(path) for name, path in textures.items()},
    }
    with open(TEXTURE_MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")


def sample_reference_polar(frame, radius, angle, radius_jitter=0.0, angle_jitter=0.0):
    image = frame["image"]
    r = radius + radius_jitter
    a = angle + angle_jitter
    x = frame["cx"] + math.cos(a) * frame["rx"] * r
    y = frame["cy"] + math.sin(a) * frame["ry"] * r
    return sample_png(image, x, y)


def average_colors(colors):
    total = [0.0, 0.0, 0.0, 0.0]
    for color in colors:
        for index in range(4):
            total[index] += color[index]
    scale = 1.0 / max(1, len(colors))
    return [channel * scale for channel in total]


def color_luma(color):
    return color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114


def color_chroma(color):
    return max(color[:3]) - min(color[:3])


def reference_pixel_radius(frame, x, y):
    dx = (x - frame["cx"]) / max(frame["rx"], 1.0)
    dy = (y - frame["cy"]) / max(frame["ry"], 1.0)
    return math.sqrt(dx * dx + dy * dy)


def reference_polar_xy(frame, radius, angle):
    return (
        frame["cx"] + math.cos(angle) * frame["rx"] * radius,
        frame["cy"] + math.sin(angle) * frame["ry"] * radius,
    )


def looks_like_instrument(color):
    r, g, b = color[:3]
    luma = color_luma(color)
    chroma = color_chroma(color)
    neutral = chroma < 0.18 and abs(r - g) < 0.12 and abs(g - b) < 0.14
    cold_highlight = b >= r * 0.82 and g >= r * 0.76
    return neutral and cold_highlight and luma > 0.54


def looks_like_specular(color):
    return color_luma(color) > 0.78 and color_chroma(color) < 0.24


def looks_like_vessel(color):
    r, g, b = color[:3]
    red_excess = r - (g + b) * 0.5
    return r > 0.36 and red_excess > 0.16 and g < 0.42


def material_radius_band(material):
    bands = {
        "sclera": (0.52, 0.90),
        "iris": (0.30, 0.50),
        "retro": (0.05, 0.31),
        "capsule": (0.09, 0.34),
        "flap": (0.08, 0.35),
        "metal": (0.0, 0.95),
    }
    return bands[material]


def material_source_radius(material, texture_radius):
    low, high = material_radius_band(material)
    shaped = clamp01(texture_radius)
    if material in ("retro", "capsule", "flap"):
        shaped = math.sqrt(shaped)
    return mix(low, high, shaped)


def material_pixel_allowed(material, color, eye_radius):
    luma = color_luma(color)
    if luma < 0.045:
        return False

    low, high = material_radius_band(material)
    if eye_radius < low or eye_radius > high:
        return False

    if material != "metal" and (looks_like_instrument(color) or looks_like_specular(color)):
        return False

    r, g, b = color[:3]
    if material == "sclera":
        return luma > 0.22 and r >= g * 0.92 and g >= b * 0.88 and not looks_like_vessel(color)
    if material == "iris":
        return 0.07 < luma < 0.48 and color_chroma(color) < 0.42 and r < 0.58
    if material == "retro":
        return r > g * 1.30 and r > b * 1.45 and 0.08 < luma < 0.58
    if material == "capsule":
        return r > g * 1.25 and r > b * 1.45 and 0.09 < luma < 0.62
    if material == "flap":
        return r > g * 1.12 and r > b * 1.30 and 0.10 < luma < 0.68
    if material == "metal":
        return looks_like_instrument(color) and not looks_like_specular(color)
    return False


def build_reference_material_sets(reference_frames):
    materials = ["sclera", "iris", "retro", "capsule", "flap", "metal"]
    sets = {material: {"samples": [], "average": [0.5, 0.5, 0.5, 1.0]} for material in materials}

    for frame in reference_frames:
        image = frame["image"]
        step = max(4, min(image["width"], image["height"]) // 180)
        for y in range(0, image["height"], step):
            for x in range(0, int(image["width"] * 0.76), step):
                color = [channel / 255.0 for channel in image["pixels"][y][x]]
                eye_radius = reference_pixel_radius(frame, x, y)
                for material in materials:
                    if material_pixel_allowed(material, color, eye_radius):
                        sets[material]["samples"].append(color)

    fallbacks = {
        "sclera": [0.62, 0.43, 0.36, 1.0],
        "iris": [0.18, 0.21, 0.23, 1.0],
        "retro": [0.72, 0.06, 0.05, 1.0],
        "capsule": [0.78, 0.07, 0.06, 0.55],
        "flap": [0.88, 0.22, 0.05, 0.78],
        "metal": [0.64, 0.67, 0.72, 1.0],
    }

    for material in materials:
        if sets[material]["samples"]:
            sets[material]["average"] = average_colors(sets[material]["samples"])
        else:
            sets[material]["average"] = fallbacks[material]
    return sets


def sample_material_palette(material_sets, material, x, y, seed):
    samples = material_sets[material]["samples"]
    if not samples:
        return list(material_sets[material]["average"])
    first = int(noise2(x * 19.0, y * 19.0, seed) * len(samples)) % len(samples)
    second = int(noise2(x * 7.0 + 3.1, y * 7.0 - 2.4, seed + 17) * len(samples)) % len(samples)
    t = fbm(x * 3.0, y * 3.0, seed + 31)
    return [mix(samples[first][index], samples[second][index], t) for index in range(4)]


def sample_reference_material(reference_frames, material_sets, material, texture_radius, angle, x, y, seed):
    source_radius = material_source_radius(material, texture_radius)
    low, high = material_radius_band(material)
    for attempt in range(18):
        frame = reference_frames[(seed + attempt * 3) % len(reference_frames)]
        radius_jitter = (noise2(x * 13.0 + attempt, y * 11.0 - attempt, seed) - 0.5) * (high - low) * 0.52
        angle_jitter = (noise2(x * 5.0 - attempt, y * 6.0 + attempt, seed + 5) - 0.5) * 0.62
        radius = clamp(source_radius + radius_jitter, low, high)
        sample_angle = angle + angle_jitter
        sx, sy = reference_polar_xy(frame, radius, sample_angle)
        color = sample_png(frame["image"], sx, sy)
        eye_radius = reference_pixel_radius(frame, sx, sy)
        if material_pixel_allowed(material, color, eye_radius):
            return color
    return sample_material_palette(material_sets, material, x, y, seed + 101)


def vary_reference_color(color, average, x, y, seed, amount=0.05, average_mix=0.18):
    low = fbm(x * 4.0, y * 4.0, seed) - 0.5
    high = fbm(x * 36.0, y * 36.0, seed + 7) - 0.5
    varied = []
    for index in range(3):
        base = mix(color[index], average[index], average_mix)
        varied.append(clamp01(base + low * amount + high * amount * 0.35))
    varied.append(color[3])
    return varied


def choose_reference_frame(reference_frames, preferred_name):
    for frame in reference_frames:
        if frame.get("name") == preferred_name:
            return frame
    return reference_frames[0]


def write_eye_photo_texture(path, frames, source_radius, width=1024, height=1024, alpha=1.0, reject_instruments=False):
    if isinstance(frames, dict):
        frames = [frames]

    def pixel(u, v):
        x = (u * 2.0 - 1.0) * source_radius
        y = (v * 2.0 - 1.0) * source_radius
        fallback = None
        for frame in frames:
            sx = frame["cx"] + x * frame["rx"]
            sy = frame["cy"] + y * frame["ry"]
            color = sample_png(frame["image"], sx, sy)
            if fallback is None:
                fallback = color
            if not reject_instruments or (not looks_like_instrument(color) and not looks_like_specular(color)):
                break
        else:
            color = fallback
        return [color[0], color[1], color[2], alpha]

    write_png(path, width, height, pixel)


def write_forceps_photo_texture(path, frame, width=1024, height=512):
    image = frame["image"]
    start = (frame["cx"] + frame["rx"] * 0.01, frame["cy"] + frame["ry"] * 0.38)
    end = (frame["cx"] + frame["rx"] * 0.82, frame["cy"] + frame["ry"] * 0.69)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy) or 1.0
    nx = -dy / length
    ny = dx / length
    strip_width = min(frame["rx"], frame["ry"]) * 0.18

    def pixel(u, v):
        along_x = start[0] + dx * u
        along_y = start[1] + dy * u
        sx = along_x + nx * (v - 0.5) * strip_width
        sy = along_y + ny * (v - 0.5) * strip_width
        color = sample_png(image, sx, sy)
        return [color[0], color[1], color[2], 1.0]

    write_png(path, width, height, pixel)


def looks_like_iris_pixel(color):
    r, g, b = color[:3]
    luma = color_luma(color)
    red_reflex = r > g * 1.22 and r > b * 1.35
    return 0.06 < luma < 0.48 and color_chroma(color) < 0.42 and not red_reflex


def write_iris_photo_texture(path, frames, width=1024, height=1024):
    angle_offsets = [0.0, 0.65, -0.65, 1.25, -1.25, 2.1, -2.1, math.pi]

    def sample_iris(frame, source_radius, angle):
        sx = frame["cx"] + math.cos(angle) * frame["rx"] * source_radius
        sy = frame["cy"] + math.sin(angle) * frame["ry"] * source_radius
        return sample_png(frame["image"], sx, sy)

    def pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        annulus_t = clamp01((radius - 0.42) / 0.58)
        source_radius = mix(0.43, 0.66, annulus_t)
        fallback = sample_iris(frames[0], source_radius, angle)

        for offset in angle_offsets:
            for frame in frames:
                color = sample_iris(frame, source_radius, angle + offset)
                if looks_like_iris_pixel(color) and not looks_like_instrument(color) and not looks_like_specular(color):
                    return [color[0], color[1], color[2], 1.0]

        return [fallback[0], fallback[1], fallback[2], 1.0]

    write_png(path, width, height, pixel)


def write_photo_texture_assets(textures, reference_frames):
    material_sets = build_reference_material_sets(reference_frames)

    def reference_tint(material, fallback, blend=0.30, max_chroma=None, luma_range=None):
        color = material_sets[material]["average"] if material_sets[material]["samples"] else fallback
        if max_chroma is not None and color_chroma(color) > max_chroma:
            color = fallback
        if luma_range is not None:
            luma = color_luma(color)
            if luma < luma_range[0] or luma > luma_range[1]:
                color = fallback
        return [clamp01(mix(fallback[index], color[index], blend)) for index in range(3)] + [fallback[3]]

    sclera_base = reference_tint("sclera", [0.68, 0.48, 0.41, 1.0], blend=0.24, luma_range=(0.32, 0.82))
    iris_base = reference_tint("iris", [0.18, 0.20, 0.21, 1.0], blend=0.22, max_chroma=0.22, luma_range=(0.10, 0.36))
    retro_base = reference_tint("retro", [0.70, 0.045, 0.035, 1.0], blend=0.34, luma_range=(0.08, 0.55))
    capsule_base = reference_tint("capsule", [0.74, 0.055, 0.065, 0.56], blend=0.26, luma_range=(0.08, 0.56))
    flap_base = reference_tint("flap", [0.86, 0.22, 0.045, 0.78], blend=0.26, luma_range=(0.10, 0.64))

    def sclera_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        tissue = fbm(x * 3.4, y * 3.4, 103)
        fine = fbm(x * 22.0, y * 22.0, 104)
        warm_lift = 0.055 * (1.0 - clamp01(radius * 0.92)) + 0.045 * (tissue - 0.5) + 0.018 * (fine - 0.5)
        vessel = 0.0
        for branch in range(11):
            branch_angle = branch * (2.0 * math.pi / 11.0) + 0.28 * fbm(branch, 0.0, 170)
            branch_angle += 0.10 * math.sin(radius * (9.0 + branch * 0.7) + branch)
            angular_distance = abs(math.atan2(math.sin(angle - branch_angle), math.cos(angle - branch_angle)))
            width = mix(0.0045, 0.012, noise2(branch, 0.6, 172))
            radial_gate = clamp01((radius - 0.25) * 1.4) * clamp01((1.08 - radius) * 3.0)
            vessel += math.exp(-(angular_distance / width) ** 2) * radial_gate * mix(0.25, 0.75, noise2(branch, 1.3, 173))
        vessel = clamp01(vessel)
        r = clamp01(sclera_base[0] + warm_lift + vessel * 0.32)
        g = clamp01(sclera_base[1] + warm_lift * 0.58 - vessel * 0.13)
        b = clamp01(sclera_base[2] + warm_lift * 0.32 - vessel * 0.16)
        return [r, g, b, 1.0]

    def iris_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        spoke = abs(math.sin(angle * 58.0 + fbm(x * 5.0, y * 5.0, 112) * 5.6))
        ring = 0.5 + 0.5 * math.sin(radius * 31.0 + fbm(x * 4.0, y * 4.0, 113) * 3.2)
        crypt = max(0.0, 0.58 - spoke) * (0.65 + 0.35 * ring)
        collarette = 0.050 * math.exp(-((radius - 0.48) ** 2) / 0.012)
        limb = clamp01((radius - 0.74) * 3.6) * 0.10
        pupil_shadow = clamp01((radius - 0.22) * 4.0)
        value = (0.88 + 0.18 * ring - 0.16 * crypt + collarette - limb) * pupil_shadow
        r = clamp01(iris_base[0] * value + 0.018 * collarette)
        g = clamp01(iris_base[1] * value + 0.024 * collarette)
        b = clamp01(iris_base[2] * value + 0.030 * collarette + limb * 0.02)
        return [r, g, b, 1.0]

    def retro_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        radial = 0.5 + 0.5 * math.sin(angle * 22.0 + radius * 7.0)
        fibers = 0.5 + 0.5 * math.sin(radius * 44.0 + fbm(x * 5.0, y * 5.0, 122) * 6.0)
        glow = 0.16 * clamp01(1.0 - radius * 0.72)
        dark_spoke = 0.18 * max(0.0, 0.45 - radial)
        r = clamp01(retro_base[0] + 0.22 * glow + 0.08 * fibers)
        g = clamp01(retro_base[1] + 0.08 * glow + 0.025 * fibers - dark_spoke)
        b = clamp01(retro_base[2] + 0.030 * glow - dark_spoke * 0.55)
        return [r, g, b, 1.0]

    def capsule_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        striae = 0.5 + 0.5 * math.sin(angle * 19.0 + radius * 29.0 + fbm(x * 6.0, y * 6.0, 132) * 6.0)
        wrinkle = fbm(x * 14.0, y * 14.0, 133)
        veil = 0.08 * wrinkle + 0.035 * striae
        r = clamp01(capsule_base[0] + veil)
        g = clamp01(capsule_base[1] + veil * 0.28)
        b = clamp01(capsule_base[2] + veil * 0.12)
        alpha = clamp01(capsule_base[3] + 0.12 * striae + 0.06 * wrinkle)
        return [r, g, b, alpha]

    def flap_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        grain = fbm(x * 12.0, y * 12.0, 142)
        crease = 0.5 + 0.5 * math.sin(angle * 15.0 + radius * 34.0 + grain * 5.0)
        wet_sheen = max(0.0, 1.0 - ((u - 0.60) ** 2 / 0.012 + (v - 0.43) ** 2 / 0.004))
        r = clamp01(flap_base[0] + 0.11 * crease + 0.14 * wet_sheen)
        g = clamp01(flap_base[1] + 0.05 * grain + 0.12 * wet_sheen)
        b = clamp01(flap_base[2] + 0.025 * crease + 0.035 * wet_sheen)
        alpha = clamp01(flap_base[3] + 0.10 * crease + 0.09 * wet_sheen)
        return [r, g, b, alpha]

    def metal_pixel(u, v):
        x = u * 2.0 - 1.0
        y = v * 2.0 - 1.0
        color = sample_material_palette(material_sets, "metal", x, y, 151)
        length_grain = fbm(u * 46.0, v * 4.0, 152) - 0.5
        fine_grain = fbm(u * 180.0, v * 18.0, 153) - 0.5
        bevel = 0.18 * math.exp(-((v - 0.28) ** 2) / 0.0018) + 0.20 * math.exp(-((v - 0.72) ** 2) / 0.0018)
        dark_edge = 0.13 * math.exp(-((v - 0.05) ** 2) / 0.0025) + 0.13 * math.exp(-((v - 0.95) ** 2) / 0.0025)
        shade = color_luma(color) + length_grain * 0.12 + fine_grain * 0.035 + bevel - dark_edge
        return [clamp01(shade + 0.012), clamp01(shade + 0.026), clamp01(shade + 0.052), 1.0]

    write_png(textures["sclera"], 1024, 1024, sclera_pixel)
    write_png(textures["iris"], 1024, 1024, iris_pixel)
    write_png(textures["retro"], 1024, 1024, retro_pixel)
    write_png(textures["capsule"], 1024, 1024, capsule_pixel)
    write_png(textures["flap"], 1024, 1024, flap_pixel)
    write_png(textures["metal"], 1024, 512, metal_pixel)


def ensure_texture_assets(force=False):
    os.makedirs(TEXTURE_DIR, exist_ok=True)

    simulator_textures = texture_paths(SIMULATOR_TEXTURE_FILENAMES)
    image_generated_textures = texture_paths(IMAGE_GENERATED_TEXTURE_FILENAMES)
    textures = texture_paths(PROCEDURAL_FALLBACK_TEXTURE_FILENAMES)
    reference_signature = reference_frame_signature()
    if force:
        log_texture_decision("force regeneration requested; skipping reusable texture manifests")
    else:
        simulator_missing = missing_texture_files(simulator_textures)
        if has_texture_manifest(simulator_textures, SIMULATOR_TEXTURE_MODE):
            log_texture_decision(f"using {SIMULATOR_TEXTURE_MODE}; manifest is current")
            write_texture_manifest(simulator_textures, reference_signature, SIMULATOR_TEXTURE_MODE)
            return simulator_textures
        if simulator_missing:
            log_texture_decision(
                f"not using {SIMULATOR_TEXTURE_MODE}; missing files: {', '.join(simulator_missing)}"
            )
        else:
            log_texture_decision(f"using {SIMULATOR_TEXTURE_MODE}; refreshing missing or stale manifest")
            write_texture_manifest(simulator_textures, reference_signature, SIMULATOR_TEXTURE_MODE)
            return simulator_textures

        image_missing = missing_texture_files(image_generated_textures)
        if has_image_generated_texture_manifest(image_generated_textures):
            log_texture_decision(f"using {IMAGE_GENERATED_TEXTURE_MODE}; manifest is current")
            write_texture_manifest(image_generated_textures, reference_signature, IMAGE_GENERATED_TEXTURE_MODE)
            return image_generated_textures
        if image_missing:
            log_texture_decision(
                f"not using {IMAGE_GENERATED_TEXTURE_MODE}; missing files: {', '.join(image_missing)}"
            )
        else:
            log_texture_decision(f"using {IMAGE_GENERATED_TEXTURE_MODE}; refreshing missing or stale manifest")
            write_texture_manifest(image_generated_textures, reference_signature, IMAGE_GENERATED_TEXTURE_MODE)
            return image_generated_textures

        if textures_are_current(textures, reference_signature):
            log_texture_decision("using procedural fallback textures; manifest and reference signature are current")
            return textures
        log_texture_decision("procedural fallback textures are missing or stale; regenerating")

    try:
        reference_frames = load_reference_frames()
    except Exception as error:
        log_texture_decision(f"reference frames unavailable; using procedural generator ({error})")
        reference_frames = []

    if reference_frames:
        log_texture_decision("generating photo-derived fallback textures from reference frames")
        write_photo_texture_assets(textures, reference_frames)
        write_texture_manifest(textures, reference_signature, "reference_synthesized_clean")
        return textures

    def sclera_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        warm = 0.54 + 0.18 * (1.0 - radius) + 0.13 * fbm(x * 2.8, y * 2.8, 3)
        limbus = clamp01((radius - 0.67) * 6.0)
        pink = clamp01(0.08 + 0.20 * limbus + 0.10 * fbm(x * 7.0, y * 7.0, 11))
        fiber = 0.035 * math.sin(23.0 * angle + 9.0 * radius + fbm(x * 3.0, y * 3.0, 5) * 4.0)
        r = clamp01(warm + pink + fiber)
        g = clamp01(warm * 0.78 + 0.08 - pink * 0.18)
        b = clamp01(warm * 0.66 + 0.06 - pink * 0.28)
        return [r, g, b, 1.0]

    def iris_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        spoke = abs(math.sin(angle * 42.0 + fbm(x * 5.0, y * 5.0, 17) * 5.2))
        crypts = max(0.0, 0.65 - spoke) * (0.7 + 0.3 * math.sin(radius * 34.0))
        ring = 0.5 + 0.5 * math.sin(radius * 29.0 + fbm(x * 4.0, y * 4.0, 9) * 3.0)
        limb = clamp01((radius - 0.62) * 4.2)
        pupil_shadow = 1.0 - clamp01((0.33 - radius) * 5.0)
        base = 0.20 + 0.16 * ring - 0.10 * crypts
        r = clamp01((base * 0.72 + 0.03) * pupil_shadow - limb * 0.05)
        g = clamp01((base * 0.82 + 0.04) * pupil_shadow - limb * 0.04)
        b = clamp01((base * 0.88 + 0.05) * pupil_shadow + limb * 0.02)
        return [r, g, b, 1.0]

    def retro_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        radial = 0.5 + 0.5 * math.sin(angle * 22.0 + radius * 7.0)
        fibers = 0.5 + 0.5 * math.sin(radius * 44.0 + fbm(x * 5.0, y * 5.0, 21) * 6.0)
        glow = clamp01(1.0 - radius * 0.62)
        dark_spoke = 0.20 * max(0.0, 0.45 - radial)
        r = clamp01(0.62 + 0.30 * glow + 0.10 * fibers)
        g = clamp01(0.03 + 0.11 * glow + 0.04 * fibers - dark_spoke)
        b = clamp01(0.02 + 0.035 * glow - dark_spoke * 0.6)
        return [r, g, b, 1.0]

    def capsule_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        striae = 0.5 + 0.5 * math.sin(angle * 18.0 + radius * 28.0 + fbm(x * 6.0, y * 6.0, 31) * 6.0)
        wrinkle = fbm(x * 10.0, y * 10.0, 41)
        r = clamp01(0.58 + 0.20 * striae + 0.08 * wrinkle)
        g = clamp01(0.03 + 0.05 * wrinkle)
        b = clamp01(0.09 + 0.05 * striae)
        alpha = clamp01(0.38 + 0.18 * striae)
        return [r, g, b, alpha]

    def flap_pixel(u, v):
        x, y, radius, angle = radial_uv(u, v)
        grain = fbm(x * 12.0, y * 12.0, 53)
        crease = 0.5 + 0.5 * math.sin(angle * 15.0 + radius * 33.0 + grain * 5.0)
        sheen = max(0.0, 1.0 - ((u - 0.62) ** 2 / 0.018 + (v - 0.48) ** 2 / 0.003))
        r = clamp01(0.88 + 0.15 * crease + 0.12 * sheen)
        g = clamp01(0.18 + 0.10 * grain + 0.18 * sheen)
        b = clamp01(0.025 + 0.035 * crease)
        alpha = clamp01(0.64 + 0.18 * crease + 0.12 * sheen)
        return [r, g, b, alpha]

    def metal_pixel(u, v):
        grain = 0.5 + 0.5 * math.sin(u * 210.0 + fbm(u * 12.0, v * 3.0, 67) * 9.0)
        long_streak = 0.5 + 0.5 * math.sin((u + v * 0.16) * 36.0)
        shade = 0.54 + 0.24 * grain + 0.15 * long_streak
        return [clamp01(shade), clamp01(shade + 0.035), clamp01(shade + 0.07), 1.0]

    write_png(textures["sclera"], 512, 512, sclera_pixel)
    write_png(textures["iris"], 512, 512, iris_pixel)
    write_png(textures["retro"], 512, 512, retro_pixel)
    write_png(textures["capsule"], 512, 512, capsule_pixel)
    write_png(textures["flap"], 512, 512, flap_pixel)
    write_png(textures["metal"], 512, 256, metal_pixel)
    write_texture_manifest(textures, reference_signature, "procedural_clean_fallback")
    log_texture_decision("generated procedural fallback textures")
    return textures
