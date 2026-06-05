import os

MODULE_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
DEFAULT_PROFILE_PATH = os.path.join(ROOT_DIR, "assets", "capsulorhexis_profile.json")
CUSTOM_PROFILE_PATH = os.path.join(ROOT_DIR, "assets", "capsulorhexis_profile.custom.json")
PROFILE_PATH = DEFAULT_PROFILE_PATH
TEXTURE_DIR = os.path.join(ROOT_DIR, "assets", "textures")
REFERENCE_DIR = os.path.join(ROOT_DIR, "assets", "reference")
MODEL_DIR = os.path.join(ROOT_DIR, "assets", "models")
TEXTURE_MANIFEST_PATH = os.path.join(TEXTURE_DIR, "texture_manifest.json")
EYE_MODEL_PATH = os.path.join(MODEL_DIR, "eye.stl")
FORCEPS_MODEL_PATH = os.path.join(MODEL_DIR, "Retinal_Peeling_Forceps.stl")
TROCAR_TEXTURE_PATH = os.path.join(TEXTURE_DIR, "trocar.png")
TEXTURE_GENERATOR_VERSION = 3
SIMULATOR_TEXTURE_MODE = "third_party_simulator_cataract_layers"
SIMULATOR_TEXTURE_FILENAMES = {
    "sclera": "cataract-anterior-segment.png",
    "limbus": "cataract-limbus.png",
    "iris": "cataract-iris.png",
    "red_reflex": "cataract-red-reflex.png",
    "retro": "cataract-red-reflex.png",
    "lens_surface": "cataract-lens-surface.png",
    "capsule": "cataract-anterior-capsule.png",
    "flap": "cataract-anterior-capsule.png",
    "posterior_capsule": "cataract-posterior-capsule.png",
    "cortex": "cataract-cortex.png",
    "nucleus": "cataract-nucleus.png",
    "corneal_reflection": "cataract-corneal-reflection.png",
    "metal": "forceps_real_photo_texture.png",
}
IMAGE_GENERATED_TEXTURE_MODE = "image2_texture_atlas_real_tissue"
IMAGE_GENERATED_TEXTURE_FILENAMES = {
    "sclera": "sclera_image2_real_tissue.png",
    "iris": "iris_image2_real_tissue.png",
    "retro": "retroillumination_image2_real_tissue.png",
    "capsule": "capsule_membrane_image2_real_tissue.png",
    "flap": "capsular_flap_image2_real_tissue.png",
    "metal": "forceps_real_photo_texture.png",
}
PROCEDURAL_FALLBACK_TEXTURE_FILENAMES = {
    "sclera": "sclera_real_photo_texture.png",
    "iris": "iris_real_photo_texture.png",
    "retro": "retroillumination_real_photo_texture.png",
    "capsule": "capsule_membrane_real_photo_texture.png",
    "flap": "capsular_flap_real_photo_texture.png",
    "metal": "forceps_real_photo_texture.png",
}
STABLE_TEXTURE_MODES = {SIMULATOR_TEXTURE_MODE, IMAGE_GENERATED_TEXTURE_MODE}
REFERENCE_FRAME_NAMES = [
    "keyframe_00s.png",
    "keyframe_02s.png",
    "keyframe_04s.png",
    "keyframe_06s.png",
    "keyframe_08s.png",
    "keyframe_10s.png",
    "keyframe_12s.png",
]
