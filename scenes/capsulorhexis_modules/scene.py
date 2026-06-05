import math
import os

try:
    import Sofa
    import Sofa.Core
except Exception:
    Sofa = None

from .assets import add_external_eye_model, load_forceps_model_mesh
from .constants import SIMULATOR_TEXTURE_MODE, TROCAR_TEXTURE_PATH
from .controller import CapsulorhexisController
from .geometry import (
    add_curve,
    add_generated_surface,
    annular_texcoords,
    generate_anterior_chamber_surface,
    generate_annulus,
    generate_capsule_annulus,
    generate_ciliary_body,
    generate_ciliary_processes,
    generate_cornea_shell,
    generate_curve,
    generate_domed_disk,
    generate_ellipse_curve,
    generate_flap_disk,
    flap_seam_lips,
    generate_forceps,
    generate_iris_sheet,
    generate_lens_shell,
    generate_radial_strokes,
    generate_sclera_shell,
    generate_scleral_vessels,
    generate_vessel_ribbons,
    generate_vitreous_cavity_outline,
    generate_zonule_fibers,
    planar_texcoords,
)
from .profile import load_profile
from .textures import ensure_texture_assets, resolve_sclera_surface_texture, using_rich_layered_textures, using_simulator_textures
from .trocar import trocar_ring_mesh, trocar_visual_entry_center, trocar_visual_mesh


def _anatomy(profile):
    g = profile["geometry"]
    lens_thickness = float(g.get("lens_thickness", 4.0))
    iris_front_z = float(g.get("iris_front_z", lens_thickness * 0.5 + 1.25))
    iris_thickness = float(g.get("iris_thickness", 0.6))
    posterior_chamber_z = (iris_front_z - iris_thickness + lens_thickness * 0.5) * 0.5
    pupil_radius = float(g.get("pupil_diameter", 3.5)) * 0.5
    return {
        "segments": int(g.get("capsule_segments", 216)),
        "lens_radius": float(g.get("lens_radius", 4.75)),
        "lens_thickness": lens_thickness,
        "lens_front_z": lens_thickness * 0.5,
        "lens_back_z": -lens_thickness * 0.5,
        "iris_inner_radius": float(g.get("iris_inner_radius", pupil_radius)),
        "iris_outer_radius": float(g.get("iris_outer_radius", 6.0)),
        "iris_front_z": iris_front_z,
        "iris_thickness": iris_thickness,
        "posterior_chamber_z": posterior_chamber_z,
        "cornea_horizontal_diameter": float(g.get("cornea_horizontal_diameter", 11.7)),
        "cornea_vertical_diameter": float(g.get("cornea_vertical_diameter", 10.6)),
        "cornea_central_thickness": float(g.get("cornea_central_thickness", 0.53)),
        "cornea_edge_thickness": float(g.get("cornea_edge_thickness", 0.67)),
        "cornea_anterior_radius": float(g.get("cornea_anterior_radius", 7.8)),
        "cornea_posterior_radius": float(g.get("cornea_posterior_radius", 6.5)),
        "cornea_posterior_apex_z": float(g.get("cornea_posterior_apex_z", iris_front_z + 3.0)),
        "ciliary_inner_radius": float(g.get("ciliary_inner_radius", 5.05)),
        "ciliary_outer_radius": float(g.get("ciliary_outer_radius", 6.1)),
        "ciliary_front_z": float(g.get("ciliary_front_z", iris_front_z - 0.9)),
        "ciliary_thickness": float(g.get("ciliary_thickness", 1.5)),
        "sclera_outer_radius": float(g.get("sclera_outer_radius", 12.0)),
        "sclera_posterior_z": float(g.get("sclera_posterior_z", -4.2)),
    }


def _limbus_z(anatomy):
    cornea_rx = anatomy["cornea_horizontal_diameter"] * 0.5
    cornea_ry = anatomy["cornea_vertical_diameter"] * 0.5
    cornea_front_apex_z = anatomy["cornea_posterior_apex_z"] + anatomy["cornea_central_thickness"]
    cornea_edge_sag = anatomy["cornea_anterior_radius"] - math.sqrt(
        max(anatomy["cornea_anterior_radius"] ** 2 - max(cornea_rx, cornea_ry) ** 2, 1.0e-6)
    )
    return cornea_front_apex_z - cornea_edge_sag - anatomy["cornea_edge_thickness"] * 0.35


def _vector3_setting(value, fallback):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            pass
    return [float(fallback[0]), float(fallback[1]), float(fallback[2])]


def _camera_preset(setting, fallback):
    setting = setting if isinstance(setting, dict) else {}
    return {
        "position": _vector3_setting(setting.get("position"), fallback["position"]),
        "lookAt": _vector3_setting(setting.get("lookAt", setting.get("look_at")), fallback["lookAt"]),
        "fieldOfView": float(setting.get("fieldOfView", setting.get("field_of_view", fallback["fieldOfView"]))),
    }


def _view_settings(profile):
    geometry = profile.get("geometry", {})
    capsule_z = float(geometry.get("anterior_capsule_z", 2.0))
    view = profile.get("view", {})
    overview_default = {
        "position": [0.0, -0.25, 32.0],
        "lookAt": [0.0, 0.0, 0.0],
        "fieldOfView": 36.0,
    }
    top_default = {
        "position": [0.0, 0.0, capsule_z + 18.0],
        "lookAt": [0.0, 0.0, capsule_z],
        "fieldOfView": 26.0,
    }
    overview_setting = view.get("overview", view.get("overall", {}))
    top_setting = view.get("top", {})
    return {
        "mode": str(view.get("mode", "overview")).strip().lower(),
        "overview": _camera_preset(overview_setting, overview_default),
        "top": _camera_preset(top_setting, top_default),
    }


