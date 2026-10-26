"""Enrichment database/pegawai.db: kolom turunan (satuan kerja, potensi, sertifikat).

Idempotent - aman dijalankan ulang (dan WAJIB dijalankan ulang setelah
re-extract, karena extract menghapus kolom enrichment). Duplikat NIP dihapus
(baris dengan id terkecil dipertahankan) sebelum kolom turunan dihitung.

Sumber sertifikat (per NIP):
  - PNT/SNT/BNT : database/sertifikat/rev4_Database Sertifikat Kompetensi ...xlsx
                   sheet AKTIF (header baris 4): NIP=C, JENIS SERTIFIKAT
                   KOMPETENSI=L, NOMOR SERTIFIKAT=M (baris berjenis PNT/SNT/BNT).
  - PBJ/PPK     : database/sertifikat/SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx
                   sheet PBJ & PPK (header baris 3): NIP=G, NOMOR=B.

Kolom yang dibuat/diisi ulang (semua TEXT):
  UNIT KERJA / SATUAN KERJA, URUTAN UNIT ORGANISASI, URUTAN UNKER / SATKER PS,
  POTENSI MENJABAT, SERTIFIKAT PNT/SNT/BNT/PBJ/PPK
  (isi nomor sertifikat; >1 nomor per NIP digabung "; "; kosong = tidak punya),
  POTENSI PPK (PNT dan (PBJ atau PPK)), POTENSI BENDAHARA (BNT),
  POTENSI PPSPM (SNT), PROPINSI2,
  TEKNIK PS (ya bila RIWAYAT PENDIDIKAN memuat istilah teknik/program studi
  terkait, Indonesia/Inggris), JENIS JABATAN2 (salinan JENIS JABATAN, diganti
  JABATAN PERBENDAHARAAN bila JABATAN RANGKAP memuat KEPALA/BENDAHARA/PEJABAT).

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
URUTAN_COLS = ["URUTAN UNIT ORGANISASI", "URUTAN UNKER / SATKER PS"]
ENRICH_COLS = ["UNIT KERJA / SATUAN KERJA", *URUTAN_COLS, "POTENSI MENJABAT",
               *SERTIFIKAT_COLS,
               "POTENSI PPK", "POTENSI BENDAHARA", "POTENSI PPSPM", "PROPINSI2",
               "TEKNIK PS", "JENIS JABATAN2"]
LEGACY_SATUAN = "SATUAN KERJA"  # nama kolom lama -> di-rename saat migrasi

# Urutan baku unit organisasi (angka 1-10 sesuai urutan di organisasi).
URUTAN_UNIT_ORGANISASI = (
    "Sekretariat Jenderal",
    "Direktorat Jenderal Sumber Daya Air",
    "Direktorat Jenderal Bina Marga",
    "Direktorat Jenderal Cipta Karya",
    "Direktorat Jenderal Prasarana Strategis",
    "Direktorat Jenderal Bina Konstruksi",
    "Direktorat Jenderal Pembiayaan Infrastruktur Pekerjaan Umum",
    "Inspektorat Jenderal",
    "Badan Pengembangan Infrastruktur Wilayah",
    "Badan Pengembangan Sumber Daya Manusia",
)

# Urutan unit kerja/satuan kerja di Direktorat Jenderal Prasarana Strategis.
URUTAN_UNKER_PS = (
    "Sekretariat Direktorat Jenderal Prasarana Strategis",
    "Direktorat Sistem dan Strategi Penyelenggaraan Prasarana Strategis",
    "Direktorat Infrastruktur Dukungan Pendidikan",
    "Direktorat Infrastruktur Dukungan Perekonomian, Peribadatan, Kesehatan, "
    "Olahraga dan Sosial Budaya",
    "Direktorat Kepatuhan Intern",
    "Pelaksanaan Prasarana Strategis Aceh",
    "Pelaksanaan Prasarana Strategis Sumatera Utara",
    "Pelaksanaan Prasarana Strategis Sumatera Barat",
    "Pelaksanaan Prasarana Strategis Riau",
    "Pelaksanaan Prasarana Strategis Kepulauan Riau",
    "Pelaksanaan Prasarana Strategis Jambi",
    "Pelaksanaan Prasarana Strategis Bengkulu",
    "Pelaksanaan Prasarana Strategis Sumatera Selatan",
    "Pelaksanaan Prasarana Strategis Kepulauan Bangka Belitung",
    "Pelaksanaan Prasarana Strategis Lampung",
    "Pelaksanaan Prasarana Strategis Jakarta Metropolitan",
    "Pelaksanaan Prasarana Strategis Jawa Barat",
    "Pelaksanaan Prasarana Strategis Banten",
    "Pelaksanaan Prasarana Strategis Jawa Tengah",
    "Pelaksanaan Prasarana Strategis D.I. Yogyakarta",
    "Pelaksanaan Prasarana Strategis Jawa Timur",
    "Pelaksanaan Prasarana Strategis Bali",
    "Pelaksanaan Prasarana Strategis Nusa Tenggara Barat",
    "Pelaksanaan Prasarana Strategis Nusa Tenggara Timur",
    "Pelaksanaan Prasarana Strategis Kalimantan Barat",
    "Pelaksanaan Prasarana Strategis Kalimantan Tengah",
    "Pelaksanaan Prasarana Strategis Kalimantan Selatan",
    "Pelaksanaan Prasarana Strategis Kalimantan Timur",
    "Pelaksanaan Prasarana Strategis Kalimantan Utara",
    "Pelaksanaan Prasarana Strategis Sulawesi Utara",
    "Pelaksanaan Prasarana Strategis Sulawesi Tengah",
    "Pelaksanaan Prasarana Strategis Sulawesi Selatan",
    "Pelaksanaan Prasarana Strategis Sulawesi Tenggara",
    "Pelaksanaan Prasarana Strategis Gorontalo",
    "Pelaksanaan Prasarana Strategis Sulawesi Barat",
    "Pelaksanaan Prasarana Strategis Maluku",
    "Pelaksanaan Prasarana Strategis Maluku Utara",
    "Pelaksanaan Prasarana Strategis Papua",
    "Pelaksanaan Prasarana Strategis Papua Barat",
)

URUTAN_UNIT_ORGANISASI_MAP = {
    " ".join(nama.split()).casefold(): str(i)
    for i, nama in enumerate(URUTAN_UNIT_ORGANISASI, start=1)
}
URUTAN_UNKER_PS_MAP = {
    " ".join(nama.split()).casefold(): str(i)
    for i, nama in enumerate(URUTAN_UNKER_PS, start=1)
}


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

# Istilah program studi untuk TEKNIK PS (Indonesia + padanan Inggris).
KATA_TEKNIK_PS = (
    "Arsitektur", "Architecture",
    "Sipil", "Civil",
    "Mesin", "Mechanical",
    "Elektro", "Electrical",
    "Perencanaan", "Planning",
    "Planologi", "Urban and Regional Planning",
    "Desain Interior", "Interior Design",
    "Teknik Fisika", "Engineering Physics",
    "Konstruksi", "Construction",
    "Gedung", "Building",
    "Lingkungan", "Environmental",
    "Infrastruktur", "Infrastructure",
    "Geologi", "Geology",
    "Geografi", "Geography",
    "Magister Teknik Studi Pembangunan",
    "Master of Engineering in Development Studies",
    "Geodesi", "Geodetic",
)

# JENIS JABATAN2 -> JABATAN PERBENDAHARAAN bila JABATAN RANGKAP memuat ini.
KATA_JENIS_JABATAN2 = ("KEPALA", "BENDAHARA", "PEJABAT")


def norm_nip(v: object) -> str:
    """Normalisasi NIP dari xlsx/teks: buang spasi & ekor '.0' (angka Excel)."""
    s = str(v).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace(" ", "")
    return s


def valid_nip(s: str) -> bool:
    return len(s) >= 10 and s.isdigit()


def norm_teks(v: object) -> str:
    """Uppercase, non-alfanumerik -> spasi, lalu rapikan spasi.

    Dipakai agar variasi spasi/tanda baca di RIWAYAT PENDIDIKAN tetap cocok,
    mis. "Magister Teknik, Studi Pembangunan" == "MAGISTER TEKNIK STUDI
    PEMBANGUNAN".
    """
    s = re.sub(r"[^A-Z0-9]+", " ", str(v or "").upper())
    return " ".join(s.split())


KATA_TEKNIK_PS_NORM = tuple(norm_teks(k) for k in KATA_TEKNIK_PS)


def teknik_ps(riwayat_pendidikan: str) -> str:
    """ya bila RIWAYAT PENDIDIKAN memuat salah satu istilah KATA_TEKNIK_PS."""
    teks = norm_teks(riwayat_pendidikan)
    return "ya" if any(k in teks for k in KATA_TEKNIK_PS_NORM) else "tidak"


def jenis_jabatan2(jenis_jabatan: str, jabatan_rangkap: str) -> str:
    """Salin JENIS JABATAN; ganti bila JABATAN RANGKAP memuat kata terkait."""
    if any(k in (jabatan_rangkap or "").upper() for k in KATA_JENIS_JABATAN2):
        return "JABATAN PERBENDAHARAAN"
    return (jenis_jabatan or "").strip()


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


def wilayah_ps(jabatan_lengkap: str) -> str:
    """Ekstrak nama wilayah dari 'Pelaksanaan Prasarana Strategis {wilayah}'.

    Hanya untuk baris sekretariat PS. Angka romawi (I/II/III = nomor PPK)
    dilewati; ambil kecocokan wilayah berikutnya. Hasil upper-case, tanpa
    menambah wilayah yang tidak ada di sumber.
    """
    for m in RE_PS.finditer(jabatan_lengkap):
        wilayah = " ".join(m.group(1).split())
        if wilayah and not RE_ROMAWI.match(wilayah):
            return wilayah.upper()
    return ""


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
            ' "JABATAN RANGKAP", "PROPINSI", "RIWAYAT PENDIDIKAN" FROM pegawai'
        ).fetchall()

        stats = {"satuan_ps": 0, "satuan_fallback": 0,
                 "menjabat_ya": 0, "menjabat_tidak": 0, "menjabat_kosong": 0,
                 "propinsi2_ps": 0, "propinsi2_salin": 0}
        updates = []
        for r in rows:
            sk = satuan_kerja(r["UNIT KERJA"] or "", r["JABATAN LENGKAP"] or "")
            is_ps = (r["UNIT KERJA"] or "").strip().upper() == SEKRETARIAT_PS.upper()
            if is_ps:
                if sk.upper() != SEKRETARIAT_PS.upper():
                    stats["satuan_ps"] += 1
                else:
                    stats["satuan_fallback"] += 1
            pm = potensi_menjabat(r["JENIS JABATAN"] or "", r["JABATAN LENGKAP"] or "",
                            r["JABATAN RANGKAP"] or "")
            stats["menjabat_" + (pm or "kosong")] += 1
            tp = teknik_ps(r["RIWAYAT PENDIDIKAN"] or "")
            jj2 = jenis_jabatan2(r["JENIS JABATAN"] or "", r["JABATAN RANGKAP"] or "")

            nip = norm_nip(r["NIP"] or "")
            nomor = {t: "; ".join(sert[t].get(nip, [])) for t in sert}
            punya = {t: bool(nomor[t]) for t in sert}

            # PROPINSI2: baris sekretariat PS diisi nama wilayah (upper-case)
            # dari JABATAN LENGKAP; baris lain salin PROPINSI dari sumber.
            if is_ps:
                p2 = wilayah_ps(r["JABATAN LENGKAP"] or "")
                stats["propinsi2_ps"] += 1
            else:
                p2 = r["PROPINSI"] or ""
                stats["propinsi2_salin"] += 1

            updates.append((
                sk, pm,
                nomor["PNT"], nomor["SNT"], nomor["BNT"],
                nomor["PBJ"], nomor["PPK"],
                "ya" if punya["PNT"] and (punya["PBJ"] or punya["PPK"]) else "tidak",
                "ya" if punya["BNT"] else "tidak",
                "ya" if punya["SNT"] else "tidak",
                p2,
                tp,
                jj2,
                r["id"],
            ))

        con.executemany(
            'UPDATE pegawai SET "UNIT KERJA / SATUAN KERJA"=?,'
            ' "POTENSI MENJABAT"=?,'
            ' "SERTIFIKAT PNT"=?, "SERTIFIKAT SNT"=?, "SERTIFIKAT BNT"=?,'
            ' "SERTIFIKAT PBJ"=?, "SERTIFIKAT PPK"=?, "POTENSI PPK"=?,'
            ' "POTENSI BENDAHARA"=?, "POTENSI PPSPM"=?, "PROPINSI2"=?,'
            ' "TEKNIK PS"=?, "JENIS JABATAN2"=? WHERE id=?',
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
    for i, name in ((7, "POTENSI PPK"), (8, "POTENSI BENDAHARA"),
                    (9, "POTENSI PPSPM"), (11, "TEKNIK PS")):
        print(f"{name:<16}: {sum(1 for u in updates if u[i] == 'ya')} ya")
    print(f"propinsi2: {stats['propinsi2_ps']} PS wilayah,"
          f" {stats['propinsi2_salin']} salin PROPINSI,"
          f" sisanya kosong")
    print(f"JENIS JABATAN2 : "
          f"{sum(1 for u in updates if u[12] == 'JABATAN PERBENDAHARAAN')}"
          f" JABATAN PERBENDAHARAAN")


if __name__ == "__main__":
    main()
