# Cataract Capsulorhexis SOFA Simulator

This project implements a first-pass continuous curvilinear capsulorhexis
simulator for SOFA/SofaPython3, driven by the local reference video
`Video Project.mp4`.

The simulator scene loads the external eyeball model when available and nests
the generated anterior segment inside it:

- transparent cornea shell
- iris and crystalline lens
- anterior capsule annulus
- animated capsular flap
- circular tear guide
- forceps/needle-like tool following the tear path

By default, the scene now prefers the layered cataract textures copied from
`third_party/simulator/public/textures` and the STL models under
`assets/models`. If those files are missing, it falls back to the older
reference-frame/procedural texture generation path.

The first version prioritizes visual and interaction fidelity over clinically
validated material parameters. It matches the reference video's microscope
style with a dark background, sclera, red vessels, gray iris, red
retroillumination, orange capsular flap, and a silver forceps path.

## Quick Start

1. Install the runtime dependencies:

   ```powershell
   .\scripts\install_deps.ps1
   ```

   This installs or stages SOFA v25.12.00, ffmpeg, Python 3.12 embeddable, pip,
   and numpy. The project-local Python runtime is used only for SofaPython3.

2. Extract video reference frames:

   ```powershell
   .\scripts\extract_keyframes.ps1
   ```

3. Check the runtime environment:

   ```powershell
   .\scripts\check_env.ps1
   ```

4. Launch the SOFA scene:

   ```powershell
   .\scripts\run_capsulorhexis.ps1
   ```

   This now also opens a local parameter menu for anatomy, trocar, and
   material tuning. Use `-NoProfileMenu` if you only want the SOFA window.

## Scene Controls

When the scene is open in `runSofa`:

- click inside the 3D view first; the launch script starts the animation loop
  by default; if the SOFA GUI intercepts normal keys, hold `Ctrl` with the same
  key
- `Space` or `P`: pause/resume the automatic demo tear when `auto_tear` is enabled
- `R`: reset the tear
- `W/A/S/D` or arrow keys: move the forceps in the microscope view plane
  (`I/J/K/L` also work as fallback movement keys; use `X` or Down arrow if
  `Ctrl+S` is captured by the GUI)
- `E` / `Q`: insert/withdraw the forceps
- `C` / `V`: close/open the forceps tips
- `+` / `-`: increase/decrease tear speed
- `[` / `]`: decrease/increase tear radius
- `T`: toggle the tear guide visibility
- `M`: toggle between the overview camera and the full-screen top operating view
- `1` / `2`: switch directly to overview / top view

The default profile now uses manual tearing: close the forceps near the capsule
edge, keep the tip near the tear radius, and drag around the guide to advance
the tear. Set `simulation.auto_tear` to `true` for the older time-driven demo.
The top-left HUD shows the signed forceps-tip distance to the capsule plane,
the offset from the tear edge, current grip, and grasp state.
When grasped, a green traction line connects the forceps tip to the tear front;
the bright green arc marks the visible torn progress.
With the default profile, clamping should happen when `Tip-Capsule dz` is
roughly between `-0.04 mm` and `+0.18 mm`; the HUD will show `BITE NOW`.

See `docs/INSTRUMENT_CONTROLS_ZH.md` for the Chinese operator guide.

## Files

- `scenes/capsulorhexis.py`: SofaPython3 scene entry point and CLI helpers
- `scenes/capsulorhexis_modules`: modular scene implementation, including
  texture generation, geometry builders, asset loading, and animation controls
- `assets/capsulorhexis_profile.json`: tunable geometry and behavior defaults
- `assets/capsulorhexis_profile.custom.json`: local overrides saved from the
  parameter menu; when present, the scene loads this file first
- `assets/textures`: copied simulator cataract texture layers and generated
  fallback textures
- `assets/models`: external eye and retinal forceps STL/OFF/SCAD models
- `scripts/install_deps.ps1`: downloads SOFA v25.12.00 and installs ffmpeg
- `scripts/extract_keyframes.ps1`: extracts reference frames from the MP4
- `scripts/check_env.ps1`: validates SOFA, SofaPython3, ffmpeg, and video paths
- `scripts/run_capsulorhexis.ps1`: starts `runSofa` with SofaPython3
- `scripts/capsulorhexis_profile_editor.ps1`: local WinForms parameter menu
  for editing and saving a custom anatomy/profile JSON

## Notes

SOFA v25.12.00 Windows binaries include SofaPython3 and the Tearing plugin, but
SofaPython3 still needs a CPython 3.12 runtime and numpy on Windows. The install
script stages both in `third_party\python312`.

This project uses SofaPython3 for the first implementation. If Python-level
topology updates are not sufficient for a later, higher-fidelity tear model, add
a small C++ SOFA plugin dedicated to triangle separation along the tear path.
