import math

from .geometry import generate_annulus, generate_disk


def normalize(vector):
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1.0e-9:
        return [0.0, 0.0, 1.0]
    return [component / length for component in vector]


def cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def cornea_surface_xy(anatomy, radius, angle):
    rx = anatomy["cornea_horizontal_diameter"] * 0.5
    ry = anatomy["cornea_vertical_diameter"] * 0.5
    x = radius * math.cos(angle)
    y = radius * math.sin(angle)
    ellipse_fraction = math.sqrt((x / max(rx, 1.0e-6)) ** 2 + (y / max(ry, 1.0e-6)) ** 2)
    if ellipse_fraction > 0.985:
        scale = 0.985 / ellipse_fraction
        x *= scale
        y *= scale
    return x, y


def cornea_surface_point(anatomy, x, y):
    rx = anatomy["cornea_horizontal_diameter"] * 0.5
    ry = anatomy["cornea_vertical_diameter"] * 0.5
    equivalent_radius = max(rx, ry)
    t = min(1.0, math.sqrt((x / max(rx, 1.0e-6)) ** 2 + (y / max(ry, 1.0e-6)) ** 2))
    anterior_apex_z = anatomy["cornea_posterior_apex_z"] + anatomy["cornea_central_thickness"]
    radial = equivalent_radius * t
    sag = anatomy["cornea_anterior_radius"] - math.sqrt(
        max(anatomy["cornea_anterior_radius"] ** 2 - radial * radial, 1.0e-6)
    )
    return [x, y, anterior_apex_z - sag]


def trocar_surface_frame(anatomy, controls):
    trocar_radius = float(controls.get("tool_trocar_radius", anatomy["cornea_horizontal_diameter"] * 0.48))
    trocar_angle = math.radians(float(controls.get("tool_trocar_angle_degrees", -38.0)))
    center_x, center_y = cornea_surface_xy(anatomy, trocar_radius, trocar_angle)
    center = cornea_surface_point(anatomy, center_x, center_y)

    sample_step = float(controls.get("trocar_visual_sample_step", 0.04))
    sample_x = cornea_surface_point(anatomy, *cornea_surface_xy(anatomy, trocar_radius + sample_step, trocar_angle))
    sample_y = cornea_surface_point(
        anatomy,
        *cornea_surface_xy(anatomy, trocar_radius, trocar_angle + sample_step / max(trocar_radius, 1.0)),
    )

    tangent_x = normalize([sample_x[index] - center[index] for index in range(3)])
    tangent_y = normalize([sample_y[index] - center[index] for index in range(3)])
    normal = normalize(cross(tangent_x, tangent_y))
    tangent_y = normalize(cross(normal, tangent_x))
    return center, normal, tangent_x, tangent_y


def trocar_entry_point(anatomy, controls):
    center, normal, _tangent_x, _tangent_y = trocar_surface_frame(anatomy, controls)
    surface_offset = float(
        controls.get(
            "tool_trocar_surface_offset",
            controls.get("trocar_visual_offset", 0.18),
        )
    )
    return [center[index] + normal[index] * surface_offset for index in range(3)]


def trocar_visual_entry_center(anatomy, controls):
    center, normal, _tangent_x, _tangent_y = trocar_surface_frame(anatomy, controls)
    visual_offset = float(controls.get("trocar_visual_offset", 0.18))
    return [center[index] + normal[index] * visual_offset for index in range(3)]


def _transform_local_mesh(center, normal, tangent_x, tangent_y, local_positions, local_offset):
    positions = []
    for local_x, local_y, local_z in local_positions:
        positions.append(
            [
                center[0] + normal[0] * (local_offset + local_z) + tangent_x[0] * local_x + tangent_y[0] * local_y,
                center[1] + normal[1] * (local_offset + local_z) + tangent_x[1] * local_x + tangent_y[1] * local_y,
                center[2] + normal[2] * (local_offset + local_z) + tangent_x[2] * local_x + tangent_y[2] * local_y,
            ]
        )
    return positions


def trocar_visual_mesh(anatomy, controls):
    center, normal, tangent_x, tangent_y = trocar_surface_frame(anatomy, controls)

    visual_radius = float(controls.get("trocar_visual_radius", 1.1))
    visual_offset = float(controls.get("trocar_visual_offset", 0.18))
    disk_positions, disk_triangles, _ = generate_disk(visual_radius, 5, 48, z=0.0)
    positions = _transform_local_mesh(center, normal, tangent_x, tangent_y, disk_positions, visual_offset)
    texcoords = []
    for local_x, local_y, _local_z in disk_positions:
        texcoords.append(
            [
                0.5 + local_x / max(visual_radius * 2.0, 1.0e-6),
                0.5 + local_y / max(visual_radius * 2.0, 1.0e-6),
            ]
        )
    return positions, disk_triangles, texcoords


def trocar_ring_mesh(anatomy, controls):
    center, normal, tangent_x, tangent_y = trocar_surface_frame(anatomy, controls)
    visual_radius = float(controls.get("trocar_visual_radius", 1.1))
    ring_inner = float(controls.get("trocar_ring_inner_radius", visual_radius * 0.78))
    ring_outer = float(controls.get("trocar_ring_outer_radius", visual_radius * 1.24))
    ring_offset = float(controls.get("trocar_ring_offset", 0.13))
    ring_positions, ring_triangles, _ = generate_annulus(ring_inner, ring_outer, 2, 48, z=0.0)
    positions = _transform_local_mesh(center, normal, tangent_x, tangent_y, ring_positions, ring_offset)
    return positions, ring_triangles
