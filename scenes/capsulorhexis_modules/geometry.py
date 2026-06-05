import math

from .assets import sofa_path
from .math_utils import clamp, clamp01, mix, noise2

def planar_texcoords(positions, radius=None, repeat=1.0):
    if radius is None:
        radius = max(math.sqrt(x * x + y * y) for x, y, _z in positions) or 1.0
    return [[0.5 + repeat * x / (2.0 * radius), 0.5 + repeat * y / (2.0 * radius)] for x, y, _z in positions]


def annular_texcoords(positions, inner_radius, outer_radius, texture_inner=0.0, texture_outer=1.0):
    span = max(outer_radius - inner_radius, 1.0e-6)
    coords = []
    for x, y, _z in positions:
        radius = math.sqrt(x * x + y * y)
        angle = math.atan2(y, x)
        t = clamp01((radius - inner_radius) / span)
        texture_radius = mix(texture_inner, texture_outer, t)
        coords.append([0.5 + math.cos(angle) * texture_radius * 0.5, 0.5 + math.sin(angle) * texture_radius * 0.5])
    return coords

def polar(radius, angle, z=0.0):
    return [radius * math.cos(angle), radius * math.sin(angle), z]


def generate_annulus(inner_radius, outer_radius, rings, segments, z=0.0):
    positions = []
    triangles = []

    for ring in range(rings + 1):
        t = ring / rings
        radius = inner_radius + (outer_radius - inner_radius) * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            positions.append(polar(radius, angle, z))

    for ring in range(rings):
        row = ring * segments
        next_row = (ring + 1) * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    boundary = list(range(segments))
    return positions, triangles, boundary


def generate_disk(radius, rings, segments, z=0.01):
    positions = [[0.0, 0.0, z]]
    triangles = []

    for ring in range(1, rings + 1):
        r = radius * ring / rings
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            positions.append(polar(r, angle, z))

    first_ring = 1
    for seg in range(segments):
        triangles.append([0, first_ring + seg, first_ring + ((seg + 1) % segments)])

    for ring in range(1, rings):
        row = 1 + (ring - 1) * segments
        next_row = 1 + ring * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    outer_boundary = list(range(1 + (rings - 1) * segments, 1 + rings * segments))
    return positions, triangles, outer_boundary


def generate_domed_disk(radius, rings, segments, z=-0.35, dome_height=0.16):
    positions = [[0.0, 0.0, z + dome_height]]
    triangles = []

    for ring in range(1, rings + 1):
        t = ring / rings
        r = radius * t
        dome = dome_height * (1.0 - t * t)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            ripple = 0.018 * math.sin(angle * 18.0 + t * 7.0) * (1.0 - t)
            positions.append(polar(r, angle, z + dome + ripple))

    first_ring = 1
    for seg in range(segments):
        triangles.append([0, first_ring + seg, first_ring + ((seg + 1) % segments)])

    for ring in range(1, rings):
        row = 1 + (ring - 1) * segments
        next_row = 1 + ring * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    outer_boundary = list(range(1 + (rings - 1) * segments, 1 + rings * segments))
    return positions, triangles, outer_boundary


def generate_sclera(inner_radius, outer_radius, rings, segments, z=-0.18):
    positions = []
    triangles = []

    for ring in range(rings + 1):
        t = ring / rings
        base_radius = inner_radius + (outer_radius - inner_radius) * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            irregularity = 0.026 * math.sin(angle * 7.0 + t * 3.0) + 0.018 * math.sin(angle * 17.0)
            radius = base_radius + irregularity * (0.2 + t)
            limbal_slope = 0.085 * t * t
            surface_pores = 0.016 * math.sin(angle * 23.0 + t * 9.0) + 0.01 * math.sin(angle * 41.0)
            positions.append(polar(radius, angle, z + limbal_slope + surface_pores * (0.3 + 0.7 * t)))

    for ring in range(rings):
        row = ring * segments
        next_row = (ring + 1) * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    return positions, triangles, list(range(segments))


