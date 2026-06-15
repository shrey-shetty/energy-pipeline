"""
ingest_entsoe.py
────────────────
Fetches Cross-Border Physical Flows (A11) from the ENTSO-E Transparency Platform
for Germany (DE-LU) ↔ France, Netherlands, Austria, Poland, Denmark, Switzerland.

Saves output to:
  data/entsoe_crossborder_flows.csv

Then uploads to:
  gs://<GCS_BUCKET>/raw/entsoe_crossborder_flows.csv

Usage:
  python scripts/ingest_entsoe.py                          # yesterday → today (real-time default)
  python scripts/ingest_entsoe.py --start 2024-06-01 --end 2024-12-31   # backfill
  python scripts/ingest_entsoe.py --date 2024-06-01        # single day

Environment variables:
  ENTSOE_API_TOKEN   your ENTSO-E security token
  GCS_BUCKET         e.g. energy-market-data-platform-480817
"""

import os
import time
import logging
import argparse
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from pathlib import Path

import requests
import pandas as pd
from google.cloud import storage

# ── Config ────────────────────────────────────────────────────────────────────

API_TOKEN  = os.environ.get("ENTSOE_API_TOKEN", "YOUR_ENTSOE_API_TOKEN")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "energy-market-data-platform-480817")
GCS_OBJECT = "raw/entsoe_crossborder_flows.csv"
BASE_URL   = "https://web-api.tp.entsoe.eu/api"

# Retry settings
MAX_RETRIES    = 3
RETRY_DELAY_S  = 10   # seconds between retries

# Paths relative to project root (script lives in scripts/, data in data/)
SCRIPT_DIR  = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
OUTPUT_CSV  = PROJECT_DIR / "data" / "entsoe_crossborder_flows.csv"

# Germany-Luxembourg bidding zone EIC
DE_LU = "10Y1001A1001A82H"

# Neighboring countries EIC codes
NEIGHBORS = {
    "FR": "10YFR-RTE------C",
    "NL": "10YNL----------L",
    "AT": "10YAT-APG------L",
    "PL": "10YPL-AREA-----S",
    "DK": "10Y1001A1001A65H",
    "CH": "10YCH-SWISSGRIDZ",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_str(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


def _fetch_xml(params: dict) -> ET.Element | None:
    """Fetch one API call with retries on timeout or server errors."""
    params["securityToken"] = API_TOKEN
    log.info("  Fetching %s → %s", params.get("in_Domain", "?"), params.get("out_Domain", "?"))

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=60)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            if "Acknowledgement_MarketDocument" in root.tag:
                reason = root.findtext(".//{*}text") or "unknown"
                log.warning("  No data returned: %s", reason)
                return None
            return root

        except requests.exceptions.ReadTimeout:
            log.warning("  Timeout on attempt %d/%d. Retrying in %ds...",
                        attempt, MAX_RETRIES, RETRY_DELAY_S)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                log.error("  All %d attempts timed out. Skipping this request.", MAX_RETRIES)
                return None

        except requests.exceptions.HTTPError as e:
            log.warning("  HTTP error on attempt %d/%d: %s. Retrying in %ds...",
                        attempt, MAX_RETRIES, e, RETRY_DELAY_S)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_S)
            else:
                log.error("  All %d attempts failed with HTTP error. Skipping.", MAX_RETRIES)
                return None


