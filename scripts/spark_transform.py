"""
PySpark Transformation Job - SMARD + ENTSO-E Energy Intelligence Pipeline
Reads:
  - SMARD generation Parquet        (GCS raw/)
  - SMARD day-ahead prices Parquet  (GCS raw/)
  - ENTSO-E cross-border flows CSV  (GCS raw/)

Joins all three and writes analytical output to GCS staging for BigQuery.

Analytical Question:
    How does renewable energy share correlate with day-ahead electricity prices
    in Germany, and how do cross-border electricity flows influence that relationship?
"""

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# ── Config ────────────────────────────────────────────────────────────────────
GCS_BUCKET       = "gs://energy-market-data-platform-480817"
INPUT_GENERATION = f"{GCS_BUCKET}/raw/smard_actual_generation.parquet"
INPUT_PRICES     = f"{GCS_BUCKET}/raw/smard_day_ahead_prices.parquet"
INPUT_FLOWS      = f"{GCS_BUCKET}/raw/entsoe_crossborder_flows.csv"
OUTPUT_PATH      = f"{GCS_BUCKET}/staging/fact_energy_market"
# ─────────────────────────────────────────────────────────────────────────────


def create_spark_session():
    return (
        SparkSession.builder
        .appName("Energy_Market_Transform")
        .getOrCreate()
    )


def read_parquet(spark, path: str):
    return spark.read.parquet(path)


def read_flows(spark, path: str):
    """
    Read ENTSO-E cross-border flows CSV.

    Schema (output of ingest_entsoe.py):
        hour_utc, neighbor, total_exports_mwh, total_imports_mwh

    CSV is already aggregated by neighbor and hour. Parse the timestamp
    and proceed directly to hourly aggregation.
    """
    return (
        spark.read
        .option("header", "true")
        .option("inferSchema", "true")
        .csv(path)
        .withColumn(
            "hour_utc",
            F.to_timestamp("hour_utc", "yyyy-MM-dd HH:mm:ssX")
        )
    )


def aggregate_flows(flows_df):
    """
    Sum exports and imports across all neighbors per hour to get
    Germany's total cross-border position for that hour.

    Input (one row per hour × neighbor):
        hour_utc | neighbor | total_exports_mwh | total_imports_mwh

    Output (one row per hour):
        hour_utc | total_exports_mwh | total_imports_mwh | net_flow_mwh
    """
    agg = flows_df.groupBy("hour_utc").agg(
        F.sum("total_exports_mwh").alias("total_exports_mwh"),
        F.sum("total_imports_mwh").alias("total_imports_mwh")
    )

    agg = agg.withColumn(
        "net_flow_mwh",
        F.col("total_exports_mwh") - F.col("total_imports_mwh")
    )

    return agg


def transform(gen_df, price_df, flows_agg_df):
    """
    1. Join generation + prices on interval_start_utc
    2. Join with aggregated cross-border flows on hour_utc
    3. Derive time dimensions
    4. Add analytical labels (price band, trade position)
    """

    # ── Join generation + prices ──────────────────────────────────────────────
    df = gen_df.join(price_df, on="interval_start_utc", how="inner")

    df = df.select(
        "interval_start_utc",

        # Renewable sources
        "biomass_mwh",
        "hydropower_mwh",
        "wind_offshore_mwh",
        "wind_onshore_mwh",
        "photovoltaics_mwh",
        "other_renewable_mwh",

        # Totals
        "total_renewable_mwh",
        "total_generation_mwh",
        "renewable_share_pct",

        # Price
        F.col("germany_luxembourg_eur_mwh").alias("price_eur_mwh"),
    )

    # ── Join with cross-border flows ──────────────────────────────────────────
    # Join key: interval_start_utc (SMARD, hourly) == hour_utc (ENTSO-E, already hourly)
    # Left join: keep all SMARD rows even if no ENTSO-E data for that hour
    df = df.join(
        flows_agg_df,
        df["interval_start_utc"] == flows_agg_df["hour_utc"],
        how="left"
    ).drop("hour_utc")

    # ── Time dimensions ───────────────────────────────────────────────────────
    df = (
        df
        .withColumn("date",        F.to_date("interval_start_utc"))
        .withColumn("hour",        F.hour("interval_start_utc"))
        .withColumn("year",        F.year("interval_start_utc"))
        .withColumn("month",       F.month("interval_start_utc"))
        .withColumn("day_of_week", F.dayofweek("interval_start_utc"))
        .withColumn("is_weekend",  F.dayofweek("interval_start_utc").isin([1, 7]))
        .withColumn("season",
            F.when(F.month("interval_start_utc").isin([12, 1, 2]), "Winter")
             .when(F.month("interval_start_utc").isin([3, 4, 5]),  "Spring")
             .when(F.month("interval_start_utc").isin([6, 7, 8]),  "Summer")
             .otherwise("Autumn")
        )
    )

    # ── Price band label ──────────────────────────────────────────────────────
    df = df.withColumn("price_band",
        F.when(F.col("price_eur_mwh") < 0,   "Negative")
         .when(F.col("price_eur_mwh") < 50,  "Low")
         .when(F.col("price_eur_mwh") < 100, "Medium")
         .otherwise("High")
    )

    # ── Trade position label ──────────────────────────────────────────────────
    # Unknown only when ENTSO-E data is missing for that hour (left join miss)
    df = df.withColumn("trade_position",
        F.when(F.col("net_flow_mwh").isNull(),   "Unknown")
         .when(F.col("net_flow_mwh") > 0,        "Net Exporter")
         .when(F.col("net_flow_mwh") < 0,        "Net Importer")
         .otherwise("Balanced")
    )

    # ── Filter out bad prices ─────────────────────────────────────────────────
    df = df.filter(
        F.col("price_eur_mwh").isNotNull() &
        (F.col("price_eur_mwh") > -500)
    )

    return df


def write_output(df, path: str):
    """Write to GCS as Parquet, partitioned by year and month."""
    (
        df.write
        .mode("overwrite")
        .partitionBy("year", "month")
        .parquet(path)
    )
    print(f"✅ Written to {path}")


def main():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    print("📥 Reading SMARD generation data...")
    gen_df = read_parquet(spark, INPUT_GENERATION)

    print("📥 Reading SMARD day-ahead prices...")
    price_df = read_parquet(spark, INPUT_PRICES)

    print("📥 Reading ENTSO-E cross-border flows...")
    flows_df = read_flows(spark, INPUT_FLOWS)

    print("⚙️  Aggregating cross-border flows across neighbors...")
    flows_agg_df = aggregate_flows(flows_df)

    print("⚙️  Transforming and joining all three sources...")
    result_df = transform(gen_df, price_df, flows_agg_df)

    print(f"📊 Row count: {result_df.count()}")

    # Sanity check: how many hours still have Unknown trade position?
    unknown_count = result_df.filter(F.col("trade_position") == "Unknown").count()
    total_count   = result_df.count()
    print(f"⚠️  Unknown trade position: {unknown_count} / {total_count} rows "
          f"({100 * unknown_count / total_count:.1f}%)")

    result_df.printSchema()
    result_df.show(5, truncate=False)

    print("📤 Writing to GCS staging...")
    write_output(result_df, OUTPUT_PATH)

    spark.stop()


if __name__ == "__main__":
    main()