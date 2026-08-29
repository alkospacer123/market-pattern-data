from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("cycle11", "research/cycle11_nonlinear_pnl_block.py")
cycle11 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cycle11)


def clean_X_writable(df, features):
    # Technical compatibility fix only: pandas/NumPy may return a read-only
    # view. The preregistered transformation is unchanged; we merely request
    # a writable copy before replacing non-finite values with NaN.
    X = df[features].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float, copy=True)
    X[~np.isfinite(X)] = np.nan
    return X


cycle11.clean_X = clean_X_writable


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--block-index", type=int, required=True)
    a = ap.parse_args()
    cycle11.run(a.data_root, a.output, a.block_index)
