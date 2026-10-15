"""Enrichment database/pegawai.db: kolom turunan (satuan kerja, potensi, sertifikat).

Idempotent - aman dijalankan ulang (dan WAJIB dijalankan ulang setelah
re-extract, karena extract menghapus kolom enrichment).

Sumber sertifikat (per NIP):
  - PNT/SNT/BNT : database/sertifikat/rev4_Database Sertifikat Kompetensi ...xlsx
                   sheet AKTIF (header baris 4): NIP=C, JENIS SERTIFIKAT
                   KOMPETENSI=L, NOMOR SERTIFIKAT=M (baris berjenis PNT/SNT/BNT).
  - PBJ/PPK     : database/sertifikat/SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx
                   sheet PBJ & PPK (header baris 3): NIP=G, NOMOR=B.

Kolom yang dibuat/diisi ulang (semua TEXT):
  UNIT KERJA / SATUAN KERJA, POTENSI MENJABAT, SERTIFIKAT PNT/SNT/BNT/PBJ/PPK
  (isi nomor sertifikat; >1 nomor per NIP digabung "; "; kosong = tidak punya),
  POTENSI PPK (PNT dan (PBJ atau PPK)), POTENSI BENDAHARA (BNT),
  POTENSI PPSPM (SNT).

Kolom lama "SATUAN KERJA" (versi sebelumnya) otomatis di-rename ke nama baru.

Pakai:
    python scripts/enrich_pegawai.py
    python scripts/enrich_pegawai.py --db path/pegawai.db

Cetak ringkasan angka saja - tanpa isi baris (PII).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "database" / "pegawai.db"
SERTIF_DIR = ROOT / "database" / "sertifikat"

FILE_AKTIF = "rev4_Database Sertifikat Kompetensi 2026_1AprilClean-DESKTOP-G1DUSIC.xlsx"
FILE_PBJ_PPK = "SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx"

SERTIFIKAT_COLS = ["SERTIFIKAT PNT", "SERTIFIKAT SNT", "SERTIFIKAT BNT",
                   "SERTIFIKAT PBJ", "SERTIFIKAT PPK"]
ENRICH_COLS = ["UNIT KERJA / SATUAN KERJA", "POTENSI MENJABAT", *SERTIFIKAT_COLS,
               "POTENSI PPK", "POTENSI BENDAHARA", "POTENSI PPSPM"]
LEGACY_SATUAN = "SATUAN KERJA"  # nama kolom lama -> di-rename saat migrasi

SEKRETARIAT_PS = "Sekretariat Direktorat Jenderal Prasarana Strategis"
# "Pelaksanaan Prasarana Strategis <Wilayah>" - wilayah bisa ada newline.
# Kecocokan berupa angka romawi (I/II/III) dilewati: itu penomoran PPK
# ("PPK Pelaksanaan Prasarana Strategis II, Pelaksanaan Prasarana Strategis
#  Jawa Barat, ...") - wilayah yang benar ada di kecocokan berikutnya.
RE_PS = re.compile(r"Pelaksanaan Prasarana Strategis\s+([^,\n]+)", re.IGNORECASE)
RE_ROMAWI = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)$", re.IGNORECASE)

KATA_TEKNIK = ("PELAKSANA TEKNIK", "PETUGAS TEKNIK", "PENATA TEKNIK")
KATA_PEMIMPIN = ("DIREKTUR", "SEKRETARIS", "KEPALA", "BENDAHARA",
                 "BENDAHARAWAN", "PEJABAT")


def norm_nip(v: object) -> str:
    """Normalisasi NIP dari xlsx/teks: buang spasi & ekor '.0' (angka Excel)."""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace(" ", "")
    return s


def valid_nip(s: str) -> bool:
    return len(s) >= 10 and s.isdigit()


def satuan_kerja(unit_kerja: str, jabatan_lengkap: str) -> str:
    # Hanya baris sekretariat PS yang dipecah ke wilayah; unit lain disalin
    # apa adanya (aturan ini TIDAK berlaku di luar sekretariat PS).
    if unit_kerja.strip().upper() != SEKRETARIAT_PS.upper():
        return unit_kerja.strip()
    for m in RE_PS.finditer(jabatan_lengkap):
        wilayah = " ".join(m.group(1).split())
        if wilayah and not RE_ROMAWI.match(wilayah):
            return f"Pelaksanaan Prasarana Strategis {wilayah}"
    return SEKRETARIAT_PS


def potensi_menjabat(jenis_jabatan: str, jabatan_lengkap: str,
                     jabatan_rangkap: str) -> str:
    j = jenis_jabatan.strip().upper()
    jl = jabatan_lengkap.upper()
    jr = jabatan_rangkap.upper()
    if not j:
        return ""
    if j in ("JABATAN STRUKTURAL", "JABATAN LAINNYA"):
        return "tidak"
    if j == "JABATAN PERBENDAHARAAN":
        return "ya" if any(k in jl for k in KATA_TEKNIK) else "tidak"
    if j in ("JABATAN FUNGSIONAL", "JABATAN PELAKSANA"):
        return "tidak" if any(k in jr for k in KATA_PEMIMPIN) else "ya"
    return ""  # jenis tak dikenal -> kosong


def load_sertifikat() -> dict[str, dict[str, list[str]]]:
    """-> {jenis: {nip: [nomor, ...]}}; jenis di PNT/SNT/BNT/PBJ/PPK."""
    out: dict[str, dict[str, list[str]]] = {k: {} for k in
                                            ("PNT", "SNT", "BNT", "PBJ", "PPK")}

    def add(jenis: str, nip: object, nomor: object) -> None:
        n = norm_nip(nip)
        if not valid_nip(n):
            return
        nom = str(nomor).strip()
        if not nom:
            return
        bucket = out[jenis].setdefault(n, [])
        if nom not in bucket:  # pertahankan urut kemunculan; buang duplikat
            bucket.append(nom)

    f_aktif = SERTIF_DIR / FILE_AKTIF
    if f_aktif.is_file():
        df = pd.read_excel(f_aktif, sheet_name="AKTIF", header=3,
                           dtype=str, keep_default_na=False)
        for _, r in df.iterrows():
            jenis = str(r.get("JENIS SERTIFIKAT KOMPETENSI", "")).strip().upper()
            if jenis in ("PNT", "SNT", "BNT"):
                add(jenis, r.get("NIP", ""), r.get("NOMOR SERTIFIKAT", ""))
    else:
        print(f"PERINGATAN: tidak ada {f_aktif.name} - sertifikat PNT/SNT/BNT kosong")

    f_pp = SERTIF_DIR / FILE_PBJ_PPK
    if f_pp.is_file():
        for jenis in ("PBJ", "PPK"):
            df = pd.read_excel(f_pp, sheet_name=jenis, header=2,
                               dtype=str, keep_default_na=False)
            for _, r in df.iterrows():
                add(jenis, r.get("NIP", ""), r.get("Nomor Sertifikat", ""))
    else:
        print(f"PERINGATAN: tidak ada {f_pp.name} - sertifikat PBJ/PPK kosong")

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB), help="path SQLite pegawai")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        sys.exit(f"{db_path} tidak ada - jalankan: python scripts/extract_pegawai.py")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(pegawai)")}
        for c in ("NIP", "UNIT KERJA", "JABATAN LENGKAP", "JENIS JABATAN"):
            if c not in cols:
                sys.exit(f"kolom wajib tidak ada di DB: {c}")

        # Migrasi nama kolom lama: SATUAN KERJA -> UNIT KERJA / SATUAN KERJA.
        if LEGACY_SATUAN in cols:
            if "UNIT KERJA / SATUAN KERJA" in cols:
                con.execute(
                    'ALTER TABLE pegawai DROP COLUMN "' + LEGACY_SATUAN + '"'
                )
            else:
                con.execute(
                    'ALTER TABLE pegawai RENAME COLUMN "'
                    + LEGACY_SATUAN + '" TO "UNIT KERJA / SATUAN KERJA"'
                )

        for c in ENRICH_COLS:
            try:
                con.execute(
                    'ALTER TABLE pegawai ADD COLUMN "' + c.replace('"', '""') + '" TEXT'
                )
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise

        sert = load_sertifikat()
        rows = con.execute(
            'SELECT id, NIP, "UNIT KERJA", "JABATAN LENGKAP", "JENIS JABATAN",'
            ' "JABATAN RANGKAP" FROM pegawai'
        ).fetchall()

        stats = {"satuan_ps": 0, "satuan_fallback": 0,
                 "menjabat_ya": 0, "menjabat_tidak": 0, "menjabat_kosong": 0}
        updates = []
        for r in rows:
            sk = satuan_kerja(r["UNIT KERJA"] or "", r["JABATAN LENGKAP"] or "")
            if (r["UNIT KERJA"] or "").strip().upper() == SEKRETARIAT_PS.upper():
                if sk.upper() != SEKRETARIAT_PS.upper():
                    stats["satuan_ps"] += 1
                else:
                    stats["satuan_fallback"] += 1
            pm = potensi_menjabat(r["JENIS JABATAN"] or "", r["JABATAN LENGKAP"] or "",
                            r["JABATAN RANGKAP"] or "")
            stats["menjabat_" + (pm or "kosong")] += 1

            nip = norm_nip(r["NIP"] or "")
            nomor = {t: "; ".join(sert[t].get(nip, [])) for t in sert}
            punya = {t: bool(nomor[t]) for t in sert}
            updates.append((
                sk, pm,
                nomor["PNT"], nomor["SNT"], nomor["BNT"],
                nomor["PBJ"], nomor["PPK"],
                "ya" if punya["PNT"] and (punya["PBJ"] or punya["PPK"]) else "tidak",
                "ya" if punya["BNT"] else "tidak",
                "ya" if punya["SNT"] else "tidak",
                r["id"],
            ))

        con.executemany(
            'UPDATE pegawai SET "UNIT KERJA / SATUAN KERJA"=?,'
            ' "POTENSI MENJABAT"=?,'
            ' "SERTIFIKAT PNT"=?, "SERTIFIKAT SNT"=?, "SERTIFIKAT BNT"=?,'
            ' "SERTIFIKAT PBJ"=?, "SERTIFIKAT PPK"=?, "POTENSI PPK"=?,'
            ' "POTENSI BENDAHARA"=?, "POTENSI PPSPM"=? WHERE id=?',
            updates,
        )

        # Catat riwayat enrichment di meta (api_meta memakai key spesifik - aman).
        con.execute("INSERT OR REPLACE INTO meta VALUES ('enriched_at', ?)",
                    (pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),))
        con.commit()
    finally:
        con.close()

    # Ringkasan angka saja - tanpa NIP/nama (PII).
    print(f"baris          : {len(updates)}")
    print(f"unit/satuan kerja: {stats['satuan_ps']} PS wilayah,"
          f" {stats['satuan_fallback']} fallback sekretariat,"
          f" sisanya salin UNIT KERJA")
    print(f"potensi menjabat: {stats['menjabat_ya']} ya,"
          f" {stats['menjabat_tidak']} tidak,"
          f" {stats['menjabat_kosong']} kosong")
    for t in ("PNT", "SNT", "BNT", "PBJ", "PPK"):
        n_rows = sum(1 for u in updates if u[2 + ("PNT", "SNT", "BNT", "PBJ", "PPK").index(t)])
        print(f"sertifikat {t:<4}: {len(sert[t])} NIP di sumber,"
              f" {n_rows} baris pegawai terisi nomor")
    for i, name in ((7, "POTENSI PPK"), (8, "POTENSI BENDAHARA"), (9, "POTENSI PPSPM")):
        print(f"{name:<16}: {sum(1 for u in updates if u[i] == 'ya')} ya")


if __name__ == "__main__":
    main()