def generate_iris(inner_radius, outer_radius, rings, segments, z=-0.105):
    positions = []
    triangles = []

    for ring in range(rings + 1):
        t = ring / rings
        radius = inner_radius + (outer_radius - inner_radius) * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            radial_furrow = 0.032 * math.sin(angle * 36.0 + t * 4.0) * (1.0 - abs(t - 0.48) * 1.6)
            collarette = 0.055 * math.exp(-((t - 0.23) ** 2) / 0.012)
            limbal_roll = -0.035 * math.exp(-((t - 0.95) ** 2) / 0.01)
            positions.append(polar(radius, angle, z + radial_furrow + collarette + limbal_roll))

    for ring in range(rings):
        row = ring * segments
        next_row = (ring + 1) * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    return positions, triangles, list(range(segments))


def generate_capsule_annulus(inner_radius, outer_radius, rings, segments, z=0.0):
    if rings < 1:
        raise ValueError("Capsule annulus requires at least one ring")
    if segments < 3:
        raise ValueError("Capsule annulus requires at least three segments")
    positions = []
    triangles = []

    if inner_radius <= 1.0e-9:
        positions.append([0.0, 0.0, z])
        inner_boundary = [0]
        first_ring = 1
    else:
        inner_boundary = list(range(segments))
        first_ring = 0

    for ring in range(first_ring, rings + 1):
        t = ring / rings
        radius = inner_radius + (outer_radius - inner_radius) * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            wrinkle = 0.018 * math.sin(angle * 16.0 + t * 13.0) + 0.011 * math.sin(angle * 37.0)
            sag = -0.025 * t + 0.018 * math.exp(-((t - 0.08) ** 2) / 0.006)
            positions.append(polar(radius, angle, z + wrinkle * (1.0 - t * 0.55) + sag))

    if inner_radius <= 1.0e-9:
        first_row = 1
        for seg in range(segments):
            c = first_row + seg
            d = first_row + ((seg + 1) % segments)
            triangles.append([0, c, d])
        start_connect_ring = 1
    else:
        start_connect_ring = 0

    for ring in range(start_connect_ring, rings):
        row = (ring - first_ring) * segments + (1 if inner_radius <= 1.0e-9 else 0)
        next_row = row + segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    return positions, triangles, inner_boundary


def generate_flap_disk(radius, rings, segments, z=0.018):
    positions = [[0.0, 0.0, z + 0.035]]
    triangles = []

    for ring in range(1, rings + 1):
        t = ring / rings
        r = radius * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            ripple = 0.028 * math.sin(angle * 11.0 + t * 8.0) * (0.4 + 0.6 * t)
            radial_crease = 0.015 * math.sin(angle * 31.0)
            positions.append(polar(r, angle, z + ripple + radial_crease))

    first_ring = 1
    for seg in range(segments):
        triangles.append([0, first_ring + seg, first_ring + ((seg + 1) % segments)])

    for ring in range(1, rings):
        row = 1 + (ring - 1) * segments
        next_row = 1 + ring * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    outer_boundary = list(range(1 + (rings - 1) * segments, 1 + rings * segments))
    return positions, triangles, outer_boundary


def generate_curve(radius, segments, z=0.045):
    positions = []
    edges = []
    for seg in range(segments):
        angle = 2.0 * math.pi * seg / segments
        positions.append(polar(radius, angle, z))
        edges.append([seg, (seg + 1) % segments])
    return positions, edges


def generate_scleral_vessels(inner_radius, outer_radius, branches=34, z=0.058):
    positions = []
    edges = []
    golden = math.pi * (3.0 - math.sqrt(5.0))

    for branch in range(branches):
        base_angle = branch * golden
        start_radius = outer_radius * (0.88 + 0.08 * math.sin(branch * 1.7))
        end_radius = inner_radius + (outer_radius - inner_radius) * (0.18 + 0.18 * math.sin(branch * 2.3) ** 2)
        steps = 5 + (branch % 4)
        previous_index = None

        for step in range(steps):
            t = step / (steps - 1)
            radius = start_radius * (1.0 - t) + end_radius * t
            wiggle = 0.08 * math.sin(step * 1.6 + branch * 0.9) + 0.035 * math.sin(step * 3.1)
            angle = base_angle + wiggle
            index = len(positions)
            positions.append(polar(radius, angle, z + 0.01 * math.sin(t * math.pi)))
            if previous_index is not None:
                edges.append([previous_index, index])
            previous_index = index

        if branch % 3 == 0:
            fork_base = previous_index
            fork_angle = base_angle + 0.18
            fork_radius = max(inner_radius, end_radius - 0.42)
            fork_index = len(positions)
            positions.append(polar(fork_radius, fork_angle, z + 0.012))
            edges.append([fork_base, fork_index])

    return positions, edges