def _add_sofa_basics(root, simulation, view_settings):
    root.dt = simulation["dt"]
    root.gravity = simulation["gravity"]
    root.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    root.addObject("RequiredPlugin", name="Sofa.Component.Constraint.Projective")
    root.addObject("RequiredPlugin", name="Sofa.Component.IO.Mesh")
    root.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Iterative")
    root.addObject("RequiredPlugin", name="Sofa.Component.Mapping.Linear")
    root.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    root.addObject("RequiredPlugin", name="Sofa.Component.MechanicalLoad")
    root.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    root.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    root.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.Spring")
    root.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    root.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Dynamic")
    root.addObject("RequiredPlugin", name="Sofa.Component.Visual")
    root.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering2D")
    root.addObject("RequiredPlugin", name="Sofa.GL.Component.Shader")
    root.addObject("RequiredPlugin", name="Sofa.GL.Component.Rendering3D")
    root.addObject("VisualStyle", displayFlags="showVisualModels showBehaviorModels hideCollisionModels hideMappings")
    root.addObject("RequiredPlugin", name="Tearing")
    status_label = root.addObject(
        "OglLabel",
        name="capsulorhexis_status_label",
        label="Tip-Capsule: -- mm | Grip: -- | State: --",
        fontsize=18,
        x=18,
        y=18,
        color="0.88 1.0 0.84",
    )
    initial_mode = "top" if view_settings.get("mode") == "top" else "overview"
    initial_camera = view_settings.get(initial_mode, view_settings["overview"])
    microscope_camera = root.addObject(
        "InteractiveCamera",
        name="microscope_camera",
        position=initial_camera["position"],
        lookAt=initial_camera["lookAt"],
        fieldOfView=initial_camera["fieldOfView"],
    )
    root.addObject("LightManager", ambient="0.17 0.14 0.13")
    root.addObject("SpotLight", name="coaxial_microscope_light", color="1.0 0.94 0.84", position=[0.0, 0.0, 18.0], direction=[0.0, 0.0, -1.0], cutoff=34, exponent=2)
    root.addObject("SpotLight", name="oblique_specular_light", color="0.68 0.78 1.0", position=[-8.0, -10.0, 11.0], direction=[0.55, 0.62, -1.0], cutoff=28, exponent=6)
    root.addObject("DefaultAnimationLoop")
    root.addObject("EulerImplicitSolver", name="timeIntegrator", rayleighMass=0.02, rayleighStiffness=0.05)
    root.addObject("CGLinearSolver", name="linearSolver", iterations=40, tolerance=1.0e-7, threshold=1.0e-9)
    return microscope_camera, status_label


