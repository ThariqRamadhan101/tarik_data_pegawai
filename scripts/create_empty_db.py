import sqlite3
import os

db_path = "/home/athar/repositories/tarik_data_pegawai/database/pegawai.db"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Create pegawai table (based on extract_pegawai.py schema)
cur.execute("""
CREATE TABLE IF NOT EXISTS pegawai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nip TEXT UNIQUE,
    nama TEXT,
    gelar_depan TEXT,
    gelar_belakang TEXT,
    jenis_kelamin TEXT,
    tempat_lahir TEXT,
    tanggal_lahir TEXT,
    agama TEXT,
    status_kawin TEXT,
    nama_pasangan TEXT,
    nip_pasangan TEXT,
    pekerjaan_pasangan TEXT,
    alamat TEXT,
    rt_rw TEXT,
    kelurahan TEXT,
    kecamatan TEXT,
    kota TEXT,
    provinsi TEXT,
    kode_pos TEXT,
    no_hp TEXT,
    email TEXT,
    nama_ibu_kandung TEXT,
    npwp TEXT,
    foto TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

# Create riwayat_jabatan table
cur.execute("""
CREATE TABLE IF NOT EXISTS riwayat_jabatan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pegawai_id INTEGER,
    nip TEXT,
    nama_jabatan TEXT,
    eselon TEXT,
    unit_kerja TEXT,
    tmt_jabatan TEXT,
    tmt_eselon TEXT,
    nomor_sk TEXT,
    tgl_sk TEXT,
    pejabat_sk TEXT,
    FOREIGN KEY (pegawai_id) REFERENCES pegawai(id)
)
""")

# Create riwayat_pendidikan table
cur.execute("""
CREATE TABLE IF NOT EXISTS riwayat_pendidikan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pegawai_id INTEGER,
    nip TEXT,
    jenjang TEXT,
    jurusan TEXT,
    nama_sekolah TEXT,
    tgl_lulus TEXT,
    nomor_ijazah TEXT,
    FOREIGN KEY (pegawai_id) REFERENCES pegawai(id)
)
""")

conn.commit()
conn.close()
print(f"Empty database created at {db_path}")
