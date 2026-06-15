"""
clean_smard.py
==============
Reads the two SMARD CSV exports, cleans them, and writes Parquet files.
Optionally uploads to GCS if --gcs-bucket is supplied.

Usage
-----
# Local only (outputs Parquet to the workspace output/ directory):
    python clean_smard.py

# With GCS upload:
    python clean_smard.py --gcs-bucket your-bucket-name --gcs-prefix smard/raw

Dependencies
------------
    pip install pandas pyarrow google-cloud-storage
"""

import re
import argparse
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── File paths ────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
ROOT = HERE.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GENERATION_CSV = DATA_DIR / "smard_actual_generation.csv"
PRICES_CSV     = DATA_DIR / "smard_day_ahead_prices.csv"

OUT_GENERATION = OUTPUT_DIR / "smard_actual_generation.parquet"
OUT_PRICES     = OUTPUT_DIR / "smard_day_ahead_prices.parquet"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snake(col: str) -> str:
    """
    Turn a raw SMARD column header into a clean snake_case name.

    'Wind offshore [MWh] Calculated resolutions'  →  'wind_offshore_mwh'
    'Germany/Luxembourg [€/MWh] Calculated resolutions'  →  'germany_luxembourg_eur_mwh'
    '∅ DE/LU neighbours [€/MWh] Calculated resolutions'  →  'avg_de_lu_neighbours_eur_mwh'
    """
    col = col.lstrip("\ufeff")                      # strip BOM if on first col
    col = col.replace("∅", "avg")                   # ∅ → avg
    col = col.replace("€", "eur")                   # € → eur
    col = re.sub(r"\[.*?\]", lambda m:              # keep unit text, strip brackets
                 " " + m.group(0)[1:-1].replace("/", "_"), col)
    col = re.sub(r"Calculated resolutions", "", col, flags=re.IGNORECASE)
    col = re.sub(r"[^a-z0-9]+", "_", col.lower())  # non-alnum → underscore
    col = col.strip("_")
    return col


def _parse_numeric(series: pd.Series) -> pd.Series:
    """
    Replace dash placeholders with NaN and parse comma-formatted numbers.

    SMARD uses '-' for missing values and ',' as a thousands separator.
    """
    return (
        series
        .replace("-", pd.NA)
        .astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )


def _parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert 'start_date' and 'end_date' from 'Jun 6, 2024 12:00 AM'
    to proper UTC-naive timestamps, then drop 'end_date' (it is always
    start + 1 h and adds no information).
    """
    for col in ("start_date", "end_date"):
        df[col] = pd.to_datetime(df[col], format="%b %d, %Y %I:%M %p")
    df = df.drop(columns=["end_date"])
    df = df.rename(columns={"start_date": "interval_start_utc"})
    return df


# ── Per-file cleaners ─────────────────────────────────────────────────────────

def clean_generation(path: Path) -> pd.DataFrame:
    log.info("Reading %s", path.name)
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")   # SMARD uses ; separator; utf-8-sig strips BOM

    log.info("  Raw shape: %s", df.shape)

    # Rename all columns to snake_case
    df.columns = [_snake(c) for c in df.columns]

    # Parse timestamps
    df = _parse_timestamps(df)

    # Every remaining column is a numeric energy source
    numeric_cols = [c for c in df.columns if c != "interval_start_utc"]
    for col in numeric_cols:
        df[col] = _parse_numeric(df[col])

    # Add a derived column: total_renewable_mwh
    renewable_sources = [
        "biomass_mwh", "hydropower_mwh",
        "wind_offshore_mwh", "wind_onshore_mwh",
        "photovoltaics_mwh", "other_renewable_mwh",
    ]
    present = [c for c in renewable_sources if c in df.columns]
    df["total_renewable_mwh"] = df[present].sum(axis=1, min_count=1)

    # Add renewable share (fraction of total generation)
    fossil_sources = [
        "lignite_mwh", "hard_coal_mwh",
        "fossil_gas_mwh", "nuclear_mwh",
        "other_conventional_mwh",
    ]
    fossil_present = [c for c in fossil_sources if c in df.columns]
    df["total_generation_mwh"] = df[present + fossil_present].sum(axis=1, min_count=1)
    df["renewable_share_pct"] = (
        (df["total_renewable_mwh"] / df["total_generation_mwh"] * 100)
        .round(2)
    )

    log.info("  Cleaned shape: %s", df.shape)
    _report_nulls(df)
    return df


def clean_prices(path: Path) -> pd.DataFrame:
    log.info("Reading %s", path.name)
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")

    log.info("  Raw shape: %s", df.shape)

    # Drop the DE/AT/LU column — it is 100% dashes (no data)
    all_dash = [c for c in df.columns if (df[c] == "-").all()]
    if all_dash:
        log.info("  Dropping all-dash columns: %s", all_dash)
        df = df.drop(columns=all_dash)

    # Rename
    df.columns = [_snake(c) for c in df.columns]

    # Parse timestamps
    df = _parse_timestamps(df)

    # Parse price columns
    price_cols = [c for c in df.columns if c != "interval_start_utc"]
    for col in price_cols:
        df[col] = _parse_numeric(df[col])

    log.info("  Cleaned shape: %s", df.shape)
    _report_nulls(df)
    return df


def _report_nulls(df: pd.DataFrame) -> None:
    null_summary = df.isnull().sum()
    null_summary = null_summary[null_summary > 0]
    if null_summary.empty:
        log.info("  ✓ No nulls")
    else:
        log.warning("  Null counts:\n%s", null_summary.to_string())


# ── Writer & GCS uploader ─────────────────────────────────────────────────────

def write_parquet(df: pd.DataFrame, path: Path) -> None:
    # Convert timestamps from nanoseconds to microseconds for Spark compatibility
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].astype("datetime64[us]")

    df.to_parquet(
        path,
        index=False,
        engine="pyarrow",
        coerce_timestamps="us",
        allow_truncated_timestamps=True
    )

    size_kb = path.stat().st_size / 1024
    log.info("  Written → %s  (%.1f KB)", path.name, size_kb)


def upload_to_gcs(local_path: Path, bucket_name: str, prefix: str) -> None:
    try:
        from google.cloud import storage
    except ImportError:
        log.error("google-cloud-storage not installed. Run: pip install google-cloud-storage")
        return

    blob_name = f"{prefix.rstrip('/')}/{local_path.name}"
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(str(local_path))
    log.info("  Uploaded → gs://%s/%s", bucket_name, blob_name)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Clean SMARD CSV exports and write Parquet.")
    parser.add_argument("--gcs-bucket", default=None,
                        help="GCS bucket name to upload Parquet files to (optional)")
    parser.add_argument("--gcs-prefix", default="smard/raw",
                        help="GCS object prefix (default: smard/raw)")
    parser.add_argument("--generation-csv", default=str(GENERATION_CSV),
                        help="Path to smard_actual_generation.csv")
    parser.add_argument("--prices-csv", default=str(PRICES_CSV),
                        help="Path to smard_day_ahead_prices.csv")
    args = parser.parse_args()

    # ── Generation ────────────────────────────────────────────────────────────
    gen_df = clean_generation(Path(args.generation_csv))
    write_parquet(gen_df, OUT_GENERATION)

    # ── Prices ────────────────────────────────────────────────────────────────
    pri_df = clean_prices(Path(args.prices_csv))
    write_parquet(pri_df, OUT_PRICES)

    # ── GCS upload ───────────────────────────────────────────────────
    if args.gcs_bucket:
        log.info("Uploading to GCS bucket: %s", args.gcs_bucket)
        upload_to_gcs(OUT_GENERATION, args.gcs_bucket, args.gcs_prefix)
        upload_to_gcs(OUT_PRICES,     args.gcs_bucket, args.gcs_prefix)

    log.info("Done. Next step: load Parquet into BigQuery with bq load or the Python client.")


if __name__ == "__main__":
    main()