def createScene(root):
    if Sofa is None:
        raise RuntimeError("This scene must be loaded with runSofa and SofaPython3.")

    profile = load_profile()
    textures = ensure_texture_assets()
    sclera_surface_texture = resolve_sclera_surface_texture(textures)
    use_layered_textures = using_rich_layered_textures(textures)
    use_simulator_texture_layers = using_simulator_textures(textures)
    geometry = profile["geometry"]
    simulation = profile["simulation"]
    view_settings = _view_settings(profile)
    assets = profile.get("assets", {})
    controls = profile.get("controls", {})
    visuals = profile.get("visuals", {})
    anatomy_view_transparent = bool(visuals.get("transparent_anatomy_view", True))
    anatomy = _anatomy(profile)
    segments = anatomy["segments"]
    cornea_rx = anatomy["cornea_horizontal_diameter"] * 0.5
    cornea_ry = anatomy["cornea_vertical_diameter"] * 0.5
    limbus_z = _limbus_z(anatomy)
    texture_radius = max(cornea_rx, cornea_ry)

    satin_material = "texture Diffuse 1 0.86 0.76 0.70 0.22 Ambient 1 0.18 0.16 0.14 1 Specular 1 0.02 0.02 0.02 1 Emissive 0 0 0 0 1 Shininess 1 4" if anatomy_view_transparent else "texture Diffuse 1 0.86 0.76 0.70 0.90 Ambient 1 0.30 0.25 0.22 1 Specular 1 0.18 0.14 0.11 1 Emissive 0 0 0 0 1 Shininess 1 18"
    limbus_material = "texture Diffuse 1 0.84 0.62 0.54 0.18 Ambient 1 0.08 0.07 0.06 1 Specular 1 0.02 0.02 0.02 1 Emissive 0 0 0 0 1 Shininess 1 4" if anatomy_view_transparent else "texture Diffuse 1 0.84 0.62 0.54 0.52 Ambient 1 0.10 0.08 0.07 1 Specular 1 0.24 0.16 0.14 1 Emissive 0 0 0 0 1 Shininess 1 28"
    cornea_material = "Default Diffuse 1 0.62 0.88 1.0 0.05 Ambient 1 0.03 0.05 0.06 1 Specular 1 0.10 0.10 0.10 1 Emissive 0 0 0 0 1 Shininess 1 20" if anatomy_view_transparent else "Default Diffuse 1 0.62 0.88 1.0 0.16 Ambient 1 0.04 0.07 0.08 1 Specular 1 1 1 0.95 1 Emissive 0 0 0 0 1 Shininess 1 160"
    aqueous_material = "Default Diffuse 1 0.60 0.85 1.0 0.03 Ambient 1 0.02 0.03 0.04 1 Specular 1 0.06 0.08 0.10 1 Emissive 0 0 0 0 1 Shininess 1 10" if anatomy_view_transparent else "Default Diffuse 1 0.60 0.85 1.0 0.07 Ambient 1 0.02 0.04 0.05 1 Specular 1 0.45 0.70 1.0 0.22 1 Emissive 0 0 0 0 1 Shininess 1 60"
    iris_material = "texture Diffuse 1 0.30 0.34 0.34 1 Ambient 1 0.045 0.055 0.055 1 Specular 1 0.10 0.13 0.14 1 Emissive 0 0 0 0 1 Shininess 1 16"
    ciliary_material = "Default Diffuse 1 0.44 0.30 0.24 1 Ambient 1 0.08 0.05 0.04 1 Specular 1 0.12 0.08 0.06 1 Emissive 0 0 0 0 1 Shininess 1 18"
    lens_material = "Default Diffuse 1 0.86 0.94 1.0 0.14 Ambient 1 0.10 0.12 0.13 1 Specular 1 0.10 0.10 0.12 1 Emissive 0 0 0 0 1 Shininess 1 18" if anatomy_view_transparent else "Default Diffuse 1 0.86 0.94 1.0 0.25 Ambient 1 0.12 0.15 0.16 1 Specular 1 0.95 0.98 1.0 0.70 1 Emissive 0 0 0 0 1 Shininess 1 110"
    retro_material = "texture Diffuse 1 0.96 0.34 0.24 0.42 Ambient 1 0.12 0.05 0.04 1 Specular 1 0.55 0.26 0.18 1 Emissive 0 0 0 0 1 Shininess 1 48"
    lens_surface_material = "texture Diffuse 1 0.96 0.70 0.48 0.28 Ambient 1 0.12 0.08 0.05 1 Specular 1 0.90 0.72 0.56 1 Emissive 0 0 0 0 1 Shininess 1 80"
    cortex_material = "texture Diffuse 1 0.92 0.54 0.30 0.18 Ambient 1 0.10 0.05 0.03 1 Specular 1 0.58 0.34 0.22 1 Emissive 0 0 0 0 1 Shininess 1 54"
    nucleus_material = "texture Diffuse 1 0.78 0.34 0.16 0.20 Ambient 1 0.09 0.03 0.02 1 Specular 1 0.38 0.22 0.14 1 Emissive 0 0 0 0 1 Shininess 1 42"
    posterior_capsule_material = "texture Diffuse 1 0.88 0.72 0.58 0.12 Ambient 1 0.08 0.05 0.04 1 Specular 1 0.40 0.26 0.18 1 Emissive 0 0 0 0 1 Shininess 1 36"
    capsule_material = "texture Diffuse 1 0.82 0.08 0.10 0.46 Ambient 1 0.18 0.02 0.04 1 Specular 1 0.76 0.48 0.42 1 Emissive 0 0 0 0 1 Shininess 1 58"
    flap_material = "texture Diffuse 1 0.98 0.34 0.08 0.72 Ambient 1 0.20 0.06 0.01 1 Specular 1 0.95 0.65 0.45 1 Emissive 0 0 0 0 1 Shininess 1 76"
    metal_material = "texture Diffuse 1 0.72 0.75 0.78 1 Ambient 1 0.35 0.35 0.37 1 Specular 1 1 1 1 1 Emissive 0 0 0 0 1 Shininess 1 110"

    microscope_camera, status_label = _add_sofa_basics(root, simulation, view_settings)

    eye_model_node = None
    if assets.get("use_external_eye_model", False):
        try:
            external_eye = add_external_eye_model(root, assets.get("eye_model", {}))
            if external_eye:
                eye_model_node = external_eye[0]
        except Exception as error:
            print(f"external eye model disabled: {error}")
    if eye_model_node is None:
        eye_model_node = root.addChild("procedural_anterior_eye")
    anterior_segment = eye_model_node.addChild("anterior_segment")

    sclera_positions, sclera_triangles, _ = generate_sclera_shell(
        inner_radius=cornea_rx,
        outer_radius=anatomy["sclera_outer_radius"],
        inner_z=limbus_z,
        posterior_z=anatomy["sclera_posterior_z"],
        rings=12,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "anterior_sclera_shell",
        sclera_positions,
        sclera_triangles,
        [0.98, 0.91, 0.84, 0.90],
        texture=sclera_surface_texture,
        texcoords=planar_texcoords(sclera_positions, texture_radius),
        material=satin_material,
    )

    if use_simulator_texture_layers and "limbus" in textures:
        limbus_layer_positions, limbus_layer_triangles, _ = generate_annulus(
            cornea_ry * 0.96,
            cornea_rx * 1.03,
            3,
            segments,
            z=limbus_z + 0.02,
        )
        add_generated_surface(
            anterior_segment,
            "limbus_texture_layer",
            limbus_layer_positions,
            limbus_layer_triangles,
            [1.0, 1.0, 1.0, 0.56],
            texture=textures["limbus"],
            texcoords=annular_texcoords(limbus_layer_positions, cornea_ry * 0.96, cornea_rx * 1.03, texture_inner=0.44, texture_outer=1.0),
            material=limbus_material,
        )

    if not use_layered_textures:
        vessel_positions, vessel_triangles = generate_vessel_ribbons(
            anatomy["iris_outer_radius"],
            anatomy["sclera_outer_radius"] * 0.96,
            branches=72,
            z=limbus_z + 0.06,
            width=0.075,
        )
        add_generated_surface(
            anterior_segment,
            "scleral_vessel_ribbons",
            vessel_positions,
            vessel_triangles,
            [0.70, 0.02, 0.03, 0.46],
            material="Default Diffuse 1 0.76 0.03 0.04 0.48 Ambient 1 0.16 0 0 1 Specular 1 0.25 0.10 0.08 1 Emissive 0 0 0 0 1 Shininess 1 24",
        )
        micro_vessel_positions, micro_vessel_edges = generate_scleral_vessels(
            anatomy["iris_outer_radius"],
            anatomy["sclera_outer_radius"] * 0.96,
            branches=96,
            z=limbus_z + 0.10,
        )
        add_curve(anterior_segment, "scleral_micro_vessels", micro_vessel_positions, micro_vessel_edges, [0.58, 0.02, 0.03, 0.32])

    limbus_positions, limbus_edges = generate_ellipse_curve(cornea_rx, cornea_ry, segments, z=limbus_z + 0.04)
    add_curve(anterior_segment, "limbus_transition_ring", limbus_positions, limbus_edges, [0.72, 0.62, 0.54, 0.58])

    cornea_positions, cornea_triangles = generate_cornea_shell(
        horizontal_diameter=anatomy["cornea_horizontal_diameter"],
        vertical_diameter=anatomy["cornea_vertical_diameter"],
        central_thickness=anatomy["cornea_central_thickness"],
        edge_thickness=anatomy["cornea_edge_thickness"],
        anterior_radius=anatomy["cornea_anterior_radius"],
        posterior_radius=anatomy["cornea_posterior_radius"],
        posterior_apex_z=anatomy["cornea_posterior_apex_z"],
        rings=16,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "transparent_cornea",
        cornea_positions,
        cornea_triangles,
        [0.62, 0.88, 1.0, 0.16],
        material=cornea_material,
    )

    if os.path.exists(TROCAR_TEXTURE_PATH):
        trocar_ring_positions, trocar_ring_triangles = trocar_ring_mesh(anatomy, controls)
        add_generated_surface(
            anterior_segment,
            "trocar_ring",
            trocar_ring_positions,
            trocar_ring_triangles,
            [0.08, 0.62, 0.70, 0.96],
            material="Default Diffuse 1 0.08 0.62 0.70 0.96 Ambient 1 0.04 0.18 0.20 1 Specular 1 0.20 0.54 0.58 1 Emissive 0 0 0 0 1 Shininess 1 60",
        )
        trocar_positions, trocar_triangles, trocar_texcoords = trocar_visual_mesh(anatomy, controls)
        add_generated_surface(
            anterior_segment,
            "trocar_port",
            trocar_positions,
            trocar_triangles,
            [1.0, 1.0, 1.0, 0.98],
            texture=TROCAR_TEXTURE_PATH,
            texcoords=trocar_texcoords,
            material="texture Diffuse 1 1 1 1 1 Ambient 1 0.18 0.18 0.18 1 Specular 1 0.24 0.24 0.24 1 Emissive 0 0 0 0 1 Shininess 1 36",
        )

    if use_simulator_texture_layers and visuals.get("show_corneal_reflection", False) and "corneal_reflection" in textures:
        add_generated_surface(
            anterior_segment,
            "corneal_reflection_texture_layer",
            cornea_positions,
            cornea_triangles,
            [1.0, 1.0, 1.0, 0.22],
            texture=textures["corneal_reflection"],
            texcoords=planar_texcoords(cornea_positions, texture_radius),
            material="texture Diffuse 1 0.75 0.88 1.0 0.18 Ambient 1 0.04 0.05 0.06 1 Specular 1 1 1 1 1 Emissive 0 0 0 0 1 Shininess 1 140",
        )

    chamber_positions, chamber_triangles = generate_anterior_chamber_surface(
        radius=anatomy["iris_outer_radius"] * 0.92,
        apex_z=anatomy["cornea_posterior_apex_z"] - 0.05,
        iris_z=anatomy["iris_front_z"] + 0.04,
        rings=10,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "anterior_chamber_aqueous_space",
        chamber_positions,
        chamber_triangles,
        [0.50, 0.82, 1.0, 0.07],
        material=aqueous_material,
    )

    iris_positions, iris_triangles, _ = generate_iris_sheet(
        anatomy["iris_inner_radius"],
        anatomy["iris_outer_radius"],
        thickness=anatomy["iris_thickness"],
        front_z=anatomy["iris_front_z"],
        rings=10,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "iris_with_pupil_opening",
        iris_positions,
        iris_triangles,
        [0.16, 0.20, 0.20, 1.0],
        material=iris_material,
    )

    iris_front_positions, iris_front_triangles, _ = generate_annulus(
        anatomy["iris_inner_radius"],
        anatomy["iris_outer_radius"],
        8,
        segments,
        z=anatomy["iris_front_z"] + 0.06,
    )
    add_generated_surface(
        anterior_segment,
        "iris_front_texture_layer",
        iris_front_positions,
        iris_front_triangles,
        [1.0, 1.0, 1.0, 1.0],
        texture=textures["iris"],
        texcoords=annular_texcoords(
            iris_front_positions,
            anatomy["iris_inner_radius"],
            anatomy["iris_outer_radius"],
            texture_inner=0.43 / 0.66,
            texture_outer=1.0,
        ),
        material="texture Diffuse 1 1 1 1 1 Ambient 1 0.12 0.12 0.12 1 Specular 1 0.08 0.08 0.08 1 Emissive 0 0 0 0 1 Shininess 1 10",
    )

    iris_stroke_positions, iris_stroke_edges = generate_radial_strokes(
        anatomy["iris_inner_radius"] + 0.20,
        anatomy["iris_outer_radius"] * 0.97,
        180,
        z=anatomy["iris_front_z"] + 0.09,
        start_phase=0.15,
    )
    add_curve(anterior_segment, "iris_radial_fibers", iris_stroke_positions, iris_stroke_edges, [0.03, 0.045, 0.045, 0.42])
    sphincter_positions, sphincter_edges = generate_curve(anatomy["iris_inner_radius"] + 0.35, segments, z=anatomy["iris_front_z"] + 0.11)
    add_curve(anterior_segment, "iris_sphincter_ring", sphincter_positions, sphincter_edges, [0.05, 0.075, 0.07, 0.55])

    ciliary_positions, ciliary_triangles = generate_ciliary_body(
        inner_radius=anatomy["ciliary_inner_radius"],
        outer_radius=anatomy["ciliary_outer_radius"],
        front_z=anatomy["ciliary_front_z"],
        thickness=anatomy["ciliary_thickness"],
        rings=4,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "ciliary_body_ring",
        ciliary_positions,
        ciliary_triangles,
        [0.42, 0.28, 0.22, 1.0],
        material=ciliary_material,
    )

    process_positions, process_triangles = generate_ciliary_processes(
        base_radius=anatomy["ciliary_inner_radius"] + 0.28,
        tip_radius=anatomy["lens_radius"] + 0.22,
        front_z=anatomy["ciliary_front_z"] - 0.08,
        back_z=anatomy["ciliary_front_z"] - anatomy["ciliary_thickness"] + 0.25,
        count=72,
    )
    add_generated_surface(
        anterior_segment,
        "ciliary_processes",
        process_positions,
        process_triangles,
        [0.50, 0.32, 0.24, 1.0],
        material="Default Diffuse 1 0.50 0.32 0.24 1 Ambient 1 0.08 0.05 0.04 1 Specular 1 0.16 0.09 0.06 1 Emissive 0 0 0 0 1 Shininess 1 24",
    )

    posterior_positions, posterior_triangles, _ = generate_annulus(
        anatomy["iris_inner_radius"],
        anatomy["ciliary_inner_radius"],
        4,
        segments,
        z=anatomy["posterior_chamber_z"],
    )
    add_generated_surface(
        anterior_segment,
        "posterior_chamber_aqueous_space",
        posterior_positions,
        posterior_triangles,
        [0.50, 0.82, 1.0, 0.06],
        material=aqueous_material,
    )

    if use_simulator_texture_layers:
        retro_positions, retro_triangles, _ = generate_domed_disk(
            anatomy["lens_radius"] * 0.98,
            12,
            segments,
            anatomy["lens_front_z"] - 0.62,
            dome_height=0.22,
        )
        add_generated_surface(
            anterior_segment,
            "retroillumination_texture_layer",
            retro_positions,
            retro_triangles,
            [1.0, 0.42, 0.35, 0.42],
            texture=textures["retro"],
            texcoords=planar_texcoords(retro_positions, anatomy["lens_radius"]),
            material=retro_material,
        )

        lens_surface_positions, lens_surface_triangles, _ = generate_domed_disk(
            anatomy["lens_radius"] * 0.98,
            12,
            segments,
            anatomy["lens_front_z"] - 0.18,
            dome_height=0.18,
        )
        add_generated_surface(
            anterior_segment,
            "lens_surface_texture_layer",
            lens_surface_positions,
            lens_surface_triangles,
            [1.0, 0.82, 0.58, 0.28],
            texture=textures["lens_surface"],
            texcoords=planar_texcoords(lens_surface_positions, anatomy["lens_radius"]),
            material=lens_surface_material,
        )

        cortex_positions, cortex_triangles, _ = generate_domed_disk(
            anatomy["lens_radius"] * 0.74,
            10,
            segments,
            anatomy["lens_front_z"] - 1.02,
            dome_height=0.14,
        )
        add_generated_surface(
            anterior_segment,
            "cortex_texture_layer",
            cortex_positions,
            cortex_triangles,
            [1.0, 0.70, 0.45, 0.20],
            texture=textures["cortex"],
            texcoords=planar_texcoords(cortex_positions, anatomy["lens_radius"] * 0.74),
            material=cortex_material,
        )

        nucleus_positions, nucleus_triangles, _ = generate_domed_disk(
            anatomy["lens_radius"] * 0.52,
            8,
            segments,
            anatomy["lens_front_z"] - 1.36,
            dome_height=0.09,
        )
        add_generated_surface(
            anterior_segment,
            "nucleus_texture_layer",
            nucleus_positions,
            nucleus_triangles,
            [1.0, 0.60, 0.32, 0.20],
            texture=textures["nucleus"],
            texcoords=planar_texcoords(nucleus_positions, anatomy["lens_radius"] * 0.52),
            material=nucleus_material,
        )

        if "posterior_capsule" in textures:
            posterior_capsule_positions, posterior_capsule_triangles, _ = generate_domed_disk(
                anatomy["lens_radius"] * 0.98,
                12,
                segments,
                anatomy["lens_back_z"] + 0.18,
                dome_height=0.10,
            )
            add_generated_surface(
                anterior_segment,
                "posterior_capsule_texture_layer",
                posterior_capsule_positions,
                posterior_capsule_triangles,
                [1.0, 0.92, 0.84, 0.12],
                texture=textures["posterior_capsule"],
                texcoords=planar_texcoords(posterior_capsule_positions, anatomy["lens_radius"]),
                material=posterior_capsule_material,
            )

    lens_positions, lens_triangles = generate_lens_shell(
        radius=anatomy["lens_radius"],
        thickness=anatomy["lens_thickness"],
        rings=18,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "transparent_biconvex_lens",
        lens_positions,
        lens_triangles,
        [0.86, 0.94, 1.0, 0.25],
        material=lens_material,
    )

    cortex_positions, cortex_triangles = generate_lens_shell(
        radius=anatomy["lens_radius"] * 0.78,
        thickness=anatomy["lens_thickness"] * 0.72,
        rings=10,
        segments=segments,
    )
    add_generated_surface(
        anterior_segment,
        "subtle_lens_cortex",
        cortex_positions,
        cortex_triangles,
        [1.0, 0.88, 0.62, 0.10],
        material="Default Diffuse 1 1.0 0.86 0.55 0.10 Ambient 1 0.10 0.08 0.04 1 Specular 1 0.45 0.36 0.22 0.22 1 Emissive 0 0 0 0 1 Shininess 1 50",
    )

    if visuals.get("show_zonules", False):
        zonule_positions, zonule_edges = generate_zonule_fibers(
            ciliary_radius=anatomy["ciliary_inner_radius"],
            lens_radius=anatomy["lens_radius"],
            count=min(96, max(48, segments // 3)),
        )
        add_curve(anterior_segment, "zonular_fiber_bundles", zonule_positions, zonule_edges, [0.86, 0.94, 1.0, 0.10])

    if visuals.get("show_vitreous_outline", False):
        vitreous_positions, vitreous_edges = generate_vitreous_cavity_outline(segments=96)
        add_curve(anterior_segment, "empty_vitreous_cavity_outline", vitreous_positions, vitreous_edges, [0.40, 0.62, 0.86, 0.10])

    capsule_z = float(geometry.get("anterior_capsule_z", anatomy["lens_front_z"] + 0.055))
    capsule_positions, capsule_triangles, _fixed_boundary = generate_capsule_annulus(
        geometry["tear_radius"],
        geometry["capsule_outer_radius"],
        geometry["capsule_rings"],
        segments,
        capsule_z,
    )
    capsule, _capsule_visual = add_generated_surface(
        anterior_segment,
        "anterior_capsule",
        capsule_positions,
        capsule_triangles,
        [0.82, 0.10, 0.18, 0.46],
        mechanical=True,
        texture=textures["capsule"],
        texcoords=planar_texcoords(capsule_positions, geometry["capsule_outer_radius"]),
        material=capsule_material,
        materials=profile["materials"],
    )
    outer_start = geometry["capsule_rings"] * segments
    outer_indices = list(range(outer_start, outer_start + segments))
    capsule.addObject("FixedProjectiveConstraint", name="zonular_capsule_anchor", indices=outer_indices)
    capsule.addObject("DiagonalVelocityDampingForceField", dampingCoefficient=profile["materials"]["damping"])

    flap_seam_enabled = bool(simulation.get("flap_seam", False))
    flap_physics_enabled = bool(simulation.get("physics_flap", False))
    flap_seam_angle = math.radians(
        float(simulation.get("flap_seam_angle_degrees", simulation.get("tear_start_angle_degrees", -105.0)))
    )
    flap_seam_lip_indices = None
    if flap_seam_enabled:
        flap_positions, flap_triangles, flap_boundary = generate_flap_disk(
            geometry["tear_radius"],
            geometry["flap_rings"],
            segments,
            capsule_z + 0.045,
            seam_angle=flap_seam_angle,
        )
        flap_seam_lip_indices = flap_seam_lips(geometry["flap_rings"], segments)
    else:
        flap_positions, flap_triangles, flap_boundary = generate_flap_disk(
            geometry["tear_radius"],
            geometry["flap_rings"],
            segments,
            capsule_z + 0.045,
        )
    flap, flap_visual = add_generated_surface(
        anterior_segment,
        "capsular_flap",
        flap_positions,
        flap_triangles,
        [1.0, 0.45, 0.12, 0.72],
        mechanical=True,
        texture=textures["flap"],
        texcoords=planar_texcoords(flap_positions, geometry["tear_radius"]),
        material=flap_material,
        materials=profile["materials"],
    )
    flap.addObject("DiagonalVelocityDampingForceField", dampingCoefficient=profile["materials"]["damping"])

    # Anchor the flap rim so a free FEM disk does not drift, shrink, or bunch up
    # when a lip is pulled. Only the seam neighbourhood is left free: an arc of
    # flap_anchor_free_arc_degrees centred on the seam angle stays unpinned so
    # that lip can lift, while the rest of the rim is fixed. Only active when
    # both physics_flap and flap_seam are on, so other modes are unchanged.
    if flap_physics_enabled and flap_seam_enabled and flap_boundary:
        free_arc = math.radians(float(simulation.get("flap_anchor_free_arc_degrees", 80.0)))
        half_arc = max(free_arc, 0.0) * 0.5
        anchored = []
        for index in flap_boundary:
            px, py, _pz = flap_positions[index]
            angle = math.atan2(py, px)
            delta = angle - flap_seam_angle
            while delta <= -math.pi:
                delta += 2.0 * math.pi
            while delta > math.pi:
                delta -= 2.0 * math.pi
            if abs(delta) > half_arc:
                anchored.append(index)
        if anchored:
            flap.addObject("FixedProjectiveConstraint", name="flap_rim_anchor", indices=anchored)

    guide_positions, guide_edges = generate_curve(geometry["tear_radius"], segments, z=capsule_z + 0.11)
    _guide, guide_visual = add_curve(anterior_segment, "tear_guide", guide_positions, guide_edges, [1.0, 0.85, 0.22, 1.0])

    tear_edge_positions, tear_edge_edges = generate_curve(geometry["tear_radius"] * 1.012, segments, z=capsule_z + 0.17)
    tear_edge, tear_edge_visual = add_curve(anterior_segment, "irregular_capsulotomy_edge", tear_edge_positions, tear_edge_edges, [1.0, 0.34, 0.04, 0.72])
    tear_start_angle = math.radians(float(simulation.get("tear_start_angle_degrees", -105.0)))
    tear_progress_start = [
        geometry["tear_radius"] * 1.035 * math.cos(tear_start_angle),
        geometry["tear_radius"] * 1.035 * math.sin(tear_start_angle),
        capsule_z + 0.27,
    ]
    tear_progress_positions = [list(tear_progress_start) for _ in range(segments + 1)]
    tear_progress_edges = [[index, index + 1] for index in range(segments)]
    tear_progress_arc, tear_progress_visual = add_curve(
        anterior_segment,
        "active_tear_progress_arc",
        tear_progress_positions,
        tear_progress_edges,
        [0.10, 1.0, 0.42, 0.95],
    )
    if bool(simulation.get("show_traction_line", True)):
        traction_line_positions = [list(tear_progress_start), list(tear_progress_start)]
        traction_line, traction_line_visual = add_curve(
            anterior_segment,
            "forceps_traction_line",
            traction_line_positions,
            [[0, 1]],
            [1.0, 0.74, 0.16, 0.80],
        )
    else:
        traction_line = None
        traction_line_visual = None

    forceps_settings = assets.get("forceps_model", {})
    if assets.get("use_external_forceps_model", True):
        try:
            tool_positions, tool_triangles = load_forceps_model_mesh(forceps_settings)
        except Exception as error:
            print(f"external forceps model disabled: {error}")
            tool_positions, tool_triangles = generate_forceps()
    else:
        tool_positions, tool_triangles = generate_forceps()
    tool_xs = [point[0] for point in tool_positions] or [-0.16]
    tool_span = max(tool_xs) - min(tool_xs)
    estimated_tip = CapsulorhexisController._estimate_tool_tip_reference(tool_positions, forceps_settings)
    tool_tip = [
        float(forceps_settings.get("tip_x", estimated_tip[0])),
        float(forceps_settings.get("tip_y", estimated_tip[1])),
        float(forceps_settings.get("tip_z", estimated_tip[2])),
    ]
    tool_length = float(forceps_settings.get("length", max(tool_span, 1.0)))
    grip_length = float(forceps_settings.get("grip_length", min(1.8, max(tool_length * 0.22, 0.2))))
    grip_end_x = float(forceps_settings.get("grip_end_x", tool_tip[0]))
    grip_start_x = float(forceps_settings.get("grip_start_x", grip_end_x - grip_length))
    tear_start_angle = math.radians(float(simulation.get("tear_start_angle_degrees", -105.0)))
    initial_target = list(
        controls.get(
            "tool_target_origin",
            [
                float(geometry["tear_radius"]) * math.cos(tear_start_angle),
                float(geometry["tear_radius"]) * math.sin(tear_start_angle),
                capsule_z + 0.12,
            ],
        )
    )
    initial_trocar_point = list(controls.get("tool_trocar_point", trocar_visual_entry_center(anatomy, controls)))
    initial_tool_positions = CapsulorhexisController.pose_tool_positions(
        tool_positions,
        initial_target,
        initial_trocar_point,
        tool_tip,
        tool_roll=math.radians(float(controls.get("tool_roll_degrees", 0.0))),
        grip_start_x=grip_start_x,
        grip_end_x=grip_end_x,
    )
    tool, tool_visual = add_generated_surface(
        root,
        "forceps",
        initial_tool_positions,
        tool_triangles,
        [0.88, 0.92, 0.96, 1.0],
        texture=textures["metal"],
        texcoords=planar_texcoords(tool_positions, radius=float(forceps_settings.get("length", 9.2)), repeat=1.8),
        material=metal_material,
    )

    controller = CapsulorhexisController(
        profile,
        flap,
        flap_visual,
        guide_visual,
        tool,
        tool_visual,
        flap_positions,
        tool_positions,
        camera=microscope_camera,
        status_label=status_label,
        tear_progress_node=tear_progress_arc,
        tear_progress_visual=tear_progress_visual,
        tear_edge_node=tear_edge,
        tear_edge_visual=tear_edge_visual,
        traction_line_node=traction_line,
        traction_line_visual=traction_line_visual,
        view_settings=view_settings,
        flap_seam_lips=flap_seam_lip_indices,
    )
    root.addObject(controller)
    return root


def dry_run():
    profile = load_profile()
    textures = ensure_texture_assets()
    use_simulator_texture_layers = using_simulator_textures(textures)
    g = profile["geometry"]
    assets = profile.get("assets", {})
    controls = profile.get("controls", {})
    visuals = profile.get("visuals", {})
    anatomy = _anatomy(profile)
    segments = anatomy["segments"]
    cornea_rx = anatomy["cornea_horizontal_diameter"] * 0.5
    cornea_ry = anatomy["cornea_vertical_diameter"] * 0.5
    limbus_z = _limbus_z(anatomy)
    cornea_front_apex_z = anatomy["cornea_posterior_apex_z"] + anatomy["cornea_central_thickness"]
    capsule_z = float(g.get("anterior_capsule_z", anatomy["lens_front_z"] + 0.055))

    if assets.get("use_external_forceps_model", True):
        try:
            forceps_mesh = load_forceps_model_mesh(assets.get("forceps_model", {}))
        except Exception as error:
            print(f"forceps STL fallback: {error}")
            forceps_mesh = generate_forceps()
    else:
        forceps_mesh = generate_forceps()

    meshes = {
        "transparent_cornea": generate_cornea_shell(
            horizontal_diameter=anatomy["cornea_horizontal_diameter"],
            vertical_diameter=anatomy["cornea_vertical_diameter"],
            central_thickness=anatomy["cornea_central_thickness"],
            edge_thickness=anatomy["cornea_edge_thickness"],
            anterior_radius=anatomy["cornea_anterior_radius"],
            posterior_radius=anatomy["cornea_posterior_radius"],
            posterior_apex_z=anatomy["cornea_posterior_apex_z"],
            rings=16,
            segments=segments,
        ),
        "anterior_sclera_shell": generate_sclera_shell(
            inner_radius=cornea_rx,
            outer_radius=anatomy["sclera_outer_radius"],
            inner_z=limbus_z,
            posterior_z=anatomy["sclera_posterior_z"],
            rings=12,
            segments=segments,
        )[:2],
        "anterior_chamber_aqueous_space": generate_anterior_chamber_surface(
            radius=anatomy["iris_outer_radius"] * 0.92,
            apex_z=anatomy["cornea_posterior_apex_z"] - 0.05,
            iris_z=anatomy["iris_front_z"] + 0.04,
            rings=10,
            segments=segments,
        ),
        "iris_with_pupil_opening": generate_iris_sheet(
            anatomy["iris_inner_radius"],
            anatomy["iris_outer_radius"],
            thickness=anatomy["iris_thickness"],
            front_z=anatomy["iris_front_z"],
            rings=10,
            segments=segments,
        )[:2],
        "iris_front_texture_layer": generate_annulus(
            anatomy["iris_inner_radius"],
            anatomy["iris_outer_radius"],
            8,
            segments,
            z=anatomy["iris_front_z"] + 0.06,
        )[:2],
        "ciliary_body_ring": generate_ciliary_body(
            inner_radius=anatomy["ciliary_inner_radius"],
            outer_radius=anatomy["ciliary_outer_radius"],
            front_z=anatomy["ciliary_front_z"],
            thickness=anatomy["ciliary_thickness"],
            rings=4,
            segments=segments,
        ),
        "ciliary_processes": generate_ciliary_processes(
            base_radius=anatomy["ciliary_inner_radius"] + 0.28,
            tip_radius=anatomy["lens_radius"] + 0.22,
            front_z=anatomy["ciliary_front_z"] - 0.08,
            back_z=anatomy["ciliary_front_z"] - anatomy["ciliary_thickness"] + 0.25,
            count=72,
        ),
        "posterior_chamber_aqueous_space": generate_annulus(
            anatomy["iris_inner_radius"],
            anatomy["ciliary_inner_radius"],
            4,
            segments,
            z=anatomy["posterior_chamber_z"],
        )[:2],
        "transparent_biconvex_lens": generate_lens_shell(
            radius=anatomy["lens_radius"],
            thickness=anatomy["lens_thickness"],
            rings=18,
            segments=segments,
        ),
        "anterior_capsule": generate_capsule_annulus(
            g["tear_radius"],
            g["capsule_outer_radius"],
            g["capsule_rings"],
            segments,
            capsule_z,
        )[:2],
        "capsular_flap": generate_flap_disk(g["tear_radius"], g["flap_rings"], segments, capsule_z + 0.045)[:2],
        "forceps": forceps_mesh,
        "trocar_ring": trocar_ring_mesh(anatomy, controls),
        "trocar_port": trocar_visual_mesh(anatomy, controls)[:2],
    }

    curves = {
        "limbus_transition_ring": generate_ellipse_curve(cornea_rx, cornea_ry, segments, z=limbus_z + 0.04),
        "iris_radial_fibers": generate_radial_strokes(
            anatomy["iris_inner_radius"] + 0.20,
            anatomy["iris_outer_radius"] * 0.97,
            180,
            z=anatomy["iris_front_z"] + 0.09,
            start_phase=0.15,
        ),
        "tear_guide": generate_curve(g["tear_radius"], segments, z=capsule_z + 0.11),
    }

    if visuals.get("show_zonules", False):
        curves["zonular_fiber_bundles"] = generate_zonule_fibers(
            ciliary_radius=anatomy["ciliary_inner_radius"],
            lens_radius=anatomy["lens_radius"],
            count=min(96, max(48, segments // 3)),
        )
    if visuals.get("show_vitreous_outline", False):
        curves["empty_vitreous_cavity_outline"] = generate_vitreous_cavity_outline(segments=96)

    if use_simulator_texture_layers:
        meshes.update(
            {
                "limbus_texture_layer": generate_annulus(
                    cornea_ry * 0.96,
                    cornea_rx * 1.03,
                    3,
                    segments,
                    z=limbus_z + 0.02,
                )[:2],
                "retroillumination_texture_layer": generate_domed_disk(
                    anatomy["lens_radius"] * 0.98,
                    12,
                    segments,
                    anatomy["lens_front_z"] - 0.62,
                    dome_height=0.22,
                )[:2],
                "lens_surface_texture_layer": generate_domed_disk(
                    anatomy["lens_radius"] * 0.98,
                    12,
                    segments,
                    anatomy["lens_front_z"] - 0.18,
                    dome_height=0.18,
                )[:2],
                "cortex_texture_layer": generate_domed_disk(
                    anatomy["lens_radius"] * 0.74,
                    10,
                    segments,
                    anatomy["lens_front_z"] - 1.02,
                    dome_height=0.14,
                )[:2],
                "nucleus_texture_layer": generate_domed_disk(
                    anatomy["lens_radius"] * 0.52,
                    8,
                    segments,
                    anatomy["lens_front_z"] - 1.36,
                    dome_height=0.09,
                )[:2],
                "posterior_capsule_texture_layer": generate_domed_disk(
                    anatomy["lens_radius"] * 0.98,
                    12,
                    segments,
                    anatomy["lens_back_z"] + 0.18,
                    dome_height=0.10,
                )[:2],
            }
        )

    if not using_rich_layered_textures(textures):
        meshes["scleral_vessel_ribbons"] = generate_vessel_ribbons(
            anatomy["iris_outer_radius"],
            anatomy["sclera_outer_radius"] * 0.96,
            branches=72,
            z=limbus_z + 0.06,
            width=0.075,
        )

    print(
        "texture_mode: "
        + (SIMULATOR_TEXTURE_MODE if use_simulator_texture_layers else os.path.basename(textures.get("sclera", "")))
    )
    print("anatomy_origin: lens_center=[0.0, 0.0, 0.0], units=millimeters")
    print(
        "anatomy_depths: cornea_front_z={0:.2f}, cornea_back_z={1:.2f}, iris_front_z={2:.2f}, lens_front_z={3:.2f}, lens_back_z={4:.2f}, vitreous_posterior_z=-17.20".format(
            cornea_front_apex_z,
            anatomy["cornea_posterior_apex_z"],
            anatomy["iris_front_z"],
            anatomy["lens_front_z"],
            anatomy["lens_back_z"],
        )
    )
    for name, (positions, triangles) in meshes.items():
        print(f"{name}: {len(positions)} vertices, {len(triangles)} triangles")
    for name, (positions, edges) in curves.items():
        print(f"{name}: {len(positions)} vertices, {len(edges)} edges")
