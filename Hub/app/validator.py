from pathlib import Path

import pandas as pd


BEKLENEN_KOLONLAR = ["ts_ns", "x", "y", "z", "fs_hz", "seq"]
BEKLENEN_FS_HZ = 3200
BEKLENEN_SAMPLE_SAYISI = 32000


def packet_dogrula(file_path: str | Path) -> tuple[bool, str | None]:
    path = Path(file_path)

    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        return False, f"Parquet dosyasi okunamadi: {exc}"

    mevcut_kolonlar = list(df.columns)

    if mevcut_kolonlar != BEKLENEN_KOLONLAR:
        return False, (
            f"Kolonlar hatali. Beklenen={BEKLENEN_KOLONLAR}, "
            f"gelen={mevcut_kolonlar}"
        )

    if len(df) != BEKLENEN_SAMPLE_SAYISI:
        return False, (
            f"Sample sayisi hatali. Beklenen={BEKLENEN_SAMPLE_SAYISI}, "
            f"gelen={len(df)}"
        )

    farkli_fs_degerleri = df["fs_hz"].dropna().unique()

    if len(farkli_fs_degerleri) != 1:
        return False, f"Birden fazla fs_hz degeri var: {farkli_fs_degerleri.tolist()}"

    if int(farkli_fs_degerleri[0]) != BEKLENEN_FS_HZ:
        return False, (
            f"fs_hz hatali. Beklenen={BEKLENEN_FS_HZ}, "
            f"gelen={int(farkli_fs_degerleri[0])}"
        )

    return True, None