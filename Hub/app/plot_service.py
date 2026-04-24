from io import BytesIO
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def plot_verisini_hazirla(file_path: str | Path, adim: int = 100) -> dict:
    df = pd.read_parquet(file_path)

    downsampled = df.iloc[::adim].copy()

    ilk_ts = downsampled["ts_ns"].iloc[0]
    downsampled["relative_time_ms"] = (downsampled["ts_ns"] - ilk_ts) / 1_000_000

    return {
        "relative_time_ms": downsampled["relative_time_ms"].tolist(),
        "x": downsampled["x"].tolist(),
        "y": downsampled["y"].tolist(),
        "z": downsampled["z"].tolist(),
        "sample_count": len(df),
        "downsampled_count": len(downsampled),
        "step": adim,
    }


def plot_png_hazirla(file_path: str | Path, adim: int = 100) -> bytes:
    df = pd.read_parquet(file_path)

    downsampled = df.iloc[::adim].copy()

    ilk_ts = downsampled["ts_ns"].iloc[0]
    zaman_ms = (downsampled["ts_ns"] - ilk_ts) / 1_000_000

    fig, ax = plt.subplots(figsize=(12, 6))

    ax.plot(zaman_ms, downsampled["x"], label="x")
    ax.plot(zaman_ms, downsampled["y"], label="y")
    ax.plot(zaman_ms, downsampled["z"], label="z")

    ax.set_title("Ivme Verisi Grafiği")
    ax.set_xlabel("Zaman (ms)")
    ax.set_ylabel("İvme")
    ax.legend()
    ax.grid(True)

    buffer = BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png")
    plt.close(fig)

    buffer.seek(0)
    return buffer.getvalue()