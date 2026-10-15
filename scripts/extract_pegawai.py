"""Ekstraksi laporan pegawai (xlsx) -> SQLite database/pegawai.db.

Default membaca file terbaru di database/pegawai/laporan-pegawai-*.xlsx.
Idempotent: tabel selalu dibuat ulang; file sumber tidak pernah diubah.

Pakai:
    python scripts/extract_pegawai.py
    python scripts/extract_pegawai.py --xlsx "path/laporan-pegawai-xxx.xlsx"
    python scripts/extract_pegawai.py --db "path/pegawai.db"

Enrichment (tambah kolom) tidak perlu ubah skrip:
    sqlite3 database/pegawai.db "ALTER TABLE pegawai ADD COLUMN <nama> TEXT"
Kolom baru otomatis muncul di picker webapp (API membaca PRAGMA table_info).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = ROOT / "database" / "pegawai"
DEFAULT_DB = ROOT / "database" / "pegawai.db"
SHEET = "laporan-pegawai"

# Kolom yang digabung jadi teks pencarian (padanan FINDER TEXT di Excel).
# NIP & nama dipilih dulu supaya ranking pencarian masuk akal.
FINDER_FIELDS = [
    "NIP",
    "NAMA LENGKAP",
    "NAMA JABATAN",
    "JENIS JABATAN",
    "JENJANG JABATAN",
    "GOLONGAN",
    "UNIT ORGANISASI",
    "UNIT KERJA",
    "STATUS PEGAWAI",
]

# Kolom sistem: tidak ditawarkan ke user sebagai kolom data.
HIDDEN_COLUMNS = {"id", "finder_text"}


def pick_source(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            sys.exit(f"File tidak ditemukan: {p}")
        return p
    candidates = sorted(
        DEFAULT_SOURCES.glob("laporan-pegawai-*.xlsx"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        sys.exit(f"Tidak ada laporan-pegawai-*.xlsx di {DEFAULT_SOURCES}")
    return candidates[-1]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", help="path xlsx sumber (default: terbaru di database/pegawai/)")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="path output SQLite")
    args = ap.parse_args()

    src = pick_source(args.xlsx)
    t0 = time.time()
    df = pd.read_excel(src, sheet_name=SHEET, dtype=str, keep_default_na=False)
    read_sec = time.time() - t0

    # NO dipertahankan apa adanya; semua sel dipaksa string (NIP & tanggal memang text).
    df = df.astype(str)
    df.columns = [str(c).strip() for c in df.columns]

    dup_cols = df.columns[df.columns.duplicated()].tolist()
    if dup_cols:
        sys.exit(f"Header duplikat di sumber: {dup_cols}")
    for f in FINDER_FIELDS:
        if f not in df.columns:
            sys.exit(f"Kolom wajib untuk finder_text tidak ada di sumber: {f}")

    df["finder_text"] = (
        df[FINDER_FIELDS]
        .apply(lambda r: " ".join(v for v in r if v), axis=1)
        .str.upper()
    )

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    con = sqlite3.connect(db_path)
    try:
        cols_sql = ", ".join(f"{quote_ident(c)} TEXT" for c in df.columns)
        con.execute(f'CREATE TABLE pegawai (id INTEGER PRIMARY KEY, {cols_sql})')

        headers = list(df.columns)
        placeholders = ", ".join("?" for _ in headers)
        col_sql = ", ".join(quote_ident(c) for c in headers)
        t1 = time.time()
        con.executemany(
            f"INSERT INTO pegawai ({col_sql}) VALUES ({placeholders})",
            df.itertuples(index=False, name=None),
        )
        insert_sec = time.time() - t1

        con.execute('CREATE INDEX idx_pegawai_nip ON pegawai("NIP")')
        con.execute('CREATE INDEX idx_pegawai_unit ON pegawai("UNIT KERJA")')

        # Uji pencarian (tanpa mencetak isi baris - PII).
        t2 = time.time()
        cur = con.execute(
            "SELECT COUNT(*) FROM pegawai WHERE "
            + " AND ".join("finder_text LIKE ?" for _ in ("AGUS", "PRASARANA")),
            ("%AGUS%", "%PRASARANA%"),
        )
        hits = cur.fetchone()[0]
        search_sec = time.time() - t2

        con.execute(
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        meta = {
            "source": src.name,
            "source_path": str(src),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sheet": SHEET,
            "rows": str(len(df)),
            "columns": str(len(df.columns) - 1),  # tanpa finder_text
        }
        con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
        con.commit()
    finally:
        con.close()

    print(f"sumber      : {src.name}")
    print(f"database    : {db_path}")
    print(f"baris       : {len(df)}  kolom data: {len(df.columns) - 1}")
    print(
        f"waktu       : baca xlsx {read_sec:.1f}s, insert {insert_sec:.1f}s, "
        f"search sample {search_sec * 1000:.0f}ms ({hits} cocok)"
    )


if __name__ == "__main__":
    main()
