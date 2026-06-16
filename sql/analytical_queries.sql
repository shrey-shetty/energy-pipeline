-- ============================================================
-- ANALYTICAL QUERIES — SMARD Energy Intelligence Pipeline
-- Run these in BigQuery against your dbt mart tables.
-- Dataset: my-project-1-480817.energy_dw
-- ============================================================


-- ── Query 1: Merit-order effect ───────────────────────────────────────────────
-- Headline result: as renewable share rises, average price falls.
-- Expected output: ~4 rows, avg_price decreasing as bucket number increases.

SELECT
    renewable_share_bucket,
    COUNT(*)                                    AS hour_count,
    ROUND(AVG(renewable_share_pct), 1)          AS avg_renewable_pct,
    ROUND(AVG(price_eur_mwh), 2)                AS avg_price_eur_mwh,
    ROUND(MIN(price_eur_mwh), 2)                AS min_price_eur_mwh,
    ROUND(MAX(price_eur_mwh), 2)                AS max_price_eur_mwh,
    COUNTIF(price_eur_mwh < 0)                  AS negative_price_hours,
    ROUND(COUNTIF(price_eur_mwh < 0) / COUNT(*) * 100, 1) AS negative_price_pct
FROM `my-project-1-480817.energy_dw_marts.mart_hourly_energy`
GROUP BY renewable_share_bucket
ORDER BY renewable_share_bucket;


-- ── Query 2: Seasonal patterns ────────────────────────────────────────────────
-- Which season has the most renewables? The cheapest prices?

SELECT
    season,
    ROUND(AVG(avg_renewable_share_pct), 1)      AS avg_renewable_share_pct,
    ROUND(AVG(avg_price_eur_mwh), 2)            AS avg_price_eur_mwh,
    ROUND(AVG(daily_wind_mwh), 0)               AS avg_daily_wind_mwh,
    ROUND(AVG(daily_solar_mwh), 0)              AS avg_daily_solar_mwh,
    SUM(negative_price_hours)                   AS total_negative_price_hours
FROM `my-project-1-480817.energy_dw_marts.mart_daily_summary`
GROUP BY season
ORDER BY
    CASE season
        WHEN 'Winter' THEN 1 WHEN 'Spring' THEN 2
        WHEN 'Summer' THEN 3 WHEN 'Autumn' THEN 4
    END;


-- ── Query 3: Peak vs off-peak by season ───────────────────────────────────────
-- Shows the interaction between time-of-use and renewable generation.

SELECT
    season,
    is_peak_hour,
    COUNT(*)                                    AS hour_count,
    ROUND(AVG(renewable_share_pct), 1)          AS avg_renewable_pct,
    ROUND(AVG(price_eur_mwh), 2)                AS avg_price_eur_mwh,
    ROUND(STDDEV(price_eur_mwh), 2)             AS price_stddev
FROM `my-project-1-480817.energy_dw_marts.mart_hourly_energy`
GROUP BY season, is_peak_hour
ORDER BY season, is_peak_hour;


-- ── Query 4: Top 10 cheapest hours ───────────────────────────────────────────
-- Negative price events — caused by excess renewable output.

SELECT
    interval_start_utc,
    season,
    hour,
    is_weekend,
    ROUND(renewable_share_pct, 1)               AS renewable_share_pct,
    ROUND(total_wind_mwh, 0)                    AS wind_mwh,
    ROUND(photovoltaics_mwh, 0)                 AS solar_mwh,
    ROUND(price_eur_mwh, 2)                     AS price_eur_mwh
FROM `my-project-1-480817.energy_dw_marts.mart_hourly_energy`
ORDER BY price_eur_mwh ASC
LIMIT 10;


-- ── Query 5: Monthly trend ────────────────────────────────────────────────────
-- Renewable share and price evolution over time.

SELECT
    year,
    month,
    COUNT(*)                                    AS days,
    ROUND(AVG(avg_renewable_share_pct), 1)      AS avg_renewable_share_pct,
    ROUND(AVG(avg_price_eur_mwh), 2)            AS avg_price_eur_mwh,
    SUM(negative_price_hours)                   AS negative_price_hours
FROM `my-project-1-480817.energy_dw_marts.mart_daily_summary`
GROUP BY year, month
ORDER BY year, month;