def _parse_flows(root: ET.Element, direction: str, neighbor: str) -> list[dict]:
    """Parse raw XML into a list of flow records at native resolution."""
    rows = []
    for period in root.findall(".//{*}Period"):
        resolution = period.findtext("{*}resolution") or "PT60M"
        start_str  = period.findtext("{*}timeInterval/{*}start")
        if not start_str:
            continue
        start_dt  = datetime.strptime(start_str, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        delta_min = 60 if "60" in resolution else 15
        for point in period.findall("{*}Point"):
            pos = int(point.findtext("{*}position") or 1)
            qty = float(point.findtext("{*}quantity") or "nan")
            ts  = start_dt + timedelta(minutes=delta_min * (pos - 1))
            rows.append({
                "timestamp_utc": ts,          # keep as datetime for aggregation
                "neighbor":      neighbor,
                "direction":     direction,
                "flow_mwh":      qty,
            })
    return rows


def _aggregate_to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """
    Roll up 15-min or mixed-resolution ENTSO-E data to hourly intervals
    so it aligns with SMARD's hourly timestamps.

    Adds:
      hour_utc         — truncated to the hour  (join key with SMARD)
      is_export        — True when Germany is the exporting party
      total_exports_mwh / total_imports_mwh per hour
    """
    df["hour_utc"] = df["timestamp_utc"].dt.floor("h")
    df["is_export"] = df["direction"].str.startswith("DE_to_")

    agg = (
        df.groupby(["hour_utc", "neighbor"])
        .agg(
            total_exports_mwh=("flow_mwh", lambda s: s[df.loc[s.index, "is_export"]].sum()),
            total_imports_mwh=("flow_mwh", lambda s: s[~df.loc[s.index, "is_export"]].sum()),
        )
        .reset_index()
    )
    return agg


# ── Core ──────────────────────────────────────────────────────────────────────

def fetch_flows(start: datetime, end: datetime) -> pd.DataFrame:
    """Fetch all neighbor flows for a date range and return as hourly DataFrame."""
    all_rows = []
    current  = start

    while current < end:
        next_day = current + timedelta(days=1)
        log.info("Fetching flows for %s", current.strftime("%Y-%m-%d"))

        for code, eic in NEIGHBORS.items():
            base = {
                "documentType": "A11",
                "periodStart":  _period_str(current),
                "periodEnd":    _period_str(next_day),
            }
            # Exports: DE → neighbor
            root = _fetch_xml({**base, "in_Domain": DE_LU, "out_Domain": eic})
            if root is not None:
                all_rows.extend(_parse_flows(root, f"DE_to_{code}", code))

            # Imports: neighbor → DE
            root = _fetch_xml({**base, "in_Domain": eic, "out_Domain": DE_LU})
            if root is not None:
                all_rows.extend(_parse_flows(root, f"{code}_to_DE", code))

        current = next_day

    if not all_rows:
        log.warning("No data collected for the requested period.")
        return pd.DataFrame()

    raw_df = pd.DataFrame(all_rows)
    raw_df["timestamp_utc"] = pd.to_datetime(raw_df["timestamp_utc"], utc=True)
    raw_df = raw_df.sort_values(["timestamp_utc", "neighbor"]).reset_index(drop=True)

    log.info("Raw rows fetched: %d (native resolution)", len(raw_df))

    # Aggregate to hourly so timestamps align with SMARD
    hourly_df = _aggregate_to_hourly(raw_df)
    hourly_df = hourly_df.sort_values(["hour_utc", "neighbor"]).reset_index(drop=True)

    log.info("Hourly rows after aggregation: %d", len(hourly_df))
    return hourly_df


def save_csv(df: pd.DataFrame) -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    log.info("Saved %d rows → %s", len(df), OUTPUT_CSV)


def upload_to_gcs(df: pd.DataFrame) -> None:
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob   = bucket.blob(GCS_OBJECT)
    blob.upload_from_string(df.to_csv(index=False), content_type="text/csv")
    log.info("Uploaded → gs://%s/%s", GCS_BUCKET, GCS_OBJECT)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch ENTSO-E cross-border flows")
    parser.add_argument("--date",  help="Single date YYYY-MM-DD")
    parser.add_argument("--start", help="Range start YYYY-MM-DD (inclusive)")
    parser.add_argument("--end",   help="Range end   YYYY-MM-DD (exclusive)")
    args = parser.parse_args()

    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end   = datetime.strptime(args.end,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
    elif args.date:
        start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end   = start + timedelta(days=1)
    else:
        # ── Real-time default: yesterday → today ──────────────────────────────
        # This is what runs in the scheduled pipeline.
        # Each daily run fetches the previous day's flows and appends to GCS.
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start = today - timedelta(days=1)
        end   = today
        log.info("No date args supplied — defaulting to yesterday (%s)", start.strftime("%Y-%m-%d"))

    log.info("Fetching ENTSO-E cross-border flows: %s → %s",
             start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    df = fetch_flows(start, end)

    if df.empty:
        log.error("No data fetched. Check your API token and date range.")
        return

    log.info("── Step 1: Save CSV locally ──")
    save_csv(df)

    log.info("── Step 2: Upload to GCS ──")
    upload_to_gcs(df)

    log.info("Done. Preview:")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()