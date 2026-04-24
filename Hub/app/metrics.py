from pathlib import Path

import pandas as pd


def paket_metriklerini_hesapla(file_path: str | Path) -> dict:
    df = pd.read_parquet(file_path)

    return {
        "downsample_method": "full_aggregate",
        "n_samples": len(df),
        "mean_x": float(df["x"].mean()),
        "mean_y": float(df["y"].mean()),
        "mean_z": float(df["z"].mean()),
        "rms_x": float((df["x"] ** 2).mean() ** 0.5),
        "rms_y": float((df["y"] ** 2).mean() ** 0.5),
        "rms_z": float((df["z"] ** 2).mean() ** 0.5),
        "peak_x": float(df["x"].abs().max()),
        "peak_y": float(df["y"].abs().max()),
        "peak_z": float(df["z"].abs().max()),
    }