def generate_vessel_ribbons(inner_radius, outer_radius, branches=42, z=0.075, width=0.035):
    positions = []
    triangles = []
    golden = math.pi * (3.0 - math.sqrt(5.0))

    def add_polyline(points, base_width):
        if len(points) < 2:
            return
        start = len(positions)
        for index, point in enumerate(points):
            if index == 0:
                dx = points[1][0] - point[0]
                dy = points[1][1] - point[1]
            elif index == len(points) - 1:
                dx = point[0] - points[index - 1][0]
                dy = point[1] - points[index - 1][1]
            else:
                dx = points[index + 1][0] - points[index - 1][0]
                dy = points[index + 1][1] - points[index - 1][1]
            length = math.sqrt(dx * dx + dy * dy) or 1.0
            nx = -dy / length
            ny = dx / length
            taper = 1.0 - 0.58 * (index / max(1, len(points) - 1))
            half = base_width * taper
            positions.append([point[0] + nx * half, point[1] + ny * half, point[2]])
            positions.append([point[0] - nx * half, point[1] - ny * half, point[2]])

        for index in range(len(points) - 1):
            a = start + index * 2
            b = a + 1
            c = a + 2
            d = a + 3
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    for branch in range(branches):
        base_angle = branch * golden
        start_radius = outer_radius * (0.92 + 0.05 * math.sin(branch * 1.9))
        end_radius = inner_radius + (outer_radius - inner_radius) * (0.14 + 0.22 * math.sin(branch * 2.2) ** 2)
        steps = 7 + (branch % 5)
        points = []
        for step in range(steps):
            t = step / (steps - 1)
            radius = mix(start_radius, end_radius, t)
            wiggle = 0.11 * math.sin(step * 1.3 + branch * 0.7) + 0.045 * math.sin(step * 3.7)
            angle = base_angle + wiggle
            points.append(polar(radius, angle, z + 0.018 * math.sin(t * math.pi)))
        add_polyline(points, width * (0.55 + 0.65 * ((branch % 7) / 6.0)))

        if branch % 3 == 0:
            fork_start = points[max(2, len(points) - 3)]
            fork_points = [fork_start]
            fork_angle = base_angle + 0.22 + 0.08 * math.sin(branch)
            fork_radius = math.sqrt(fork_start[0] * fork_start[0] + fork_start[1] * fork_start[1])
            for step in range(1, 4):
                t = step / 3.0
                fork_points.append(polar(fork_radius - 0.28 * t, fork_angle + 0.08 * t, z + 0.015))
            add_polyline(fork_points, width * 0.52)

    return positions, triangles


def generate_radial_strokes(inner_radius, outer_radius, count, z=0.04, start_phase=0.0):
    positions = []
    edges = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for index in range(count):
        angle = start_phase + index * golden
        length = 0.35 + 0.65 * noise2(index, count, 5)
        r0 = mix(inner_radius, outer_radius, 0.08 + 0.18 * noise2(index, 0.2, 8))
        r1 = mix(r0, outer_radius, length)
        steps = 4
        previous = None
        for step in range(steps):
            t = step / (steps - 1)
            radius = mix(r0, r1, t)
            bend = 0.035 * math.sin(t * math.pi + index * 0.9)
            current_angle = angle + bend
            current = len(positions)
            positions.append(polar(radius, current_angle, z + 0.006 * math.sin(t * math.pi)))
            if previous is not None:
                edges.append([previous, current])
            previous = current
    return positions, edges


