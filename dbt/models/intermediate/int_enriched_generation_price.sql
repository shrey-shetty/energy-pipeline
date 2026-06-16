-- int_enriched_generation_price.sql
--
-- Enrichment layer on top of the staging model.
-- Spark already computed the core joins and basic time dimensions.
-- dbt adds the analytical enrichments that belong in the warehouse layer:
--   - Finer-grained price band (5 tiers vs Spark's 3)
--   - Renewable share quartile buckets for dimensional analysis
--   - Wind and solar share as % of total generation
--   - Peak/off-peak classification (not in Spark output)
--   - Cross-source wind total
--   - Cross-border flow columns passed through from staging

with base as (
    select * from {{ ref('stg_fact_generation_price') }}
)
select
    -- ── Pass-through from staging ──────────────────────────────────────────
    interval_start_utc,
    date,
    hour,
    year,
    month,
    day_of_week,
    is_weekend,
    season,
    spark_price_band,

    -- ── Generation columns ─────────────────────────────────────────────────
    biomass_mwh,
    hydropower_mwh,
    wind_offshore_mwh,
    wind_onshore_mwh,
    photovoltaics_mwh,
    other_renewable_mwh,
    total_renewable_mwh,
    total_generation_mwh,
    renewable_share_pct,
    price_eur_mwh,

    -- ── Cross-border flows (from ENTSO-E via staging) ──────────────────────
    total_exports_mwh,
    total_imports_mwh,
    net_flow_mwh,
    trade_position,

    -- ── dbt-derived: combined wind ─────────────────────────────────────────
    round(wind_offshore_mwh + wind_onshore_mwh, 2)                 as total_wind_mwh,

    -- ── dbt-derived: source shares as % of total ──────────────────────────
    round(safe_divide(wind_offshore_mwh + wind_onshore_mwh,
                      total_generation_mwh) * 100, 2)              as wind_share_pct,
    round(safe_divide(photovoltaics_mwh,
                      total_generation_mwh) * 100, 2)              as solar_share_pct,
    round(safe_divide(biomass_mwh,
                      total_generation_mwh) * 100, 2)              as biomass_share_pct,

    -- ── dbt-derived: peak hour flag ────────────────────────────────────────
    case
        when is_weekend = false and hour between 8 and 19
        then true else false
    end                                                             as is_peak_hour,

    -- ── dbt-derived: finer price band (5 tiers) ───────────────────────────
    case
        when price_eur_mwh < 0   then 'Negative'
        when price_eur_mwh < 50  then 'Low (0–50)'
        when price_eur_mwh < 100 then 'Medium (50–100)'
        when price_eur_mwh < 200 then 'High (100–200)'
        else                          'Very High (>200)'
    end                                                             as price_band,

    -- ── dbt-derived: renewable share quartile buckets ─────────────────────
    case
        when renewable_share_pct < 25  then '1 — Low (0–25%)'
        when renewable_share_pct < 50  then '2 — Medium-Low (25–50%)'
        when renewable_share_pct < 75  then '3 — Medium-High (50–75%)'
        else                                '4 — High (75–100%)'
    end                                                             as renewable_share_bucket,

    -- ── dbt-derived: approximate market value proxy ───────────────────────
    round(total_generation_mwh * price_eur_mwh / 1000, 2)         as market_value_keur,
    round(total_renewable_mwh  * price_eur_mwh / 1000, 2)         as renewable_market_value_keur

from base
