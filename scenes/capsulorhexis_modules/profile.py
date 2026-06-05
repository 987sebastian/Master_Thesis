import json
import os

from .constants import CUSTOM_PROFILE_PATH, DEFAULT_PROFILE_PATH


def _read_profile(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            profile = json.load(handle)
    except FileNotFoundError as error:
        raise RuntimeError(f"Capsulorhexis profile is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Capsulorhexis profile is not valid JSON: {path} ({error})") from error
    except OSError as error:
        raise RuntimeError(f"Unable to read capsulorhexis profile: {path} ({error})") from error
    return profile


def validate_profile(profile, path):
    if not isinstance(profile, dict):
        raise RuntimeError(f"Capsulorhexis profile must contain a JSON object: {path}")
    missing_sections = [section for section in ("geometry", "simulation", "materials") if section not in profile]
    if missing_sections:
        sections = ", ".join(missing_sections)
        raise RuntimeError(f"Capsulorhexis profile is missing required section(s): {sections}")
    return profile


def _load_profile_from_path(path):
    return validate_profile(_read_profile(path), path)


def profile_paths():
    return {
        "default": DEFAULT_PROFILE_PATH,
        "custom": CUSTOM_PROFILE_PATH,
    }


def load_default_profile():
    return _load_profile_from_path(DEFAULT_PROFILE_PATH)


def load_custom_profile():
    return _load_profile_from_path(CUSTOM_PROFILE_PATH)


def load_profile():
    if os.path.exists(CUSTOM_PROFILE_PATH):
        try:
            return load_custom_profile()
        except RuntimeError as error:
            print(f"warning: custom capsulorhexis profile ignored, falling back to default: {error}")
    return load_default_profile()


def save_custom_profile(profile):
    validate_profile(profile, CUSTOM_PROFILE_PATH)
    try:
        with open(CUSTOM_PROFILE_PATH, "w", encoding="utf-8") as handle:
            json.dump(profile, handle, indent=2)
            handle.write("\n")
    except OSError as error:
        raise RuntimeError(f"Unable to write custom capsulorhexis profile: {CUSTOM_PROFILE_PATH} ({error})") from error
    return CUSTOM_PROFILE_PATH