def generate_cornea(radius, rings=10, segments=96, limbus_radius=None, apex_z=None):
    if rings < 1:
        raise ValueError("Cornea requires at least one ring")
    if segments < 3:
        raise ValueError("Cornea requires at least three segments")
    positions = []
    triangles = []
    if limbus_radius is None:
        max_theta = math.radians(72.0)
    else:
        max_theta = math.asin(clamp(limbus_radius / max(radius, 1.0e-6), 0.0, 0.999))
    z_offset = -1.2 if apex_z is None else apex_z - radius

    positions.append([0.0, 0.0, radius + z_offset])

    for ring in range(1, rings + 1):
        theta = max_theta * ring / rings
        r = radius * math.sin(theta)
        z = radius * math.cos(theta) + z_offset
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            positions.append([r * math.cos(angle), r * math.sin(angle), z])

    for seg in range(segments):
        c = 1 + seg
        d = 1 + ((seg + 1) % segments)
        triangles.append([0, c, d])

    for ring in range(1, rings):
        row = 1 + (ring - 1) * segments
        next_row = row + segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    return positions, triangles


def generate_cornea_shell(
    horizontal_diameter=11.7,
    vertical_diameter=10.6,
    central_thickness=0.53,
    edge_thickness=0.67,
    anterior_radius=7.8,
    posterior_radius=6.5,
    posterior_apex_z=6.25,
    rings=16,
    segments=216,
):
    if rings < 1:
        raise ValueError("Cornea shell requires at least one ring")
    if segments < 3:
        raise ValueError("Cornea shell requires at least three segments")

    rx = horizontal_diameter * 0.5
    ry = vertical_diameter * 0.5
    equivalent_radius = max(rx, ry)
    anterior_apex_z = posterior_apex_z + central_thickness
    anterior_edge_sag = anterior_radius - math.sqrt(max(anterior_radius * anterior_radius - equivalent_radius * equivalent_radius, 1.0e-6))
    posterior_edge_sag = posterior_radius - math.sqrt(max(posterior_radius * posterior_radius - equivalent_radius * equivalent_radius, 1.0e-6))
    anterior_edge_z = anterior_apex_z - anterior_edge_sag
    desired_posterior_edge_z = anterior_edge_z - edge_thickness
    raw_posterior_edge_z = posterior_apex_z - posterior_edge_sag
    posterior_edge_correction = desired_posterior_edge_z - raw_posterior_edge_z

    positions = [[0.0, 0.0, anterior_apex_z]]
    front_rows = [[0]]
    for ring in range(1, rings + 1):
        t = ring / rings
        row = []
        radial = equivalent_radius * t
        anterior_sag = anterior_radius - math.sqrt(max(anterior_radius * anterior_radius - radial * radial, 1.0e-6))
        z = anterior_apex_z - anterior_sag
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            row.append(len(positions))
            positions.append([rx * t * math.cos(angle), ry * t * math.sin(angle), z])
        front_rows.append(row)

    back_center = len(positions)
    positions.append([0.0, 0.0, posterior_apex_z])
    back_rows = [[back_center]]
    for ring in range(1, rings + 1):
        t = ring / rings
        row = []
        radial = equivalent_radius * t
        posterior_sag = posterior_radius - math.sqrt(max(posterior_radius * posterior_radius - radial * radial, 1.0e-6))
        z = posterior_apex_z - posterior_sag + posterior_edge_correction * t * t
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            row.append(len(positions))
            positions.append([rx * t * math.cos(angle), ry * t * math.sin(angle), z])
        back_rows.append(row)

    triangles = []

    for seg in range(segments):
        triangles.append([front_rows[0][0], front_rows[1][seg], front_rows[1][(seg + 1) % segments]])

    for ring in range(1, rings):
        row = front_rows[ring]
        next_row = front_rows[ring + 1]
        for seg in range(segments):
            a = row[seg]
            b = row[(seg + 1) % segments]
            c = next_row[seg]
            d = next_row[(seg + 1) % segments]
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    for seg in range(segments):
        triangles.append([back_rows[0][0], back_rows[1][(seg + 1) % segments], back_rows[1][seg]])

    for ring in range(1, rings):
        row = back_rows[ring]
        next_row = back_rows[ring + 1]
        for seg in range(segments):
            a = row[seg]
            b = row[(seg + 1) % segments]
            c = next_row[seg]
            d = next_row[(seg + 1) % segments]
            triangles.append([a, d, c])
            triangles.append([a, b, d])

    front_outer = front_rows[-1]
    back_outer = back_rows[-1]
    for seg in range(segments):
        a = front_outer[seg]
        b = front_outer[(seg + 1) % segments]
        c = back_outer[seg]
        d = back_outer[(seg + 1) % segments]
        triangles.append([a, b, d])
        triangles.append([a, d, c])

    return positions, triangles


