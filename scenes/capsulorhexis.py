import argparse
import os
import sys

SCENE_DIR = os.path.dirname(__file__)
if SCENE_DIR not in sys.path:
    sys.path.insert(0, SCENE_DIR)

from capsulorhexis_modules.scene import createScene, dry_run
from capsulorhexis_modules.textures import ensure_texture_assets


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="validate generated meshes without SOFA")
    parser.add_argument("--regenerate-textures", action="store_true", help="refresh texture assets and manifest")
    args = parser.parse_args()
    if args.regenerate_textures:
        for name, path in ensure_texture_assets(force=True).items():
            print(f"{name}: {path}")
    if args.dry_run:
        dry_run()
