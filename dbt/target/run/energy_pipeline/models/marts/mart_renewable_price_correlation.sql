
  
    

    create or replace table `my-project-1-480817`.`energy_dw_marts`.`mart_renewable_price_correlation`
      
    
    

    
    OPTIONS()
    as (
      -- mart_renewable_price_correlation.sql
--
-- Answers the central project question:
--   "How does renewable energy share correlate with day-ahead electricity prices?"
--
-- Groups by renewable share bucket × season × peak/off-peak.
-- Demonstrates the merit-order effect: higher renewable penetration
-- increases supply and pushes spot prices down — including into negative territory.

with hourly as (
    select * from `my-project-1-480817`.`energy_dw_marts`.`mart_hourly_energy`
)

select
    -- ── Grouping dimensions ────────────────────────────────────────────────
    renewable_share_bucket,
    season,
    is_peak_hour,
    is_weekend,
    year,

    -- ── Volume ────────────────────────────────────────────────────────────
    count(*)                                                    as hour_count,

    -- ── Renewable mix within bucket ───────────────────────────────────────
    round(avg(renewable_share_pct),     2)                      as avg_renewable_share_pct,
    round(avg(wind_share_pct),          2)                      as avg_wind_share_pct,
    round(avg(solar_share_pct),         2)                      as avg_solar_share_pct,
    round(avg(total_generation_mwh),    2)                      as avg_total_generation_mwh,
    round(avg(total_renewable_mwh),     2)                      as avg_renewable_mwh,

    -- ── Price stats within bucket ─────────────────────────────────────────
    round(avg(price_eur_mwh),           2)                      as avg_price_eur_mwh,
    round(min(price_eur_mwh),           2)                      as min_price_eur_mwh,
    round(max(price_eur_mwh),           2)                      as max_price_eur_mwh,
    round(stddev(price_eur_mwh),        2)                      as stddev_price_eur_mwh,

    -- ── Negative price incidence (merit-order signal) ─────────────────────
    countif(price_eur_mwh < 0)                                  as negative_price_hours,
    round(
        countif(price_eur_mwh < 0) / count(*) * 100,
    2)                                                          as negative_price_pct

from hourly
where price_eur_mwh is not null
group by
    renewable_share_bucket,
    season,
    is_peak_hour,
    is_weekend,
    year
order by
    year,
    season,
    renewable_share_bucket,
    is_peak_hour
    );
  