def generate_anterior_chamber_surface(radius=5.45, apex_z=6.22, iris_z=3.25, rings=10, segments=216):
    positions = [[0.0, 0.0, apex_z]]
    triangles = []
    for ring in range(1, rings + 1):
        t = ring / rings
        r = radius * t
        z = mix(apex_z, iris_z, t ** 1.65)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            positions.append([r * math.cos(angle), r * math.sin(angle), z])

    for seg in range(segments):
        triangles.append([0, 1 + seg, 1 + ((seg + 1) % segments)])

    for ring in range(1, rings):
        row = 1 + (ring - 1) * segments
        next_row = row + segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])
    return positions, triangles


def generate_iris_sheet(inner_radius, outer_radius, thickness=0.6, front_z=3.25, rings=8, segments=216):
    positions = []
    triangles = []
    front_rows = []
    back_rows = []

    for side in ("front", "back"):
        rows = front_rows if side == "front" else back_rows
        z_base = front_z if side == "front" else front_z - thickness
        for ring in range(rings + 1):
            t = ring / rings
            radius = mix(inner_radius, outer_radius, t)
            row = []
            for seg in range(segments):
                angle = 2.0 * math.pi * seg / segments
                radial_furrow = 0.055 * math.sin(angle * 42.0 + t * 5.0) * (1.0 - abs(t - 0.52) * 1.35)
                sphincter = 0.05 * math.exp(-((t - 0.13) ** 2) / 0.006)
                collarette = 0.08 * math.exp(-((t - 0.30) ** 2) / 0.012)
                root_roll = -0.05 * math.exp(-((t - 0.96) ** 2) / 0.01)
                side_offset = 0.35 if side == "front" else -0.18
                z = z_base + radial_furrow * side_offset + sphincter + collarette + root_roll
                row.append(len(positions))
                positions.append([radius * math.cos(angle), radius * math.sin(angle), z])
            rows.append(row)

    for ring in range(rings):
        front_row = front_rows[ring]
        front_next = front_rows[ring + 1]
        back_row = back_rows[ring]
        back_next = back_rows[ring + 1]
        for seg in range(segments):
            a = front_row[seg]
            b = front_row[(seg + 1) % segments]
            c = front_next[seg]
            d = front_next[(seg + 1) % segments]
            triangles.append([a, c, d])
            triangles.append([a, d, b])

            a = back_row[seg]
            b = back_row[(seg + 1) % segments]
            c = back_next[seg]
            d = back_next[(seg + 1) % segments]
            triangles.append([a, d, c])
            triangles.append([a, b, d])

    for boundary_index in (0, -1):
        front = front_rows[boundary_index]
        back = back_rows[boundary_index]
        for seg in range(segments):
            a = front[seg]
            b = front[(seg + 1) % segments]
            c = back[seg]
            d = back[(seg + 1) % segments]
            triangles.append([a, b, d])
            triangles.append([a, d, c])

    return positions, triangles, front_rows[0]


def generate_sclera_shell(inner_radius=5.85, outer_radius=12.0, inner_z=3.7, posterior_z=-4.2, rings=12, segments=216):
    positions = []
    triangles = []

    for ring in range(rings + 1):
        t = ring / rings
        radius = mix(inner_radius, outer_radius, t)
        z = mix(inner_z, posterior_z, t ** 1.15)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            limbal_blend = 0.08 * math.exp(-((t - 0.04) ** 2) / 0.006)
            fiber = 0.035 * math.sin(angle * 9.0 + t * 6.0) + 0.016 * math.sin(angle * 23.0)
            positions.append([radius * math.cos(angle), radius * math.sin(angle), z + limbal_blend + fiber * (0.2 + t)])

    for ring in range(rings):
        row = ring * segments
        next_row = (ring + 1) * segments
        for seg in range(segments):
            a = row + seg
            b = row + ((seg + 1) % segments)
            c = next_row + seg
            d = next_row + ((seg + 1) % segments)
            triangles.append([a, c, d])
            triangles.append([a, d, b])

    return positions, triangles, list(range(segments))


