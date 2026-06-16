-- mart_daily_summary.sql
--
-- Daily aggregation of generation and price metrics.
-- One row per calendar day.
-- Used for time-series charts and seasonal breakdowns in the presentation.

with hourly as (
    select * from `my-project-1-480817`.`energy_dw_marts`.`mart_hourly_energy`
)

select
    -- ── Time dimensions ────────────────────────────────────────────────────
    date,
    year,
    month,
    season,
    is_weekend,

    -- ── Daily generation totals (MWh) ──────────────────────────────────────
    round(sum(total_generation_mwh),    2)  as daily_generation_mwh,
    round(sum(total_renewable_mwh),     2)  as daily_renewable_mwh,
    round(sum(total_wind_mwh),          2)  as daily_wind_mwh,
    round(sum(photovoltaics_mwh),       2)  as daily_solar_mwh,
    round(sum(biomass_mwh),             2)  as daily_biomass_mwh,
    round(sum(hydropower_mwh),          2)  as daily_hydro_mwh,

    -- ── Daily renewable share ──────────────────────────────────────────────
    round(avg(renewable_share_pct),     2)  as avg_renewable_share_pct,
    round(max(renewable_share_pct),     2)  as max_renewable_share_pct,
    round(min(renewable_share_pct),     2)  as min_renewable_share_pct,

    -- ── Daily price statistics ─────────────────────────────────────────────
    round(avg(price_eur_mwh),           2)  as avg_price_eur_mwh,
    round(min(price_eur_mwh),           2)  as min_price_eur_mwh,
    round(max(price_eur_mwh),           2)  as max_price_eur_mwh,

    -- ── Negative price hours (key renewable market signal) ─────────────────
    countif(price_eur_mwh < 0)              as negative_price_hours,

    -- ── Row count (24 = complete day) ──────────────────────────────────────
    count(*)                                as hour_count

from hourly
group by date, year, month, season, is_weekend
order by date