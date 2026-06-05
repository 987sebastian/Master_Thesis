import math
import os
from copy import deepcopy

try:
    import Sofa
    import Sofa.Core
except Exception:
    Sofa = None

from .input import (
    CTRL_KEY_ALIASES,
    EVENT_KEY_FIELDS,
    KEY_DOWN,
    KEY_LEFT,
    KEY_NAME_ALIASES,
    KEY_RIGHT,
    KEY_UP,
    WINDOWS_KEY_BINDINGS,
    WindowsKeyboardPoller,
)
from .math_utils import clamp, clamp01
from .trocar import trocar_visual_entry_center

class CapsulorhexisController(Sofa.Core.Controller if Sofa else object):
    @staticmethod
    def _estimate_tool_tip_reference(tool_positions, forceps_settings):
        if not tool_positions:
            return [-0.16, 0.0, float(forceps_settings.get("z", 0.2))]

        xs = [point[0] for point in tool_positions]
        max_x = max(xs)
        min_x = min(xs)
        span = max(max_x - min_x, 1.0e-6)
        tip_slice = float(forceps_settings.get("tip_slice", min(0.2, span * 0.02)))
        tip_band = [point for point in tool_positions if point[0] >= max_x - tip_slice]
        if not tip_band:
            tip_band = [point for point in tool_positions if point[0] == max_x]

        return [
            sum(point[0] for point in tip_band) / len(tip_band),
            sum(point[1] for point in tip_band) / len(tip_band),
            sum(point[2] for point in tip_band) / len(tip_band),
        ]

    @staticmethod
    def _gripped_y_for_pose(x, y, tool_grip, grip_start_x, grip_end_x):
        span = max(abs(grip_end_x - grip_start_x), 1.0e-6)
        tip_factor = clamp((x - grip_start_x) / span, 0.0, 1.0)
        grip_scale = 1.0 - tool_grip * 0.65 * tip_factor
        return y * grip_scale

    @classmethod
    def pose_tool_positions(
        cls,
        base_tool_positions,
        target,
        trocar_point,
        tool_tip,
        tool_roll=0.0,
        tool_grip=0.0,
        grip_start_x=0.0,
        grip_end_x=0.0,
    ):
        target_x, target_y, target_z = target
        axis_x = target_x - trocar_point[0]
        axis_y = target_y - trocar_point[1]
        axis_z = target_z - trocar_point[2]
        axis_length = math.sqrt(axis_x * axis_x + axis_y * axis_y + axis_z * axis_z)
        if axis_length <= 1.0e-6:
            axis_x, axis_y, axis_z = 0.0, 0.0, -1.0
            axis_length = 1.0
        axis_x /= axis_length
        axis_y /= axis_length
        axis_z /= axis_length

        ref_x, ref_y, ref_z = (0.0, 0.0, 1.0) if abs(axis_z) < 0.92 else (0.0, 1.0, 0.0)
        side_x = ref_y * axis_z - ref_z * axis_y
        side_y = ref_z * axis_x - ref_x * axis_z
        side_z = ref_x * axis_y - ref_y * axis_x
        side_length = math.sqrt(side_x * side_x + side_y * side_y + side_z * side_z) or 1.0
        side_x /= side_length
        side_y /= side_length
        side_z /= side_length
        normal_x = axis_y * side_z - axis_z * side_y
        normal_y = axis_z * side_x - axis_x * side_z
        normal_z = axis_x * side_y - axis_y * side_x

        if tool_roll:
            roll_c = math.cos(tool_roll)
            roll_s = math.sin(tool_roll)
            rolled_side = (
                side_x * roll_c + normal_x * roll_s,
                side_y * roll_c + normal_y * roll_s,
                side_z * roll_c + normal_z * roll_s,
            )
            rolled_normal = (
                normal_x * roll_c - side_x * roll_s,
                normal_y * roll_c - side_y * roll_s,
                normal_z * roll_c - side_z * roll_s,
            )
            side_x, side_y, side_z = rolled_side
            normal_x, normal_y, normal_z = rolled_normal

        tool_tip_x, tool_tip_y, tool_tip_z = tool_tip
        posed_positions = []
        for x, y, z in base_tool_positions:
            y = cls._gripped_y_for_pose(x, y, tool_grip, grip_start_x, grip_end_x)
            local_x = x - tool_tip_x
            local_y = y - tool_tip_y
            local_z = z - tool_tip_z
            posed_positions.append(
                [
                    target_x + axis_x * local_x + side_x * local_y + normal_x * local_z,
                    target_y + axis_y * local_x + side_y * local_y + normal_y * local_z,
                    target_z + axis_z * local_x + side_z * local_y + normal_z * local_z,
                ]
            )
        return posed_positions

    def __init__(
        self,
        profile,
        flap_node,
        flap_visual,
        guide_visual,
        tool_node,
        tool_visual,
        base_flap_positions,
        base_tool_positions,
        camera=None,
        status_label=None,
        tear_progress_node=None,
        tear_progress_visual=None,
        tear_edge_node=None,
        tear_edge_visual=None,
        traction_line_node=None,
        traction_line_visual=None,
        view_settings=None,
        name="capsulorhexis_controller",
    ):
        if Sofa:
            init_errors = []
            for kwargs in ({"name": name, "listening": True}, {"name": name}, {}):
                try:
                    Sofa.Core.Controller.__init__(self, **kwargs)
                    break
                except TypeError as error:
                    init_errors.append(error)
            else:
                raise RuntimeError(
                    "Unable to initialize Sofa.Core.Controller with supported SofaPython3 signatures"
                ) from init_errors[-1]
        self.name = name
        self.profile = profile
        self.flap_node = flap_node
        self.flap_visual = flap_visual
        self.guide_visual = guide_visual
        self.tool_node = tool_node
        self.tool_visual = tool_visual
        self.camera = camera
        self.status_label = status_label
        self.tear_progress_node = tear_progress_node
        self.tear_progress_visual = tear_progress_visual
        self.tear_edge_node = tear_edge_node
        self.tear_edge_visual = tear_edge_visual
        self.traction_line_node = traction_line_node
        self.traction_line_visual = traction_line_visual
        self.base_flap_positions = self._snapshot_positions(getattr(flap_node, "dofs", None), base_flap_positions)
        self.base_tool_positions = deepcopy(base_tool_positions)
        self.base_tear_progress_positions = self._snapshot_positions(getattr(tear_progress_node, "dofs", None), [])
        self.base_tear_edge_positions = self._snapshot_positions(getattr(tear_edge_node, "dofs", None), [])
        self.base_traction_line_positions = self._snapshot_positions(getattr(traction_line_node, "dofs", None), [])
        self.elapsed = 0.0
        self.paused = False
        self.speed_scale = 1.0
        simulation = profile["simulation"]
        self.guide_visible = bool(simulation.get("guide_visible", True))
        self.manual_tearing = bool(simulation.get("manual_tearing", False))
        self.physics_flap = bool(simulation.get("physics_flap", False))
        self.grab_handle_count = int(simulation.get("grab_handle_count", 6))
        self.grab_radius = float(simulation.get("grab_radius", 1.2))
        self.grab_curl = float(simulation.get("grab_curl", 0.3))
        self._grab_handles = []
        self._grab_orig = []
        self._grab_weight = []
        self._grab_local = []
        self._grab_tool_anchor = None
        self._grab_anchor0 = None
        self._was_grasped = False
        self.auto_tear = bool(simulation.get("auto_tear", not self.manual_tearing))
        self.grasp_grip_threshold = float(simulation.get("grasp_grip_threshold", 0.55))
        self.grasp_release_threshold = float(simulation.get("grasp_release_threshold", 0.25))
        self.grasp_radius_tolerance = float(simulation.get("grasp_radius_tolerance", 0.75))
        self.grasp_depth_above_max = float(simulation.get("grasp_depth_above_max", 0.18))
        self.grasp_depth_below_max = float(simulation.get("grasp_depth_below_max", 0.04))
        self.grasp_hold_above_max = float(simulation.get("grasp_hold_above_max", 0.25))
        self.grasp_hold_below_max = float(simulation.get("grasp_hold_below_max", 0.12))
        self.grasp_front_tolerance = float(simulation.get("grasp_front_tolerance", 0.16))
        self.tear_follow_rate = float(simulation.get("tear_follow_rate", 1.25))
        self.tear_force_threshold = float(simulation.get("tear_force_threshold", 0.05))
        self.tear_force_nominal = float(simulation.get("tear_force_nominal", 0.30))
        self.tear_force_overload = float(simulation.get("tear_force_overload", 0.82))
        self.tear_radial_sensitivity = float(simulation.get("tear_radial_sensitivity", 0.30))
        self.tear_start_bias_scale = float(simulation.get("tear_start_bias_scale", 0.38))
        self.tear_irregularity = float(simulation.get("tear_irregularity", 0.11))
        self.tear_irregularity_max = float(simulation.get("tear_irregularity_max", 0.42))
        self.tear_edge_memory = float(simulation.get("tear_edge_memory", 0.46))
        self.tear_tag_lift = float(simulation.get("tear_tag_lift", 0.24))
        self.tear_radius = float(profile["geometry"]["tear_radius"])
        self.progress = 0.0
        controls = profile.get("controls", {})
        self.tool_plane_step = float(controls.get("tool_plane_step", 0.08))
        self.tool_plane_rate = float(controls.get("tool_plane_rate", self.tool_plane_step * 8.0))
        self.tool_plane_limit = float(controls.get("tool_plane_limit", 1.25))
        self.tool_depth_step = float(controls.get("tool_depth_step", 0.06))
        self.tool_depth_max = float(controls.get("tool_depth_max", 0.75))
        self.tool_grip_step = float(controls.get("tool_grip_step", 0.2))
        self.tool_path_clearance = float(controls.get("tool_path_clearance", 0.25))
        self.tool_base_z = float(controls.get("tool_base_z", 0.68))
        self.tool_arc_lift = float(controls.get("tool_arc_lift", 0.22))
        self.tool_axis_angle = math.radians(float(controls.get("tool_axis_angle_degrees", 45.0)))
        self.tool_axis_offset = math.radians(float(controls.get("tool_axis_offset_degrees", 180.0)))
        self.tool_pitch = math.radians(float(controls.get("tool_pitch_degrees", 24.0)))
        self.tool_rotate_with_tear = bool(controls.get("tool_rotate_with_tear", False))
        self.tool_roll = math.radians(float(controls.get("tool_roll_degrees", 0.0)))
        forceps_settings = profile.get("assets", {}).get("forceps_model", {})
        tool_xs = [point[0] for point in self.base_tool_positions] or [-0.16]
        tool_span = max(tool_xs) - min(tool_xs)
        estimated_tip = self._estimate_tool_tip_reference(self.base_tool_positions, forceps_settings)
        self.tool_tip_x = float(forceps_settings.get("tip_x", estimated_tip[0]))
        self.tool_tip_y = float(forceps_settings.get("tip_y", estimated_tip[1]))
        self.tool_tip_z = float(forceps_settings.get("tip_z", estimated_tip[2]))
        tool_length = float(forceps_settings.get("length", max(tool_span, 1.0)))
        grip_length = float(forceps_settings.get("grip_length", min(1.8, max(tool_length * 0.22, 0.2))))
        self.tool_grip_end_x = float(forceps_settings.get("grip_end_x", self.tool_tip_x))
        self.tool_grip_start_x = float(forceps_settings.get("grip_start_x", self.tool_grip_end_x - grip_length))
        geometry = profile.get("geometry", {})
        self.capsule_z = float(geometry.get("anterior_capsule_z", 0.0))
        tear_start_angle = math.radians(float(profile["simulation"].get("tear_start_angle_degrees", -105.0)))
        default_target_z = float(geometry.get("anterior_capsule_z", 0.0)) + 0.12
        anatomy = {
            "cornea_horizontal_diameter": float(geometry.get("cornea_horizontal_diameter", 11.7)),
            "cornea_vertical_diameter": float(geometry.get("cornea_vertical_diameter", 10.6)),
            "cornea_central_thickness": float(geometry.get("cornea_central_thickness", 0.53)),
            "cornea_anterior_radius": float(geometry.get("cornea_anterior_radius", 7.8)),
            "cornea_posterior_apex_z": float(geometry.get("cornea_posterior_apex_z", 6.25)),
        }
        self.tool_target_origin = list(
            controls.get(
                "tool_target_origin",
                [self.tear_radius * math.cos(tear_start_angle), self.tear_radius * math.sin(tear_start_angle), default_target_z],
            )
        )
        self.tool_target_radius_limit = float(controls.get("tool_target_radius_limit", self.tear_radius + self.tool_path_clearance))
        self.tool_trocar_point = list(
            controls.get(
                "tool_trocar_point",
                trocar_visual_entry_center(anatomy, controls),
            )
        )
        self.debug_controls = bool(controls.get("debug_controls", False))
        self._debug_alive_interval = float(controls.get("debug_alive_interval", 2.0))
        self.keyboard_polling = bool(controls.get("keyboard_polling", os.name == "nt"))
        self._keyboard = WindowsKeyboardPoller() if self.keyboard_polling and os.name == "nt" else None
        self._poll_previous_keys = set()
        self.tool_offset = [0.0, 0.0]
        self.tool_insert_depth = 0.0
        self.tool_grip = 0.0
        self.grasped_capsule = False
        self._manual_pull_target = None
        self._previous_pull_target = None
        self._grasp_fraction = 0.0
        self._grasp_radius_error = 0.0
        self._tear_front_force = 0.0
        self._tear_stress = 0.0
        self._tear_direction_quality = 0.0
        self._tear_radial_bias = 0.0
        self._reset_tear_path()
        self._tip_capsule_distance = 0.0
        self._tip_radial_error = 0.0
        self._status_text = ""
        self._held_motion_keys = set()
        self._last_unhandled_key = None
        self._debug_elapsed = 0.0
        self._debug_last_tool_target = None
        self._position_write_successes = set()
        self._position_write_failures = set()
        self.view_presets = self._build_view_presets(view_settings)
        self.view_mode = self._normalize_view_mode((view_settings or {}).get("mode", "overview"))
        self.listening = True
        self._apply_view_mode(self.view_mode, log=False)
        self._update_tip_feedback()
        self._update_guidance_visuals()
        tear_mode = "manual forceps-driven tear" if self.manual_tearing else "time-driven demo tear"
        print(f"Capsulorhexis controls ready: {tear_mode}. In RCM mode WASD/arrows move the tool tip, E/Q insert/withdraw, C/V close/open, M toggles overview/top view, 1 sets overview, 2 sets top, R reset. If Ctrl is needed, use Ctrl+W/A/D and Down/X for down.")
        if self.debug_controls:
            print(
                "control debug enabled: controller is listening={0}, plane_step={1:.3f}, plane_limit={2:.3f}, depth_step={3:.3f}, keyboard_polling={4}, tip_ref=({5:.3f},{6:.3f},{7:.3f}), view_mode={8}, manual_tearing={9}, auto_tear={10}".format(
                    self.listening,
                    self.tool_plane_step,
                    self.tool_plane_limit,
                    self.tool_depth_step,
                    bool(self._keyboard and self._keyboard.available),
                    self.tool_tip_x,
                    self.tool_tip_y,
                    self.tool_tip_z,
                    self.view_mode,
                    self.manual_tearing,
                    self.auto_tear,
                )
            )

    @staticmethod
    def _snapshot_positions(mechanical_object, fallback_positions):
        if mechanical_object is not None:
            try:
                return [list(point) for point in mechanical_object.position.value]
            except Exception:
                pass
        return deepcopy(fallback_positions)

    def _reset_tear_path(self):
        count = len(self.base_tear_edge_positions)
        if count <= 0:
            count = int(self.profile.get("geometry", {}).get("capsule_segments", 216))
        self._tear_edge_offsets = [0.0 for _ in range(count)]
        self._tear_edge_stress = [0.0 for _ in range(count)]

    def _tear_sample_count(self):
        return max(1, len(getattr(self, "_tear_edge_offsets", [])))

    def _tear_offset_at_fraction(self, fraction):
        offsets = getattr(self, "_tear_edge_offsets", [])
        if not offsets:
            return 0.0
        count = len(offsets)
        position = (fraction % 1.0) * count
        index0 = int(math.floor(position)) % count
        index1 = (index0 + 1) % count
        blend = position - math.floor(position)
        return offsets[index0] * (1.0 - blend) + offsets[index1] * blend

    def _tear_stress_at_fraction(self, fraction):
        stress_values = getattr(self, "_tear_edge_stress", [])
        if not stress_values:
            return 0.0
        count = len(stress_values)
        position = (fraction % 1.0) * count
        index0 = int(math.floor(position)) % count
        index1 = (index0 + 1) % count
        blend = position - math.floor(position)
        return stress_values[index0] * (1.0 - blend) + stress_values[index1] * blend

    def _tear_front_radius(self):
        return self.tear_radius + self._tear_offset_at_fraction(self.progress)

    @staticmethod
    def _normalize_view_mode(mode):
        normalized = str(mode or "overview").strip().lower()
        if normalized in ("top", "topview", "top_view"):
            return "top"
        if normalized in ("overall", "whole", "full", "fullview"):
            return "overview"
        return "overview"

    @classmethod
    def _build_view_presets(cls, view_settings):
        defaults = {
            "overview": {
                "position": [0.0, -0.25, 32.0],
                "lookAt": [0.0, 0.0, 0.0],
                "fieldOfView": 36.0,
            },
            "top": {
                "position": [0.0, 0.0, 20.0],
                "lookAt": [0.0, 0.0, 2.0],
                "fieldOfView": 26.0,
            },
        }
        if not isinstance(view_settings, dict):
            return defaults

        presets = {}
        for mode in ("overview", "top"):
            source = view_settings.get(mode, {})
            fallback = defaults[mode]
            presets[mode] = {
                "position": list(source.get("position", fallback["position"])),
                "lookAt": list(source.get("lookAt", fallback["lookAt"])),
                "fieldOfView": float(source.get("fieldOfView", fallback["fieldOfView"])),
            }
        return presets

    def onAnimateBeginEvent(self, event):
        dt = event.get("dt", self.profile["simulation"]["dt"]) if isinstance(event, dict) else self.profile["simulation"]["dt"]
        if self.auto_tear and not self.paused:
            duration = self.profile["simulation"]["tear_duration_seconds"]
            self.elapsed += dt * self.speed_scale
            self.progress = min(1.0, self.elapsed / duration)
        self._poll_keyboard(dt)
        if not self._keyboard_polling_active():
            self._apply_held_motion(dt)
        self._update_manual_tear(dt)
        self.apply_animation()
        self._update_tip_feedback()
        self._update_guidance_visuals()
        self._log_controller_alive(dt)

    def onKeypressedEvent(self, event):
        key, code = self._normalize_key(event)
        self._poll_previous_keys.clear()
        if self.debug_controls:
            print(
                "key pressed: raw={0!r} normalized={1!r} code={2!r} event_type={3}".format(
                    self._event_key_value(event),
                    key,
                    code,
                    type(event).__name__,
                )
            )
        action = self._handle_control_key(key, code, "event")
        self.apply_animation()
        if action:
            self._log_tool_state(action)
        else:
            self._log_unhandled_key(event, key, code)

    def _handle_control_key(self, key, code, source):
        action = None
        if key in (" ", "p"):
            self.paused = not self.paused
            action = "pause" if self.paused else "resume"
        elif key == "r":
            self.elapsed = 0.0
            self.progress = 0.0
            self.paused = False
            self.tool_offset = [0.0, 0.0]
            self.tool_insert_depth = 0.0
            self.tool_grip = 0.0
            self.grasped_capsule = False
            self._manual_pull_target = None
            self._previous_pull_target = None
            self._tear_front_force = 0.0
            self._tear_stress = 0.0
            self._tear_direction_quality = 0.0
            self._tear_radial_bias = 0.0
            self._reset_tear_path()
            self._held_motion_keys.clear()
            action = "reset"
        elif key in ("+", "="):
            self.speed_scale = min(3.0, self.speed_scale + 0.15)
            action = "speed-up"
        elif key in ("-", "_"):
            self.speed_scale = max(0.15, self.speed_scale - 0.15)
            action = "speed-down"
        elif key == "[":
            self.tear_radius = max(self.profile["geometry"]["tear_radius_min"], self.tear_radius - 0.05)
            action = "radius-down"
        elif key == "]":
            self.tear_radius = min(self.profile["geometry"]["tear_radius_max"], self.tear_radius + 0.05)
            action = "radius-up"
        elif key == "t":
            self.guide_visible = not self.guide_visible
            action = "toggle-guide"
        elif key == "m":
            action = self._toggle_view_mode()
        elif key == "1":
            action = self._set_view_mode("overview")
        elif key == "2":
            action = self._set_view_mode("top")
        elif self._motion_key(key, code):
            motion = self._motion_key(key, code)
            if source == "event":
                if not self._keyboard_polling_active():
                    self._held_motion_keys.add(motion)
                self._move_tool_by_motion(motion, self.tool_plane_step)
            action = f"move-{motion}"
        elif key == "e":
            self.tool_insert_depth = min(self.tool_depth_max, self.tool_insert_depth + self.tool_depth_step)
            action = "insert"
        elif key == "q":
            self.tool_insert_depth = max(0.0, self.tool_insert_depth - self.tool_depth_step)
            action = "withdraw"
        elif key == "c":
            self.tool_grip = min(1.0, self.tool_grip + self.tool_grip_step)
            action = "close"
        elif key == "v":
            self.tool_grip = max(0.0, self.tool_grip - self.tool_grip_step)
            action = "open"
        return action

    def onKeyreleasedEvent(self, event):
        key, code = self._normalize_key(event)
        motion = self._motion_key(key, code)
        if self.debug_controls:
            print(
                "key released: raw={0!r} normalized={1!r} code={2!r} motion={3!r}".format(
                    self._event_key_value(event),
                    key,
                    code,
                    motion,
                )
            )
        if motion:
            self._held_motion_keys.discard(motion)

    def _poll_keyboard(self, dt):
        if not self._keyboard or not self._keyboard.available:
            return

        current = {name for name in WINDOWS_KEY_BINDINGS if self._keyboard.pressed(name)}
        pressed_now = current - self._poll_previous_keys
        released_now = self._poll_previous_keys - current

        motion_keys = {
            "up": ("w", "i", "up"),
            "down": ("s", "x", "k", "down"),
            "left": ("a", "j", "left"),
            "right": ("d", "l", "right"),
        }
        active_motions = []
        for motion, names in motion_keys.items():
            if any(name in current for name in names):
                active_motions.append(motion)

        if active_motions:
            distance = self.tool_plane_rate * dt
            for motion in active_motions:
                self._move_tool_by_motion(motion, distance)
            if self.debug_controls and any(name in pressed_now for names in motion_keys.values() for name in names):
                print(f"keyboard poll motion: active={active_motions}")

        discrete_keys = [
            ("space", " "),
            ("p", "p"),
            ("r", "r"),
            ("e", "e"),
            ("q", "q"),
            ("c", "c"),
            ("v", "v"),
            ("t", "t"),
            ("m", "m"),
            ("1", "1"),
            ("2", "2"),
            ("plus", "+"),
            ("numpad_plus", "+"),
            ("minus", "-"),
            ("numpad_minus", "-"),
            ("left_bracket", "["),
            ("right_bracket", "]"),
        ]
        for key_name, normalized in discrete_keys:
            if key_name not in pressed_now:
                continue
            action = self._handle_control_key(normalized, ord(normalized), "poll")
            if self.debug_controls:
                print(f"keyboard poll pressed: raw={key_name!r} normalized={normalized!r} action={action!r}")
            if action:
                self._log_tool_state(action)

        if self.debug_controls and released_now:
            interesting = sorted(released_now.intersection(WINDOWS_KEY_BINDINGS))
            if interesting:
                print(f"keyboard poll released: {interesting}")

        self._poll_previous_keys = current

    def _keyboard_polling_active(self):
        return bool(self._keyboard and self._keyboard.available)

    def _normalize_key(self, event):
        raw_key = self._event_key_value(event)
        if isinstance(raw_key, bytes):
            raw_key = raw_key.decode("utf-8", errors="ignore")
        if isinstance(raw_key, int):
            key = chr(raw_key).lower() if 32 <= raw_key <= 126 else CTRL_KEY_ALIASES.get(raw_key, "")
            return key, raw_key
        if not isinstance(raw_key, str):
            return "", None
        if len(raw_key) == 1:
            code = ord(raw_key)
            key = raw_key.lower() if 32 <= code <= 126 else CTRL_KEY_ALIASES.get(code, "")
            return key, code
        key = raw_key.strip().lower()
        if key.startswith("key."):
            key = key[4:]
        if key.startswith("key_"):
            aliased = KEY_NAME_ALIASES.get(key)
            if aliased:
                return self._normalize_key_value(aliased[0])
            key = key[4:]
        aliased = KEY_NAME_ALIASES.get(key)
        if aliased:
            return self._normalize_key_value(aliased[0])
        if len(key) == 1:
            return self._normalize_key_value(key)
        code = None
        return key, code

    def _event_key_value(self, event):
        if isinstance(event, (str, int, bytes)):
            return event
        if isinstance(event, dict):
            for field in EVENT_KEY_FIELDS:
                if field in event and event[field] is not None:
                    return event[field]
            return ""
        for field in EVENT_KEY_FIELDS:
            if hasattr(event, field):
                value = getattr(event, field)
                value = value() if callable(value) else value
                if value is not None:
                    return value
        for field in EVENT_KEY_FIELDS:
            try:
                return event[field]
            except Exception:
                pass
        return ""

    def _normalize_key_value(self, raw_key):
        return self._normalize_key({"key": raw_key})

    def _log_unhandled_key(self, event, key, code):
        marker = (key, code)
        if marker == self._last_unhandled_key:
            return
        self._last_unhandled_key = marker
        print(f"unhandled key event: raw={self._event_key_value(event)!r} normalized={key!r} code={code!r}")

    def _log_controller_alive(self, dt):
        if not self.debug_controls:
            return
        self._debug_elapsed += dt
        if self._debug_elapsed < self._debug_alive_interval:
            return
        self._debug_elapsed = 0.0
        print(
            "control alive: progress={0:.3f} paused={1} held={2} offset=({3:.2f},{4:.2f}) depth={5:.2f} target={6}".format(
                self.progress,
                self.paused,
                sorted(self._held_motion_keys),
                self.tool_offset[0],
                self.tool_offset[1],
                self.tool_insert_depth,
                self._debug_last_tool_target,
            )
        )

    def _motion_key(self, key, code):
        if key in ("w", "i") or code == KEY_UP:
            return "up"
        if key in ("s", "x", "k") or code == KEY_DOWN:
            return "down"
        if key in ("a", "j") or code == KEY_LEFT:
            return "left"
        if key in ("d", "l") or code == KEY_RIGHT:
            return "right"
        return None

    def _move_tool_by_motion(self, motion, distance):
        if motion == "up":
            self._move_tool(0.0, distance)
        elif motion == "down":
            self._move_tool(0.0, -distance)
        elif motion == "left":
            self._move_tool(-distance, 0.0)
        elif motion == "right":
            self._move_tool(distance, 0.0)

    def _apply_held_motion(self, dt):
        if not self._held_motion_keys:
            return
        distance = self.tool_plane_rate * dt
        for motion in tuple(self._held_motion_keys):
            self._move_tool_by_motion(motion, distance)

    def _move_tool(self, dx, dy):
        old_offset = tuple(self.tool_offset)
        next_x = clamp(self.tool_offset[0] + dx, -self.tool_plane_limit, self.tool_plane_limit)
        next_y = clamp(self.tool_offset[1] + dy, -self.tool_plane_limit, self.tool_plane_limit)
        target_x = self.tool_target_origin[0] + next_x
        target_y = self.tool_target_origin[1] + next_y
        radius = math.sqrt(target_x * target_x + target_y * target_y)
        if radius > self.tool_target_radius_limit > 1.0e-6:
            scale = self.tool_target_radius_limit / radius
            target_x *= scale
            target_y *= scale
            next_x = target_x - self.tool_target_origin[0]
            next_y = target_y - self.tool_target_origin[1]
        self.tool_offset[0] = next_x
        self.tool_offset[1] = next_y
        if self.debug_controls:
            print(
                "tool offset update: delta=({0:.3f},{1:.3f}) old=({2:.3f},{3:.3f}) new=({4:.3f},{5:.3f})".format(
                    dx,
                    dy,
                    old_offset[0],
                    old_offset[1],
                    self.tool_offset[0],
                    self.tool_offset[1],
                )
            )

    def _log_tool_state(self, action):
        self._update_tip_feedback()
        print(
            "control {0}: offset=({1:.2f}, {2:.2f}) depth={3:.2f} grip={4:.2f} target={5} view={6} grasped={7} progress={8:.3f} tip_capsule={9:+.2f}mm radial_error={10:+.2f}mm".format(
                action,
                self.tool_offset[0],
                self.tool_offset[1],
                self.tool_insert_depth,
                self.tool_grip,
                self._debug_last_tool_target,
                self.view_mode,
                self.grasped_capsule,
                self.progress,
                self._tip_capsule_distance,
                self._tip_radial_error,
            )
        )

    def _toggle_view_mode(self):
        next_mode = "top" if self.view_mode != "top" else "overview"
        return self._set_view_mode(next_mode)

    def _set_view_mode(self, mode):
        normalized = self._normalize_view_mode(mode)
        changed = self._apply_view_mode(normalized)
        return f"view-{normalized}" if changed else None

    def _apply_view_mode(self, mode, log=True):
        preset = self.view_presets.get(self._normalize_view_mode(mode))
        if not preset:
            return False
        self.view_mode = self._normalize_view_mode(mode)
        if self.camera is None:
            return True
        success = True
        success = self._set_camera_field("position", preset["position"]) and success
        success = self._set_camera_field("lookAt", preset["lookAt"]) and success
        success = self._set_camera_field("fieldOfView", preset["fieldOfView"]) and success
        if log and success:
            print(f"view mode switched to {self.view_mode}")
        return success

    def _set_camera_field(self, name, value):
        if self.camera is None:
            return False
        try:
            field = getattr(self.camera, name)
        except Exception:
            field = None
        if field is not None:
            try:
                field.value = value
                return True
            except Exception:
                pass
        try:
            setattr(self.camera, name, value)
            return True
        except Exception:
            return False

    def apply_animation(self):
        self._animate_flap()
        self._animate_tool()
        self._animate_guide()

    def _tool_target(self):
        return [
            self.tool_target_origin[0] + self.tool_offset[0],
            self.tool_target_origin[1] + self.tool_offset[1],
            self.tool_target_origin[2] - self.tool_insert_depth,
        ]

    def _tip_feedback(self):
        target = self._tool_target()
        radial = math.sqrt(target[0] * target[0] + target[1] * target[1])
        tip_capsule_distance = target[2] - self.capsule_z
        radial_error = radial - self.tear_radius
        bite_depth_ok = -self.grasp_depth_below_max <= tip_capsule_distance <= self.grasp_depth_above_max
        hold_depth_ok = -self.grasp_hold_below_max <= tip_capsule_distance <= self.grasp_hold_above_max
        radius_ok = abs(radial_error) <= self.grasp_radius_tolerance
        grip_ok = self.tool_grip >= self.grasp_grip_threshold
        target_fraction = self._angle_fraction(math.atan2(target[1], target[0]))
        front_delta = self._signed_progress_delta(target_fraction, self.progress)
        front_ok = abs(front_delta) <= self.grasp_front_tolerance

        if self.grasped_capsule:
            if self._tear_stress >= 0.62:
                state = "TEARING HARD"
                color = [1.0, 0.34, 0.16]
            elif self._tear_direction_quality < 0.35 and self._tear_front_force > self.tear_force_threshold:
                state = "OFF AXIS"
                color = [1.0, 0.76, 0.22]
            else:
                state = "GRASPED"
                color = [0.35, 1.0, 0.40]
        elif not bite_depth_ok:
            state = "TOO HIGH" if tip_capsule_distance > 0.0 else "TOO DEEP"
            color = [1.0, 0.76, 0.22]
        elif not radius_ok:
            state = "EDGE FAR"
            color = [1.0, 0.76, 0.22]
        elif not front_ok:
            state = "FIND FRONT"
            color = [1.0, 0.76, 0.22]
        elif not grip_ok:
            state = "BITE NOW"
            color = [0.95, 0.95, 0.95]
        else:
            state = "READY TO GRASP"
            color = [0.45, 0.90, 1.0]

        return {
            "target": target,
            "radial": radial,
            "tip_capsule_distance": tip_capsule_distance,
            "radial_error": radial_error,
            "bite_depth_ok": bite_depth_ok,
            "hold_depth_ok": hold_depth_ok,
            "front_delta": front_delta,
            "front_ok": front_ok,
            "tear_force": self._tear_front_force,
            "tear_stress": self._tear_stress,
            "direction_quality": self._tear_direction_quality,
            "state": state,
            "color": color,
        }

    def _update_tip_feedback(self):
        feedback = self._tip_feedback()
        self._tip_capsule_distance = feedback["tip_capsule_distance"]
        self._tip_radial_error = feedback["radial_error"]
        self._status_text = (
            "Tip-Capsule dz: {0:+.2f} mm | Edge offset: {1:+.2f} mm | Grip: {2:.2f} | Force: {3:.2f} | {4} | {5}".format(
                self._tip_capsule_distance,
                self._tip_radial_error,
                self.tool_grip,
                self._tear_front_force,
                feedback["state"],
                self._operator_hint(feedback),
            )
        )
        self._set_label_text(self.status_label, self._status_text)
        self._set_label_color(self.status_label, feedback["color"])

    def _operator_hint(self, feedback):
        if self.grasped_capsule:
            if feedback["state"] == "TEARING HARD":
                return "REDUCE PULL"
            if feedback["state"] == "OFF AXIS":
                return "PULL TANGENTIAL"
            return "PULL ALONG GUIDE"
        if feedback["state"] == "TOO HIGH":
            return "PRESS E"
        if feedback["state"] == "TOO DEEP":
            return "PRESS Q"
        if feedback["state"] == "EDGE FAR":
            return "MOVE TO EDGE"
        if feedback["state"] == "FIND FRONT":
            return "MOVE TO TEAR FRONT"
        if feedback["state"] == "BITE NOW":
            return "PRESS C"
        return "READY"

    def _update_guidance_visuals(self):
        self._update_tear_edge_curve()
        self._update_tear_progress_arc()
        self._update_traction_line()

    def _update_tear_edge_curve(self):
        if self.tear_edge_node is None or not self.base_tear_edge_positions:
            return
        positions = []
        for point in self.base_tear_edge_positions:
            angle = math.atan2(point[1], point[0])
            fraction = self._angle_fraction(angle)
            opened = 1.0 if fraction <= self.progress or self.progress >= 0.995 else 0.0
            feather = clamp01((self.progress - fraction + 0.035) / 0.035) if opened <= 0.0 else 1.0
            edge_offset = self._tear_offset_at_fraction(fraction) * max(opened, feather)
            edge_stress = self._tear_stress_at_fraction(fraction) * max(opened, feather)
            radius = self.tear_radius * 1.012 + edge_offset
            z = self.capsule_z + 0.17 + edge_stress * 0.07
            positions.append([radius * math.cos(angle), radius * math.sin(angle), z])
        self._set_position(self.tear_edge_node.dofs, positions, "tear edge")
        edge_color = [1.0, 0.18 + 0.20 * (1.0 - self._tear_stress), 0.04, 0.78]
        self._set_visual_color(self.tear_edge_visual, edge_color)

    def _update_tear_progress_arc(self):
        if self.tear_progress_node is None or not self.base_tear_progress_positions:
            return
        count = len(self.base_tear_progress_positions)
        if count < 2:
            return
        start = math.radians(self.profile["simulation"]["tear_start_angle_degrees"])
        direction = float(self.profile["simulation"]["tear_direction"])
        z = self.capsule_z + 0.27
        positions = []
        for index in range(count):
            fraction = min(self.progress, index / max(1, count - 1))
            radius = self.tear_radius * 1.035 + self._tear_offset_at_fraction(fraction)
            angle = start + direction * fraction * 2.0 * math.pi
            positions.append([radius * math.cos(angle), radius * math.sin(angle), z])
        self._set_position(self.tear_progress_node.dofs, positions, "tear progress")

    def _update_traction_line(self):
        if self.traction_line_node is None:
            return
        feedback = self._tip_feedback()
        target = feedback["target"]
        front_angle = self._tear_angle()
        front_radius = self._tear_front_radius()
        front = [
            front_radius * math.cos(front_angle),
            front_radius * math.sin(front_angle),
            self.capsule_z + 0.24,
        ]
        if self.grasped_capsule:
            positions = [target, front]
            color = [0.20, 1.0, 0.30, 0.95]
        else:
            positions = [front, front]
            color = [1.0, 0.74, 0.16, 0.35]
        self._set_position(self.traction_line_node.dofs, positions, "traction line")
        self._set_visual_color(self.traction_line_visual, color)
        progress_color = [0.10, 1.0, 0.42, 0.95] if self.progress > 0.0 else [1.0, 0.74, 0.16, 0.55]
        self._set_visual_color(self.tear_progress_visual, progress_color)

    def _set_label_text(self, label, text):
        if label is None:
            return
        if self._set_data_field(label, "label", text):
            return
        self._set_data_field(label, "text", text)

    def _set_label_color(self, label, color):
        if label is None:
            return
        if self._set_data_field(label, "color", color):
            return
        color_text = "{0:.3f} {1:.3f} {2:.3f}".format(color[0], color[1], color[2])
        self._set_data_field(label, "color", color_text)

    def _set_visual_color(self, visual_model, color):
        if visual_model is None:
            return
        if self._set_data_field(visual_model, "color", color):
            return
        color_text = " ".join("{0:.3f}".format(channel) for channel in color)
        self._set_data_field(visual_model, "color", color_text)

    def _set_data_field(self, component, name, value):
        try:
            field = getattr(component, name)
        except Exception:
            field = None
        if field is not None:
            try:
                field.value = value
                return True
            except Exception:
                pass
        try:
            setattr(component, name, value)
            return True
        except Exception:
            return False

    def _update_manual_tear(self, dt):
        if not self.manual_tearing or self.progress >= 1.0:
            return

        feedback = self._tip_feedback()
        target = feedback["target"]
        near_tear_radius = abs(feedback["radial_error"]) <= self.grasp_radius_tolerance
        near_tear_front = feedback["front_ok"]
        bite_depth_ok = feedback["bite_depth_ok"]
        hold_depth_ok = feedback["hold_depth_ok"]
        closed_enough = self.tool_grip >= self.grasp_grip_threshold

        if self.grasped_capsule:
            if self.tool_grip <= self.grasp_release_threshold or not hold_depth_ok:
                self.grasped_capsule = False
                self._manual_pull_target = None
                self._previous_pull_target = None
                self._tear_front_force = 0.0
                self._tear_stress *= 0.55
                self._tear_direction_quality = 0.0
                if self.debug_controls:
                    print("manual tear released")
                return
        elif closed_enough and near_tear_radius and near_tear_front and bite_depth_ok:
            self.grasped_capsule = True
            self._grasp_fraction = self._angle_fraction(math.atan2(target[1], target[0]))
            self._grasp_radius_error = feedback["radial_error"]
            self._previous_pull_target = list(target)
            if self.debug_controls:
                print(
                    "manual tear grasped capsule edge: fraction={0:.3f} radial_error={1:+.3f}mm".format(
                        self._grasp_fraction,
                        self._grasp_radius_error,
                    )
                )
        else:
            return

        self._manual_pull_target = target
        traction = self._tear_traction(target, dt)
        self._tear_front_force = traction["force"]
        self._tear_stress = traction["stress"]
        self._tear_direction_quality = traction["quality"]
        self._tear_radial_bias = traction["radial_bias"]
        target_fraction = self._angle_fraction(math.atan2(target[1], target[0]))
        delta = self._signed_progress_delta(target_fraction, self.progress)

        drive = max(0.0, traction["tangential"] - self.tear_force_threshold)
        if delta > 0.0 and drive > 0.0:
            force_gain = clamp(drive / max(self.tear_force_nominal, 1.0e-6), 0.0, 2.4)
            quality_gain = 0.20 + 0.80 * traction["quality"]
            advance_rate = self.tear_follow_rate * force_gain * quality_gain * (0.65 + 0.35 * self.tool_grip)
            previous_progress = self.progress
            self.progress = min(1.0, self.progress + min(delta, advance_rate * dt))
            self._scar_tear_path(previous_progress, self.progress, traction)
            duration = self.profile["simulation"]["tear_duration_seconds"]
            self.elapsed = self.progress * duration
        elif traction["stress"] > 0.35:
            self._stress_tear_front(traction)

        self._previous_pull_target = list(target)

    def _tear_traction(self, target, dt):
        front_angle = self._tear_angle()
        front_radius = self._tear_front_radius()
        front_x = front_radius * math.cos(front_angle)
        front_y = front_radius * math.sin(front_angle)
        direction = float(self.profile["simulation"]["tear_direction"])
        tangent_x = -math.sin(front_angle) * direction
        tangent_y = math.cos(front_angle) * direction
        radial_x = math.cos(front_angle)
        radial_y = math.sin(front_angle)
        pull_x = target[0] - front_x
        pull_y = target[1] - front_y
        tangential = pull_x * tangent_x + pull_y * tangent_y
        radial = pull_x * radial_x + pull_y * radial_y
        lift = target[2] - self.capsule_z
        velocity = 0.0
        if self._previous_pull_target is not None and dt > 1.0e-6:
            vx = target[0] - self._previous_pull_target[0]
            vy = target[1] - self._previous_pull_target[1]
            vz = target[2] - self._previous_pull_target[2]
            velocity = math.sqrt(vx * vx + vy * vy + vz * vz) / dt

        traction_length = math.sqrt(tangential * tangential + radial * radial + (0.55 * lift) * (0.55 * lift))
        force = (traction_length + velocity * 0.018) * (0.55 + 0.45 * self.tool_grip)
        lateral_penalty = abs(radial) * 0.85 + max(0.0, -tangential) * 1.10
        quality = clamp01((max(0.0, tangential) + 0.035) / (max(0.0, tangential) + lateral_penalty + 0.035))
        overload = clamp01((force - self.tear_force_nominal) / max(self.tear_force_overload - self.tear_force_nominal, 1.0e-6))
        radial_stress = clamp01(abs(radial) / max(self.grasp_radius_tolerance * 0.72, 1.0e-6))
        reverse_stress = clamp01(max(0.0, -tangential) / max(self.tear_force_nominal, 1.0e-6))
        depth_stress = clamp01(max(0.0, -lift - self.grasp_hold_below_max * 0.35) / max(self.grasp_hold_below_max, 1.0e-6))
        stress = clamp01(overload * 0.50 + radial_stress * 0.32 + reverse_stress * 0.22 + depth_stress * 0.20)
        radial_bias = radial * self.tear_radial_sensitivity + self._grasp_radius_error * self.tear_start_bias_scale
        return {
            "force": force,
            "tangential": tangential,
            "radial": radial,
            "lift": lift,
            "quality": quality,
            "stress": stress,
            "radial_bias": radial_bias,
        }

    def _scar_tear_path(self, previous_progress, current_progress, traction):
        if current_progress <= previous_progress:
            return
        count = self._tear_sample_count()
        start = int(math.floor(previous_progress * count))
        end = int(math.ceil(current_progress * count)) + 1
        for index in range(start, end + 1):
            self._write_tear_sample(index % count, traction)

    def _stress_tear_front(self, traction):
        count = self._tear_sample_count()
        center = int(round(self.progress * count)) % count
        for offset in range(-2, 3):
            weight = 1.0 - abs(offset) / 3.0
            self._write_tear_sample(center + offset, traction, weight=weight * 0.55)

    def _write_tear_sample(self, index, traction, weight=1.0):
        count = self._tear_sample_count()
        index %= count
        deterministic = (
            math.sin(index * 12.9898 + self._grasp_fraction * 31.0)
            + 0.45 * math.sin(index * 4.1414 + self.progress * 19.0)
        ) / 1.45
        roughness = self.tear_irregularity * (0.25 + 0.75 * traction["stress"])
        target_offset = traction["radial_bias"] + deterministic * roughness
        target_offset = clamp(target_offset, -self.tear_irregularity_max, self.tear_irregularity_max)
        memory = clamp01(self.tear_edge_memory * weight)
        self._tear_edge_offsets[index] = self._tear_edge_offsets[index] * (1.0 - memory) + target_offset * memory
        local_stress = clamp01(traction["stress"] * weight + abs(self._tear_edge_offsets[index]) / max(self.tear_irregularity_max, 1.0e-6) * 0.22)
        self._tear_edge_stress[index] = max(self._tear_edge_stress[index] * 0.92, local_stress)

    def _tear_angle(self):
        start = math.radians(self.profile["simulation"]["tear_start_angle_degrees"])
        direction = float(self.profile["simulation"]["tear_direction"])
        return start + direction * self.progress * 2.0 * math.pi

    def _angle_fraction(self, angle):
        start = math.radians(self.profile["simulation"]["tear_start_angle_degrees"])
        direction = float(self.profile["simulation"]["tear_direction"])
        delta = direction * (angle - start)
        while delta < 0.0:
            delta += 2.0 * math.pi
        while delta >= 2.0 * math.pi:
            delta -= 2.0 * math.pi
        return delta / (2.0 * math.pi)

    def _signed_progress_delta(self, target_fraction, current_fraction):
        delta = target_fraction - current_fraction
        while delta < -0.5:
            delta += 1.0
        while delta > 0.5:
            delta -= 1.0
        return delta

    def _animate_flap(self):
        if self.physics_flap:
            return  # flap is owned by the FEM solver; do not script its vertices
        lift = float(self.profile["simulation"]["flap_lift"])
        drag = float(self.profile["simulation"]["flap_drag"])
        curl = float(self.profile["simulation"]["flap_curl"])
        tear_angle = self._tear_angle()
        if self._manual_pull_target is not None:
            pulled_x, pulled_y, pulled_z = self._manual_pull_target
        else:
            pulled_x = self.tear_radius * math.cos(tear_angle) + drag * math.cos(tear_angle)
            pulled_y = self.tear_radius * math.sin(tear_angle) + drag * math.sin(tear_angle)
            pulled_z = None
        new_positions = []

        for point in self.base_flap_positions:
            x, y, z = point
            radius = math.sqrt(x * x + y * y)
            angle = math.atan2(y, x)
            fraction = self._angle_fraction(angle)
            opened = max(0.0, min(1.0, (self.progress - fraction) * 8.0))
            radial = radius / max(self.tear_radius, 0.001)
            edge_offset = self._tear_offset_at_fraction(fraction) * opened * (radial ** 1.7)
            local_stress = self._tear_stress_at_fraction(fraction) * opened * (0.35 + 0.65 * radial)
            x = x + math.cos(angle) * edge_offset
            y = y + math.sin(angle) * edge_offset
            hinge = max(0.0, min(1.0, radial))
            bend = opened * hinge
            twist = opened * math.sin(radial * math.pi) * curl
            twist += local_stress * self.tear_tag_lift * math.sin(radial * math.pi * 0.72)
            nx = x * (1.0 - bend * 0.34) + pulled_x * bend * 0.34
            ny = y * (1.0 - bend * 0.34) + pulled_y * bend * 0.34
            lifted_z = z + lift * bend + twist
            nz = lifted_z if pulled_z is None else lifted_z * (1.0 - bend * 0.28) + (pulled_z + 0.18) * bend * 0.28
            new_positions.append([nx, ny, nz])

        self._set_position(self.flap_node.dofs, new_positions)

    def _animate_tool(self):
        target_x, target_y, target_z = self._tool_target()
        self._debug_last_tool_target = (round(target_x, 3), round(target_y, 3), round(target_z, 3))
        new_positions = self.pose_tool_positions(
            self.base_tool_positions,
            [target_x, target_y, target_z],
            self.tool_trocar_point,
            [self.tool_tip_x, self.tool_tip_y, self.tool_tip_z],
            tool_roll=self.tool_roll,
            tool_grip=self.tool_grip,
            grip_start_x=self.tool_grip_start_x,
            grip_end_x=self.tool_grip_end_x,
        )
        self._set_position(self.tool_node.dofs, new_positions, "forceps mechanical")

    def _gripped_tool_y(self, x, y):
        return self._gripped_y_for_pose(x, y, self.tool_grip, self.tool_grip_start_x, self.tool_grip_end_x)

    def _animate_guide(self):
        alpha = 1.0 if self.guide_visible else 0.0
        try:
            self.guide_visual.color.value = [1.0, 0.85, 0.22, alpha]
        except Exception:
            pass

    def _set_position(self, mechanical_object, positions, label="mechanical"):
        try:
            mechanical_object.position.value = positions
            self._log_position_write(label, "value", positions)
        except Exception:
            try:
                with mechanical_object.position.writeable() as data:
                    for index, point in enumerate(positions):
                        data[index] = point
                self._log_position_write(label, "writeable", positions)
            except Exception:
                self._log_position_write_failure(label)

    def _set_visual_positions(self, visual_model, positions, label="visual"):
        try:
            visual_model.position.value = positions
            self._log_position_write(label, "value", positions)
        except Exception:
            self._log_position_write_failure(label)

    def _log_position_write(self, label, method, positions):
        if not self.debug_controls or not label.startswith("forceps"):
            return
        marker = (label, "ok")
        if marker in self._position_write_successes:
            return
        self._position_write_successes.add(marker)
        first = positions[0] if positions else None
        print(f"{label} position write ok via {method}; first_vertex={first}")

    def _log_position_write_failure(self, label):
        marker = (label, "failed")
        if marker in self._position_write_failures:
            return
        self._position_write_failures.add(marker)
        print(f"{label} position write FAILED")

    # --- physics flap (active only when simulation.physics_flap = true) ------ #
    def onAnimateEndEvent(self, event):
        if not self.physics_flap:
            return
        grasped = self.grasped_capsule
        if grasped and not self._was_grasped:
            self._pick_grab_handles()
        elif not grasped and self._was_grasped:
            self._grab_handles = []
            self._grab_orig = []
            self._grab_weight = []
            self._grab_tool_anchor = None
            self._grab_anchor0 = None
        self._was_grasped = grasped
        if grasped and self._grab_handles:
            self._pin_grab_handles()

    def _live_flap_positions(self):
        node = getattr(self, "flap_node", None)
        dofs = getattr(node, "dofs", None) if node is not None else None
        if dofs is not None:
            try:
                return [list(point) for point in dofs.position.value]
            except Exception:
                pass
        return [list(point) for point in self.base_flap_positions]

    def _live_tool_positions(self):
        node = getattr(self, "tool_node", None)
        dofs = getattr(node, "dofs", None) if node is not None else None
        if dofs is not None:
            try:
                return [list(point) for point in dofs.position.value]
            except Exception:
                pass
        return [list(point) for point in self.base_tool_positions]

    def _tool_anchor_position(self):
        """World position of the forceps vertex used as the grab anchor.

        Falls back to the control target if no forceps vertex is available, so
        the behaviour degrades gracefully rather than crashing.
        """
        tool_live = self._live_tool_positions()
        if self._grab_tool_anchor is not None and 0 <= self._grab_tool_anchor < len(tool_live):
            return tool_live[self._grab_tool_anchor]
        return self._tool_target()

    def _pick_grab_handles(self):
        flap_live = self._live_flap_positions()
        if not flap_live:
            self._grab_handles = []
            self._grab_orig = []
            self._grab_weight = []
            self._grab_tool_anchor = None
            self._grab_anchor0 = None
            return

        # Lock onto the real forceps vertex nearest the control tip, so the
        # tissue follows the rendered forceps head rather than the guide point.
        target = self._tool_target()
        tool_live = self._live_tool_positions()
        self._grab_tool_anchor = None
        if tool_live:
            def tool_distance(index):
                point = tool_live[index]
                dx = point[0] - target[0]
                dy = point[1] - target[1]
                dz = point[2] - target[2]
                return dx * dx + dy * dy + dz * dz

            self._grab_tool_anchor = min(range(len(tool_live)), key=tool_distance)

        anchor = self._tool_anchor_position()
        self._grab_anchor0 = list(anchor)

        # Select a LOCAL patch within grab_radius of the anchor. Each handle gets
        # a weight that fades from 1 (at the anchor) to 0 (at the radius), so the
        # patch lifts smoothly instead of being yanked into a spike.
        radius = max(self.grab_radius, 1.0e-3)
        handles = []
        orig = []
        weight = []
        for index, point in enumerate(flap_live):
            dx = point[0] - anchor[0]
            dy = point[1] - anchor[1]
            dz = point[2] - anchor[2]
            distance = math.sqrt(dx * dx + dy * dy + dz * dz)
            if distance <= radius:
                handles.append(index)
                orig.append([point[0], point[1], point[2]])
                weight.append(1.0 - distance / radius)

        # Fallback: if the radius caught nothing (anchor far from flap), grab the
        # nearest few vertices so the action still does something.
        if not handles:
            def flap_distance(index):
                point = flap_live[index]
                dx = point[0] - anchor[0]
                dy = point[1] - anchor[1]
                dz = point[2] - anchor[2]
                return dx * dx + dy * dy + dz * dz

            count = max(1, min(self.grab_handle_count, len(flap_live)))
            for index in sorted(range(len(flap_live)), key=flap_distance)[:count]:
                handles.append(index)
                orig.append([flap_live[index][0], flap_live[index][1], flap_live[index][2]])
                weight.append(1.0)

        self._grab_handles = handles
        self._grab_orig = orig
        self._grab_weight = weight
        if self.debug_controls:
            print(f"physics grab: anchor_vertex={self._grab_tool_anchor} patch={len(handles)} verts")

    def _pin_grab_handles(self):
        node = getattr(self, "flap_node", None)
        dofs = getattr(node, "dofs", None) if node is not None else None
        if dofs is None or self._grab_anchor0 is None:
            return
        anchor = self._tool_anchor_position()
        move_x = anchor[0] - self._grab_anchor0[0]
        move_y = anchor[1] - self._grab_anchor0[1]
        move_z = anchor[2] - self._grab_anchor0[2]
        pull = math.sqrt(move_x * move_x + move_y * move_y)
        curl = self.grab_curl
        try:
            with dofs.position.writeable() as positions:
                for handle, base, weight in zip(self._grab_handles, self._grab_orig, self._grab_weight):
                    positions[handle][0] = base[0] + weight * move_x
                    positions[handle][1] = base[1] + weight * move_y
                    # weighted vertical follow plus a curl that lifts the near
                    # edge more strongly, so the patch rolls up as it is dragged.
                    positions[handle][2] = base[2] + weight * move_z + curl * weight * weight * pull
        except Exception:
            pass
        try:
            with dofs.velocity.writeable() as velocities:
                for handle in self._grab_handles:
                    velocities[handle][0] = 0.0
                    velocities[handle][1] = 0.0
                    velocities[handle][2] = 0.0
        except Exception:
            pass
