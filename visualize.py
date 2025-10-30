# visualize.py
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

def plot_summary(csv_path, out_png="output/failure_chart.png"):
    df = pd.read_csv(csv_path)
    if df.empty:
        print("No data to plot")
        return
    df = df.sort_values("count", ascending=False)
    plt.figure(figsize=(8,4))
    plt.bar(df["category"], df["count"])
    plt.xlabel("Error Category")
    plt.ylabel("Count")
    plt.title("Failure Distribution by Category")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png)
    print(f"Saved chart to {out_png}")

if __name__ == "__main__":
    import sys
    csv = sys.argv[1] if len(sys.argv)>1 else "output/failure_summary.csv"
    plot_summary(csv)