def generate_ciliary_body(inner_radius=5.05, outer_radius=6.45, front_z=2.35, thickness=1.5, rings=4, segments=216):
    positions = []
    triangles = []
    front_rows = []
    back_rows = []

    for side in ("front", "back"):
        rows = front_rows if side == "front" else back_rows
        z_base = front_z if side == "front" else front_z - thickness
        for ring in range(rings + 1):
            t = ring / rings
            radius = mix(inner_radius, outer_radius, t)
            row = []
            for seg in range(segments):
                angle = 2.0 * math.pi * seg / segments
                muscle_bulge = 0.16 * math.sin(t * math.pi)
                process_ripple = 0.07 * math.sin(angle * 72.0) * (1.0 - t)
                z = z_base + (0.10 * math.sin(angle * 24.0) * (1.0 - t) if side == "front" else -0.04 * math.sin(angle * 18.0))
                row.append(len(positions))
                positions.append([(radius + muscle_bulge + process_ripple) * math.cos(angle), (radius + muscle_bulge + process_ripple) * math.sin(angle), z])
            rows.append(row)

    for ring in range(rings):
        for rows, flip in ((front_rows, False), (back_rows, True)):
            row = rows[ring]
            next_row = rows[ring + 1]
            for seg in range(segments):
                a = row[seg]
                b = row[(seg + 1) % segments]
                c = next_row[seg]
                d = next_row[(seg + 1) % segments]
                triangles.append([a, d, c] if flip else [a, c, d])
                triangles.append([a, b, d] if flip else [a, d, b])

    for boundary_index in (0, -1):
        front = front_rows[boundary_index]
        back = back_rows[boundary_index]
        for seg in range(segments):
            a = front[seg]
            b = front[(seg + 1) % segments]
            c = back[seg]
            d = back[(seg + 1) % segments]
            triangles.append([a, b, d])
            triangles.append([a, d, c])

    return positions, triangles


def generate_ciliary_processes(base_radius=5.45, tip_radius=4.9, front_z=2.12, back_z=0.95, count=72, angular_width=0.020):
    positions = []
    triangles = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        width = angular_width * (0.75 + 0.25 * math.sin(index * 1.7))
        start = len(positions)
        points = [
            (base_radius, angle - width, front_z),
            (base_radius, angle + width, front_z - 0.06),
            (tip_radius, angle + width * 0.55, (front_z + back_z) * 0.5),
            (tip_radius, angle - width * 0.55, (front_z + back_z) * 0.5 + 0.08),
            (base_radius, angle - width * 0.72, back_z),
            (base_radius, angle + width * 0.72, back_z),
        ]
        for radius, point_angle, z in points:
            positions.append([radius * math.cos(point_angle), radius * math.sin(point_angle), z])
        triangles.extend(
            [
                [start + 0, start + 1, start + 2],
                [start + 0, start + 2, start + 3],
                [start + 4, start + 3, start + 2],
                [start + 4, start + 2, start + 5],
                [start + 0, start + 3, start + 4],
                [start + 1, start + 5, start + 2],
            ]
        )
    return positions, triangles


