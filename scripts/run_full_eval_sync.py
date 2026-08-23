import sys
sys.path.insert(0, ".")
from eval.run_eval import run_evaluation

if __name__ == "__main__":
    df_raw, df_summary, exclusions = run_evaluation()
    print("\n=== FULL 1,500 EVALUATION RUN COMPLETE ===")
    print(f"Total rows in eval_raw.csv: {len(df_raw)}")
    print(f"Total valid PESQ scores: {df_raw['pesq_wb'].notna().sum()} / {len(df_raw)}")
