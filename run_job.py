import os
import runpy
import sys
from pathlib import Path


ALLOWED_SCRIPTS = {
    "Dable_API_daily.py",
    "facebook_api_daily_cmb.py",
    "facebook_api_image.py",
    "GoogleAds_API_daily.py",
    "GoogleAds_Pmax.py",
    "line_api_daily_cmb.py",
    "popin_api_daily_cmb.py",
    "Union_mediaTables.py",
}

SECRET_FILES = {
    "GOOGLEADS_TOKEN_PY": "GoogleAds_api_token_Han.py",
    "DABLE_TOKEN_PY": "Dable_Parm_token.py",
    "META_TOKEN_PY": "meta_token.py",
    "BQ_MAIN_JSON": "eco-carver-356809-38c8914cd90f.json",
    "BQ_SHEETS_JSON": "eco-carver-356809-a5ccbfde00b9.json",
}


def write_secret_files() -> None:
    for env_name, filename in SECRET_FILES.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        path = Path("/app") / filename
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)


def main() -> int:
    write_secret_files()

    script = os.environ.get("SCRIPT")
    if not script:
        print("SCRIPT environment variable is required", file=sys.stderr)
        return 2

    script_name = Path(script).name
    if script_name not in ALLOWED_SCRIPTS:
        print(f"Unsupported script: {script_name}", file=sys.stderr)
        return 2

    script_path = Path("/app") / script_name
    if not script_path.exists():
        print(f"Script not found: {script_path}", file=sys.stderr)
        return 2

    print(f"Starting {script_name}")
    runpy.run_path(str(script_path), run_name="__main__")
    print(f"Finished {script_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
