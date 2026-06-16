

  create or replace view `my-project-1-480817`.`energy_dw_staging`.`stg_fact_generation_price`
  OPTIONS()
  as -- stg_fact_generation_price.sql
--
-- Staging layer over the BigQuery table fact_energy_market.
-- This table is the direct output of the PySpark Dataproc Serverless job.
--
-- Responsibilities:
--   1. Enforce correct column types
--   2. Rename price_band to spark_price_band to distinguish from dbt's richer version
--   3. Filter out null timestamps and invalid prices
--   4. No business logic — that lives in intermediate and mart models

with source as (
    select * from `my-project-1-480817`.`energy_dw`.`fact_energy_market`
),
typed as (
    select
        -- ── Timestamp ────────────────────────────────────────────────────────
        cast(interval_start_utc     as timestamp)   as interval_start_utc,

        -- ── Renewable generation (MWh) ───────────────────────────────────────
        cast(biomass_mwh            as float64)     as biomass_mwh,
        cast(hydropower_mwh         as float64)     as hydropower_mwh,
        cast(wind_offshore_mwh      as float64)     as wind_offshore_mwh,
        cast(wind_onshore_mwh       as float64)     as wind_onshore_mwh,
        cast(photovoltaics_mwh      as float64)     as photovoltaics_mwh,
        cast(other_renewable_mwh    as float64)     as other_renewable_mwh,

        -- ── Totals ───────────────────────────────────────────────────────────
        cast(total_renewable_mwh    as float64)     as total_renewable_mwh,
        cast(total_generation_mwh   as float64)     as total_generation_mwh,
        cast(renewable_share_pct    as float64)     as renewable_share_pct,

        -- ── Price ────────────────────────────────────────────────────────────
        cast(price_eur_mwh          as float64)     as price_eur_mwh,

        -- ── Cross-border flows (ENTSO-E, may be null for hours with no data) ─
        cast(total_exports_mwh      as float64)     as total_exports_mwh,
        cast(total_imports_mwh      as float64)     as total_imports_mwh,
        cast(net_flow_mwh           as float64)     as net_flow_mwh,
        cast(trade_position         as string)      as trade_position,

        -- ── Time dimensions (pre-computed by Spark) ──────────────────────────
        cast(date                   as date)        as date,
        cast(hour                   as int64)       as hour,
        extract(year  from cast(interval_start_utc as timestamp)) as year,
        extract(month from cast(interval_start_utc as timestamp)) as month,
        cast(day_of_week            as int64)       as day_of_week,
        cast(is_weekend             as bool)        as is_weekend,
        cast(season                 as string)      as season,

        -- Rename to make clear this is Spark's price label
        cast(price_band             as string)      as spark_price_band

    from source
    where interval_start_utc is not null
      and cast(price_eur_mwh as float64) > -500
)
select * from typed;

