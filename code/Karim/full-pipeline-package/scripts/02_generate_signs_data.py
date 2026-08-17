"""
Convert a signs_zip_{ZIP}.csv (from 01_query_sims_by_zip.py) into the
signs_data.json lookup file the browser extension needs. Standalone script,
no Jupyter or AI assistant required.

Pass the same ZIP code(s) you gave 01_query_sims_by_zip.py, in the same
order, so the CSV filename matches. Pass EVERY zip you want the extension
to cover, not just a new one -- this always writes a complete
signs_data.json for exactly the zip codes passed, it does not merge with
whatever the extension currently has.

Usage:
    python 02_generate_signs_data.py 10002
    python 02_generate_signs_data.py 10001 10003
    python 02_generate_signs_data.py 10001 10003 --out path/to/signs_data.json
    python 02_generate_signs_data.py cb301 --csv signs_zip_cb301.csv

Reads:
    signs_zip_10002.csv            (in the current directory)
    signs_zip_10001_10003.csv      (multiple ZIPs)
    --csv PATH                     (overrides the above -- read this exact
                                     file instead of deriving a filename from
                                     the zip codes/label. The label argument
                                     is still required and still drives the
                                     output "zip" field and corner_id prefix,
                                     e.g. for 01_query_sims_by_community_board.py's
                                     output, which isn't named signs_zip_{ZIP}.csv)
Writes:
    ../extension/signs_data.json   (default -- correct when this script sits
                                     under ML Project/scripts/, a sibling of
                                     ML Project/extension/. Pass --out to
                                     override for a different layout, e.g.
                                     the partner package's pull_more_sims_data.bat,
                                     where backend/scripts/ and the top-level
                                     extension/ aren't a simple parent/child.
                                     Reload the extension in
                                     chrome://extensions afterward, and if
                                     you're rebuilding a shareable package,
                                     re-run build_extension_package.py, which
                                     will hard-fail until EXPECTED_ZIPS in
                                     that script is updated to match)
"""
import sys
import json
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_PATH = SCRIPT_DIR.parent / "extension" / "signs_data.json"


def main(zip_codes: list[str], out_path=DEFAULT_OUT_PATH, csv_path=None):
    label = "_".join(zip_codes)
    if csv_path is None:
        csv_path = f"signs_zip_{label}.csv"
    df = pd.read_csv(csv_path).dropna(subset=["latitude", "longitude"])
    df["lat_r"] = df["latitude"].round(7)
    df["lon_r"] = df["longitude"].round(7)

    corners = []
    for i, ((lat_r, lon_r), group) in enumerate(df.groupby(["lat_r", "lon_r"])):
        signs = [
            {
                "order_number": row.order_number,
                "sign_code": row.sign_code,
                "sign_description": row.sign_description,
                "sign_location": row.sign_location,
                "support": row.support,
            }
            for row in group.itertuples()
        ]
        corners.append(
            {
                "corner_id": f"{label}_{i:03d}",
                "on_street": group.iloc[0]["on_street"],
                "from_street": group.iloc[0]["from_street"],
                "latitude": float(group.iloc[0]["latitude"]),
                "longitude": float(group.iloc[0]["longitude"]),
                # State Plane feet (EPSG:2263), straight from the source API --
                # this is the same CRS Cyclomedia Street Smart reports its own
                # X/Y in, so it lets a Cyclomedia-side matcher compare directly
                # in feet instead of needing a live lat/lon reprojection in JS.
                "x_2263": float(group.iloc[0]["sign_x_coord"]),
                "y_2263": float(group.iloc[0]["sign_y_coord"]),
                "signs": signs,
            }
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"zip": zip_codes, "corners": corners}, f, indent=0)

    total_signs = sum(len(c["signs"]) for c in corners)
    print(f"Wrote {len(corners)} corners, {total_signs} total sign records to {out_path}")
    print("Reload the extension in chrome://extensions to pick up the new data.")
    print("If you're rebuilding a shareable package, update EXPECTED_ZIPS in")
    print("build_extension_package.py to match, then re-run it.")


def _extract_flag(args, flag):
    """Pulls a `flag VALUE` pair out of args if present. Returns
    (remaining_args, value_or_None). Raises SystemExit if the flag is
    present with nothing after it."""
    if flag not in args:
        return args, None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        raise SystemExit(f"{flag} requires a path argument")
    value = args[idx + 1]
    remaining = args[:idx] + args[idx + 2:]
    return remaining, value


def parse_cli_args(args):
    """args: sys.argv[1:]-shaped list. Returns (zip_codes, out_path, csv_path)
    -- out_path/csv_path are None when their flag wasn't passed, so callers
    can fall back to DEFAULT_OUT_PATH / the derived signs_zip_{label}.csv.
    Raises SystemExit for missing zip codes or a flag with nothing after it."""
    if not args:
        raise SystemExit(
            "Usage: python 02_generate_signs_data.py <ZIP_CODE> [ZIP_CODE ...] "
            "[--out PATH] [--csv PATH]"
        )
    args, cli_out_path = _extract_flag(args, "--out")
    args, cli_csv_path = _extract_flag(args, "--csv")
    if not args:
        raise SystemExit("At least one ZIP code is required")
    out_path = Path(cli_out_path) if cli_out_path is not None else None
    csv_path = Path(cli_csv_path) if cli_csv_path is not None else None
    return args, out_path, csv_path


if __name__ == "__main__":
    zip_codes, cli_out_path, cli_csv_path = parse_cli_args(sys.argv[1:])
    main(
        zip_codes,
        out_path=cli_out_path if cli_out_path is not None else DEFAULT_OUT_PATH,
        csv_path=cli_csv_path,
    )