def generate_lens_shell(radius=4.75, thickness=4.0, rings=18, segments=216):
    positions = [[0.0, 0.0, thickness * 0.5]]
    front_rows = [[0]]
    for ring in range(1, rings + 1):
        t = ring / rings
        row = []
        r = radius * t
        z = thickness * 0.5 * (1.0 - t ** 2.15)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            row.append(len(positions))
            positions.append([r * math.cos(angle), r * math.sin(angle), z])
        front_rows.append(row)

    back_center = len(positions)
    positions.append([0.0, 0.0, -thickness * 0.5])
    back_rows = [[back_center]]
    for ring in range(1, rings + 1):
        t = ring / rings
        row = []
        r = radius * t
        z = -thickness * 0.5 * (1.0 - t ** 1.55)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            row.append(len(positions))
            positions.append([r * math.cos(angle), r * math.sin(angle), z])
        back_rows.append(row)

    triangles = []
    for seg in range(segments):
        triangles.append([front_rows[0][0], front_rows[1][seg], front_rows[1][(seg + 1) % segments]])
        triangles.append([back_rows[0][0], back_rows[1][(seg + 1) % segments], back_rows[1][seg]])

    for ring in range(1, rings):
        front = front_rows[ring]
        front_next = front_rows[ring + 1]
        back = back_rows[ring]
        back_next = back_rows[ring + 1]
        for seg in range(segments):
            a = front[seg]
            b = front[(seg + 1) % segments]
            c = front_next[seg]
            d = front_next[(seg + 1) % segments]
            triangles.append([a, c, d])
            triangles.append([a, d, b])

            a = back[seg]
            b = back[(seg + 1) % segments]
            c = back_next[seg]
            d = back_next[(seg + 1) % segments]
            triangles.append([a, d, c])
            triangles.append([a, b, d])

    front_outer = front_rows[-1]
    back_outer = back_rows[-1]
    for seg in range(segments):
        a = front_outer[seg]
        b = front_outer[(seg + 1) % segments]
        c = back_outer[seg]
        d = back_outer[(seg + 1) % segments]
        triangles.append([a, b, d])
        triangles.append([a, d, c])

    return positions, triangles


def generate_zonule_fibers(ciliary_radius=5.05, lens_radius=4.75, count=240):
    positions = []
    edges = []
    z_pairs = ((1.00, 0.42), (0.42, 0.0), (-0.10, -0.42))
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        angle_jitter = 0.004 * math.sin(index * 2.17)
        for start_z, end_z in z_pairs:
            start = len(positions)
            start_angle = angle + angle_jitter
            end_angle = angle - angle_jitter * 0.5
            positions.append([ciliary_radius * math.cos(start_angle), ciliary_radius * math.sin(start_angle), start_z])
            positions.append([lens_radius * math.cos(end_angle), lens_radius * math.sin(end_angle), end_z])
            edges.append([start, start + 1])
    return positions, edges


