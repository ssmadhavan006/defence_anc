import pandas as pd
import os

def investigate_pesq(csv_path="results/eval_raw.csv"):
    if not os.path.exists(csv_path):
        print(f"File missing: {csv_path}")
        return

    df = pd.read_csv(csv_path)
    print(f"Total rows in {csv_path}: {len(df)}")
    
    null_pesq = df["pesq_wb"].isna().sum()
    non_null_pesq = df["pesq_wb"].notna().sum()
    
    print(f"PESQ-WB Null Count    : {null_pesq} / {len(df)} ({null_pesq/len(df)*100:.1f}%)")
    print(f"PESQ-WB Non-Null Count: {non_null_pesq} / {len(df)} ({non_null_pesq/len(df)*100:.1f}%)")

    print("\n--- Breakdown by Method ---")
    method_gb = df.groupby("method")["pesq_wb"].agg(
        total="count",
        valid=lambda x: x.notna().sum(),
        nulls=lambda x: x.isna().sum(),
        mean="mean"
    )
    print(method_gb.to_string())

    print("\n--- Breakdown by Category ---")
    cat_gb = df.groupby("category")["pesq_wb"].agg(
        total="count",
        valid=lambda x: x.notna().sum(),
        nulls=lambda x: x.isna().sum(),
        mean="mean"
    )
    print(cat_gb.to_string())

if __name__ == "__main__":
    investigate_pesq()
