-- mart_hourly_energy.sql
--
-- Core analytical fact table. One row per hour.
-- Materialized as a physical table in BigQuery for fast BI queries.
--
-- This is the primary table to use for:
--   - Presentation charts and findings
--   - Ad-hoc SQL analysis
--   - Any downstream visualization tool

with enriched as (
    select * from {{ ref('int_enriched_generation_price') }}
)

select
    -- ── Identifiers & time ─────────────────────────────────────────────────
    interval_start_utc,
    date,
    year,
    month,
    hour,
    day_of_week,
    is_weekend,
    is_peak_hour,
    season,

    -- ── Categorical dimensions ─────────────────────────────────────────────
    renewable_share_bucket,
    price_band,
    spark_price_band,
    trade_position,

    -- ── Renewable generation (MWh) ─────────────────────────────────────────
    biomass_mwh,
    hydropower_mwh,
    wind_offshore_mwh,
    wind_onshore_mwh,
    photovoltaics_mwh,
    other_renewable_mwh,
    total_wind_mwh,
    total_renewable_mwh,
    total_generation_mwh,

    -- ── Renewable share metrics ────────────────────────────────────────────
    renewable_share_pct,
    wind_share_pct,
    solar_share_pct,
    biomass_share_pct,

    -- ── Price ──────────────────────────────────────────────────────────────
    price_eur_mwh,

    -- ── Cross-border flows ─────────────────────────────────────────────────
    total_exports_mwh,
    total_imports_mwh,
    net_flow_mwh,

    -- ── Market value proxy ─────────────────────────────────────────────────
    market_value_keur,
    renewable_market_value_keur

from enriched
order by interval_start_utc