def generate_vitreous_cavity_outline(segments=96):
    positions = []
    edges = []
    rings = [
        (-2.05, 5.15),
        (-4.6, 8.0),
        (-8.5, 10.7),
        (-12.2, 11.4),
        (-15.3, 7.6),
        (-17.2, 0.35),
    ]

    for z, radius in rings:
        row_start = len(positions)
        for seg in range(segments):
            angle = 2.0 * math.pi * seg / segments
            positions.append([radius * math.cos(angle), radius * math.sin(angle), z])
            edges.append([row_start + seg, row_start + ((seg + 1) % segments)])

    for row in range(len(rings) - 1):
        start = row * segments
        next_start = (row + 1) * segments
        for seg in range(0, segments, max(1, segments // 12)):
            edges.append([start + seg, next_start + seg])

    return positions, edges


def generate_ellipse_curve(radius_x, radius_y, segments, z=0.0):
    positions = []
    edges = []
    for seg in range(segments):
        angle = 2.0 * math.pi * seg / segments
        positions.append([radius_x * math.cos(angle), radius_y * math.sin(angle), z])
        edges.append([seg, (seg + 1) % segments])
    return positions, edges


def generate_forceps(length=8.5, width=0.10, gap=0.22, z=0.2):
    positions = []
    triangles = []

    def add_box(center0, center1, half_width0, half_width1, half_height0, half_height1):
        start = len(positions)
        x0, y0, z0 = center0
        x1, y1, z1 = center1
        positions.extend(
            [
                [x0, y0 - half_width0, z0 - half_height0],
                [x0, y0 + half_width0, z0 - half_height0],
                [x0, y0 + half_width0, z0 + half_height0],
                [x0, y0 - half_width0, z0 + half_height0],
                [x1, y1 - half_width1, z1 - half_height1],
                [x1, y1 + half_width1, z1 - half_height1],
                [x1, y1 + half_width1, z1 + half_height1],
                [x1, y1 - half_width1, z1 + half_height1],
            ]
        )
        triangles.extend(
            [
                [start + 0, start + 4, start + 5],
                [start + 0, start + 5, start + 1],
                [start + 1, start + 5, start + 6],
                [start + 1, start + 6, start + 2],
                [start + 2, start + 6, start + 7],
                [start + 2, start + 7, start + 3],
                [start + 3, start + 7, start + 4],
                [start + 3, start + 4, start + 0],
                [start + 4, start + 7, start + 6],
                [start + 4, start + 6, start + 5],
            ]
        )

    def add_prong(y_offset):
        base_x = -length
        shoulder_x = -0.9
        tip_x = -0.16
        add_box([base_x, y_offset, z], [shoulder_x, y_offset * 0.72, z + 0.11], width * 1.18, width * 0.74, 0.065, 0.055)
        add_box([shoulder_x, y_offset * 0.72, z + 0.11], [tip_x, y_offset * 0.30, z + 0.22], width * 0.74, width * 0.20, 0.055, 0.03)

        groove_start = len(positions)
        groove_y = y_offset * 0.9
        positions.extend(
            [
                [base_x + 0.35, groove_y - width * 0.18, z + 0.072],
                [shoulder_x - 0.18, groove_y - width * 0.12, z + 0.158],
                [shoulder_x - 0.18, groove_y + width * 0.12, z + 0.158],
                [base_x + 0.35, groove_y + width * 0.18, z + 0.072],
            ]
        )
        triangles.extend([[groove_start, groove_start + 1, groove_start + 2], [groove_start, groove_start + 2, groove_start + 3]])

    add_prong(gap)
    add_prong(-gap)

    hinge_start = len(positions)
    positions.extend(
        [
            [-length - 0.15, -gap - width * 1.4, z - 0.055],
            [-length - 0.15, gap + width * 1.4, z - 0.055],
            [-length + 0.55, gap + width, z + 0.06],
            [-length + 0.55, -gap - width, z + 0.06],
        ]
    )
    triangles.extend([[hinge_start, hinge_start + 1, hinge_start + 2], [hinge_start, hinge_start + 2, hinge_start + 3]])
    return positions, triangles


def add_generated_surface(node, name, positions, triangles, color, mechanical=False, texture=None, texcoords=None, material=None, materials=None):
    child = node.addChild(name)
    child.addObject("TriangleSetTopologyContainer", name="topology", position=positions, triangles=triangles)
    child.addObject("TriangleSetTopologyModifier", name="modifier")
    child.addObject("TriangleSetGeometryAlgorithms", name="geometry")
    child.addObject("MechanicalObject", name="dofs", template="Vec3d", position=positions)

    if mechanical:
        # Tissue compliance parameters come from the profile's "materials"
        # section when provided; the fallbacks reproduce the previous
        # hard-coded values so callers that pass nothing are unchanged.
        params = materials or {}
        child.addObject(
            "UniformMass",
            totalMass=float(params.get("tissue_mass", 0.04)),
        )
        child.addObject(
            "TriangleFEMForceField",
            name="fem",
            youngModulus=float(params.get("tissue_young_modulus", 650.0)),
            poissonRatio=float(params.get("tissue_poisson_ratio", 0.43)),
            method="large",
        )
        child.addObject(
            "TriangularBendingSprings",
            name="bending",
            stiffness=float(params.get("tissue_bending_stiffness", 0.08)),
            damping=float(params.get("tissue_bending_damping", 0.02)),
        )

    visual_node = child.addChild("render")
    visual_kwargs = {
        "name": "visual",
        "color": color,
        "position": positions,
        "triangles": triangles,
        "updateNormals": True,
    }
    if texture:
        visual_kwargs["texturename"] = sofa_path(texture)
        visual_kwargs["srgbTexturing"] = True
    if texcoords:
        visual_kwargs["texcoords"] = texcoords
    if material:
        visual_kwargs["material"] = material
    visual = visual_node.addObject("OglModel", **visual_kwargs)
    visual_node.addObject("IdentityMapping", name="visual_mapping", input="@../dofs", output="@visual")
    return child, visual


def add_curve(node, name, positions, edges, color):
    child = node.addChild(name)
    child.addObject("EdgeSetTopologyContainer", name="topology", position=positions, edges=edges)
    child.addObject("MechanicalObject", name="dofs", template="Vec3d", position=positions)
    visual_node = child.addChild("render")
    visual = visual_node.addObject("OglModel", name="visual", color=color, position=positions, edges=edges)
    visual_node.addObject("IdentityMapping", name="visual_mapping", input="@../dofs", output="@visual")
    return child, visual
