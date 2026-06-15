import pandas as pd

print("Actual Generation file columns:")
print(pd.read_parquet("output/smard_actual_generation.parquet").columns.tolist())

print("\nDay-Ahead Prices file columns:")
print(pd.read_parquet("output/smard_day_ahead_prices.parquet").columns.tolist())