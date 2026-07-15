"""
Convert a signs_zip_{ZIP}.csv (from 01_query_sims_by_zip.py) into the
signs_data.json lookup file the browser extension needs. Standalone script,
no Jupyter or AI assistant required.

Usage:
    python 02_generate_signs_data.py 10002

Reads:
    signs_zip_10002.csv           (in the current directory)
Writes:
    signs_data.json                (in the current directory - copy this into
                                     the extension folder, replacing the
                                     existing one, then reload the extension
                                     in chrome://extensions)
"""
import sys
import json

import pandas as pd


def main(zip_code: str):
    csv_path = f"signs_zip_{zip_code}.csv"
    df = pd.read_csv(csv_path).dropna(subset=["latitude", "longitude"])
    df["lat_r"] = df["latitude"].round(7)
    df["lon_r"] = df["longitude"].round(7)

    corners = []
    for i, ((lat_r, lon_r), group) in enumerate(df.groupby(["lat_r", "lon_r"])):
        signs = [
            {
                "order_number": row.order_number,
                "sign_code": row.sign_code,
                "sign_location": row.sign_location,
                "support": row.support,
            }
            for row in group.itertuples()
        ]
        corners.append(
            {
                "corner_id": f"{zip_code}_{i:03d}",
                "on_street": group.iloc[0]["on_street"],
                "from_street": group.iloc[0]["from_street"],
                "latitude": float(group.iloc[0]["latitude"]),
                "longitude": float(group.iloc[0]["longitude"]),
                "signs": signs,
            }
        )

    out_path = "signs_data.json"
    with open(out_path, "w") as f:
        json.dump({"zip": zip_code, "corners": corners}, f, indent=0)

    total_signs = sum(len(c["signs"]) for c in corners)
    print(f"Wrote {len(corners)} corners, {total_signs} total sign records to {out_path}")
    print("Now copy this file into the extension folder (overwrite signs_data.json)")
    print("and reload the extension in chrome://extensions.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python 02_generate_signs_data.py <ZIP_CODE>")
    main(sys.argv[1])
