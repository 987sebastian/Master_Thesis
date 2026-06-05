import os
import struct
import math

from .constants import EYE_MODEL_PATH, FORCEPS_MODEL_PATH, ROOT_DIR

def sofa_path(path):
    return os.path.abspath(path).replace("\\", "/")


def asset_path(path, fallback):
    if not path:
        return fallback
    if os.path.isabs(path):
        return path
    return os.path.join(ROOT_DIR, path)


def read_binary_stl_triangles(path):
    with open(path, "rb") as handle:
        header = handle.read(80)
        count_data = handle.read(4)
        if len(count_data) != 4:
            raise ValueError(f"Invalid STL file: {path}")
        triangle_count = struct.unpack("<I", count_data)[0]
        expected_size = 84 + triangle_count * 50
        actual_size = os.path.getsize(path)
        if actual_size < expected_size:
            raise ValueError(f"Truncated STL file: {path}")

        for _index in range(triangle_count):
            record = handle.read(50)
            values = struct.unpack("<12fH", record)
            yield values[3:6], values[6:9], values[9:12]


def stl_bounds(path):
    mins = [float("inf"), float("inf"), float("inf")]
    maxs = [float("-inf"), float("-inf"), float("-inf")]
    for triangle in read_binary_stl_triangles(path):
        for point in triangle:
            for axis, value in enumerate(point):
                mins[axis] = min(mins[axis], value)
                maxs[axis] = max(maxs[axis], value)
    if mins[0] == float("inf"):
        raise ValueError(f"Empty STL file: {path}")
    degenerate_axes = [
        axis_name
        for axis_name, low, high in zip(("X", "Y", "Z"), mins, maxs)
        if abs(high - low) <= 1.0e-9
    ]
    if degenerate_axes:
        axes = ", ".join(degenerate_axes)
        raise ValueError(f"Degenerate STL bounds on {axes} axis for {path}")
    return mins, maxs


def rotate_point(point, rotation):
    rx = math.radians(float(rotation[0]))
    ry = math.radians(float(rotation[1]))
    rz = math.radians(float(rotation[2]))

    x, y, z = float(point[0]), float(point[1]), float(point[2])
    y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
    x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
    x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
    return [x, y, z]


def transform_stl_point(point, scale, rotation, translation):
    rotated = rotate_point(point, rotation)
    return [
        rotated[0] * scale + float(translation[0]),
        rotated[1] * scale + float(translation[1]),
        rotated[2] * scale + float(translation[2]),
    ]


def load_stl_mesh(path, transform_vertex=None, max_triangles=None, triangle_filter=None):
    positions = []
    triangles = []
    vertex_indices = {}
    triangle_limit = max_triangles if max_triangles and max_triangles > 0 else None

    for source_index, triangle in enumerate(read_binary_stl_triangles(path)):
        if triangle_limit and source_index >= triangle_limit:
            break
        if triangle_filter and not triangle_filter(triangle):
            continue
        face = []
        for point in triangle:
            vertex = transform_vertex(point) if transform_vertex else [point[0], point[1], point[2]]
            key = (round(vertex[0], 6), round(vertex[1], 6), round(vertex[2], 6))
            if key not in vertex_indices:
                vertex_indices[key] = len(positions)
                positions.append(vertex)
            face.append(vertex_indices[key])
        if len(set(face)) == 3:
            triangles.append(face)

    if not positions or not triangles:
        raise ValueError(f"No triangles loaded from STL file: {path}")
    return positions, triangles


def load_forceps_model_mesh(settings):
    path = asset_path(settings.get("path"), FORCEPS_MODEL_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    source_tip_x = float(settings.get("source_tip_x", -142.0))
    source_rear_x = float(settings.get("source_rear_x", 165.2))
    tip_x = float(settings.get("tip_x", -0.16))
    length = float(settings.get("length", 9.2))
    z_offset = float(settings.get("z", 0.2))
    width_scale = float(settings.get("width_scale", 0.86))
    thickness_scale = float(settings.get("thickness_scale", 0.72))
    span = max(abs(source_rear_x - source_tip_x), 1.0e-6)
    scale = length / span

    def transform(point):
        x, y, z = point
        return [
            tip_x - (x - source_tip_x) * scale,
            y * scale * width_scale,
            z * scale * thickness_scale + z_offset,
        ]

    return load_stl_mesh(path, transform_vertex=transform, max_triangles=settings.get("max_triangles"))


def add_external_eye_model(node, settings):
    path = asset_path(settings.get("path"), EYE_MODEL_PATH)
    if not os.path.exists(path):
        return None

    scale = float(settings.get("scale", 1.0))
    source_center = settings.get("source_center", [3.260009288787842, 0.0, -0.0053253173828125])
    source_landmark = settings.get("source_landmark", source_center)
    target_origin = settings.get("target_origin", [0.0, 0.0, 0.0])
    rotation = settings.get("rotation", [0.0, 90.0, 0.0])
    translation = settings.get("translation")
    if translation is None:
        point = [float(source_landmark[0]), float(source_landmark[1]), float(source_landmark[2])]
        x, y, z = rotate_point(point, rotation)
        translation = [
            float(target_origin[0]) - x * scale,
            float(target_origin[1]) - y * scale,
            float(target_origin[2]) - z * scale,
        ]

    color = settings.get("color", [0.78, 0.50, 0.44, 0.10])
    material = settings.get(
        "material",
        "Default Diffuse 1 0.86 0.84 0.80 0.08 Ambient 1 0.12 0.10 0.09 1 Specular 1 0.35 0.20 0.16 1 Emissive 0 0 0 0 1 Shininess 1 18",
    )
    display_segment = str(settings.get("display_segment", "full")).strip().lower()
    segment_cut_source_x = float(settings.get("segment_cut_source_x", float(source_landmark[0])))

    child = node.addChild("anatomical_eye_model")

    if display_segment == "posterior":
        def keep_triangle(triangle):
            return min(point[0] for point in triangle) >= segment_cut_source_x

        positions, triangles = load_stl_mesh(
            path,
            transform_vertex=lambda point: transform_stl_point(point, scale, rotation, translation),
            max_triangles=settings.get("max_triangles"),
            triangle_filter=keep_triangle,
        )
        child.addObject("TriangleSetTopologyContainer", name="topology", position=positions, triangles=triangles)
        child.addObject("TriangleSetTopologyModifier", name="modifier")
        child.addObject("TriangleSetGeometryAlgorithms", name="geometry")
        child.addObject("MechanicalObject", name="dofs", template="Vec3d", position=positions)
        render = child.addChild("render")
        visual = render.addObject(
            "OglModel",
            name="visual",
            color=color,
            material=material,
            position=positions,
            triangles=triangles,
            updateNormals=True,
        )
        render.addObject("IdentityMapping", name="visual_mapping", input="@../dofs", output="@visual")
    else:
        child.addObject(
            "MeshSTLLoader",
            name="loader",
            filename=sofa_path(path),
            scale3d=[scale, scale, scale],
            translation=translation,
            rotation=rotation,
        )
        visual = child.addObject("OglModel", name="visual", src="@loader", color=color, material=material, updateNormals=True)
    return child, visual
