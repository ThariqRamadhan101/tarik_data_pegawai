# tarik_data_pegawai

Alat lokal untuk mengubah ekspor xlsx `laporan-pegawai` (EHRM) menjadi SQLite, lalu mencari, memfilter, memilih, dan mengekspor kembali data pegawai lewat webapp.

Alur singkat:

```
xlsx EHRM  ->  extract  ->  SQLite (database/pegawai.db)  ->  enrich  ->  server.py + webapp  ->  export xlsx
```

## Prasyarat

- Python 3 dengan `pandas` + `openpyxl` (Python sistem; **tidak ada** `requirements.txt` dan `.venv/` di repo bukan lingkungan proyek ini)
- Node.js + npm (webapp: React + Vite + TypeScript + Tailwind)

Di Windows PowerShell gunakan `python` dan `npm.cmd` (ExecutionPolicy memblokir `npm.ps1`). Di Linux gunakan `python3` dan `npm`.

## Data sumber (tidak ada di repo)

File sumber berisi **PII** dan di-gitignore, jadi tidak ikut ter-commit:

- `database/pegawai/laporan-pegawai-*.xlsx` — ekspor EHRM historis. Bila ada beberapa file, extract memakai yang **mtime-nya paling baru**.
- `database/unggahan/laporan-pegawai-*.xlsx` — sumber hasil upload dari webapp (dibuat otomatis; ikut dipertimbangkan extract).
- `database/sertifikat/` — file sertifikat untuk kolom turunan:
  - `rev4_...` (sheet `AKTIF`, header baris 4)
  - `SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx` (sheet `PBJ` / `PPK`, header baris 3)

Tanpa file sertifikat, enrich tetap jalan dengan peringatan dan kolom sertifikat kosong. Tanpa DB, server menolak start.

Checkout segar: salin file xlsx ke folder di atas, lalu jalankan `extract` dan `enrich`.

## Menjalankan

```bash
# 1. xlsx terbaru -> database/pegawai.db (file DB dibuat ulang)
python3 scripts/extract_pegawai.py

# 2. tambah 15 kolom turunan (WAJIB diulang setiap setelah extract)
python3 scripts/enrich_pegawai.py

# 3. build frontend -> web/dist
cd web
npm install
npm run build

# 4. server API read-only + static web/dist
cd ..
python3 server/server.py            # http://127.0.0.1:8000
```

Opsi yang sering dipakai:

```bash
python3 scripts/extract_pegawai.py --xlsx path/ke/file.xlsx --db path/ke/pegawai.db
python3 scripts/enrich_pegawai.py --db path/ke/pegawai.db
python3 server/server.py --host 127.0.0.1 --port 8000 --db database/pegawai.db
```

### Mode development (hot reload)

```bash
python3 server/server.py            # terminal 1, port 8000
cd web && npm run dev               # terminal 2, Vite di 0.0.0.0:5174
```

Vite mem-proxy `/api` ke `127.0.0.1:8000`, jadi `server.py` harus menyala. Akses dari HP lewat port 5174 (proxy), bukan langsung ke 8000.

### Update database dari webapp (upload xlsx)

Buka webapp, klik **Perbarui Data**, pilih file `.xlsx` dengan sheet `laporan-pegawai`, lalu **Upload & Proses**. Server akan:

1. menjalankan `extract_pegawai.py` + `enrich_pegawai.py` ke DB sementara;
2. membackup DB lama ke `database/pegawai-bak.db`;
3. mengganti `database/pegawai.db` dengan hasil baru;
4. menyimpan file upload sebagai sumber baru di `database/unggahan/`.

Upload **mengganti seluruh isi DB** (bukan merge). Jika extract/enrich gagal, DB lama tidak berubah. Batas ukuran file 50 MB. Daftar terpilih, filter, dan pencarian di UI dikosongkan setelah upload sukses.

Alternatif lewat curl:

```bash
curl -X POST \
  -H "Content-Type: application/octet-stream" \
  --data-binary @database/pegawai/laporan-pegawai-xxxx.xlsx \
  http://127.0.0.1:8000/api/upload
```

### Verifikasi

```bash
cd web && npm run lint              # eslint
cd web && npm run build             # tsc -b && vite build
python3 scripts/smoke_test.py       # server harus menyala; cetak OK/FAIL + hitungan
```

Urutan yang dianjurkan: `extract -> enrich -> build -> lint -> smoke_test`. Tidak ada unit test; verifikasi backend hanya `smoke_test.py`, yang memakai data nyata (DB kosong/parsial akan FAIL) dan `BASE`-nya hardcoded `127.0.0.1:8000`.

## Fitur webapp

- **Pencarian** multi-kata: spasi = AND, `;` atau baris baru = OR (bisa paste daftar NIP/nama). Hasil diurutkan: NIP eksak -> prefix NIP -> prefix nama -> sisanya. Ditampilkan 200 teratas.
- **Filter dinamis** per kolom (facet di-lazy-load); nilai dalam satu kolom = OR, antar kolom = AND.
- **Pemilih kolom**: pilihan disimpan di localStorage; urutan terpilih menentukan urutan kolom di tabel dan Excel. Panel kolom dibuka/ditutup lewat tombol **Kolom** di header (desktop) atau hamburger (mobile).
- **Update database**: tombol **Perbarui Data** untuk upload xlsx baru; server menjalankan extract + enrich, membuat backup, lalu mengganti DB.
- **Daftar terpilih**: tambah/hapus baris, "Tambah semua" untuk seluruh hasil pencarian, sort hanya di tabel terpilih.
- **Export xlsx** sesuai urutan baris di daftar terpilih.
- Layout responsif: dashboard tetap di `lg+`, di layar kecil panel filter dan kolom bisa ditampilkan/disembunyikan.

## Struktur repo

```
scripts/
  extract_pegawai.py   # xlsx -> SQLite (tabel pegawai, kolom TEXT, id + finder_text)
  enrich_pegawai.py    # dedup NIP + 15 kolom turunan (idempotent)
  smoke_test.py        # uji end-to-end terhadap server yang menyala
  create_empty_db.py   # legacy, JANGAN dipakai (skema tidak kompatibel)
server/
  server.py            # JSON API read-only + static web/dist + export xlsx
web/                   # React + Vite + TypeScript + Tailwind
  src/App.tsx          # state utama, kolom terpilih, export
  src/components/      # SearchPanel, FilterBar, ColumnPicker, SelectionTable, DatabaseUpload
  src/lib/api.ts       # client API
database/              # PII (gitignored): xlsx sumber, sertifikat, pegawai.db
  pegawai/             # ekspor EHRM historis
  unggahan/            # sumber hasil upload webapp
  pegawai.db           # SQLite aktif
  pegawai-bak.db       # backup DB sebelum upload terakhir
```

## API

Server membuka DB read-only (`?mode=ro`) untuk request biasa. `POST /api/upload` adalah operasi khusus yang mengganti DB setelah extract + enrich; export menulis file Excel.

| Endpoint | Keterangan |
| --- | --- |
| `GET /api/meta` | sumber file & waktu generate DB |
| `GET /api/columns` | daftar kolom dari `PRAGMA table_info` (tanpa `id`/`finder_text`) |
| `GET /api/facets?column=X` | nilai unik untuk filter; param berulang = subset, tanpa param = semua kolom |
| `GET /api/search?q=&limit=&<kolom>=` | total cocok (`count`) + baris terbatas; `MAX_LIMIT` 200 |
| `GET /api/ids?...` | SEMUA id yang cocok (untuk "Tambah semua"); `MAX_ALL_IDS` 40.000 |
| `GET /api/rows?ids=&fields=` | baris terpilih, urutan `ids` dipertahankan |
| `POST /api/export {ids, fields}` | unduh xlsx; urutan `ids` = urutan baris |
| `POST /api/upload` | body xlsx mentah; extract + enrich lalu ganti DB (maks 50 MB) |

Nama parameter query yang bukan parameter sistem dianggap nama kolom, mis. `?UNIT+ORGANISASI=A&UNIT+ORGANISASI=B`. Nilai filter = exact match case-insensitive.

## Catatan penting

- **PII**: xlsx sumber dan `database/pegawai.db` berisi NIK/NPWP/telepon/alamat/email. Jangan commit, jangan paste isi baris ke prompt/log/issue. Saat melaporkan masalah, cukup sebutkan hitungan/kolom, bukan isi data.
- `extract_pegawai.py` **membuat ulang** file DB, sehingga kolom hasil enrich hilang; selalu jalankan `enrich` setelahnya.
- Upload dari webapp juga **mengganti seluruh DB** (snapshot baru), tetapi DB lama dibackup ke `database/pegawai-bak.db` dan file sumber lama tetap ada. `database/pegawai/` bersifat read-only; sumber upload baru disimpan di `database/unggahan/`.
- Semua nilai disimpan sebagai TEXT. NIP dan tanggal (`dd-mm-yyyy`) adalah string — jangan di-parse sebagai angka/tanggal.
- Kunci baris adalah `id`, **bukan NIP** (NIP bisa duplikat; enrich melakukan dedup NIP).
- Jangan `git add -A`: `__pycache__`/`.pyc` tidak di-ignore, sedangkan folder data dan `web/dist` memang di-ignore.
- Vite memakai `strictPort: true` di port 5174: jika port terpakai, dev server gagal (tidak pindah port). Cek dengan `ss -ltnp | grep :5174` (Linux) atau `Get-NetTCPConnection -LocalPort 5174 -State Listen` (Windows).
- Jangan edit/re-zip `.xlsx` secara manual; gunakan openpyxl/pandas. Ekspor EHRM baru cukup ditambahkan sebagai file baru di `database/pegawai/`.
- Tanpa `web/dist`, `server.py` mengembalikan 503 untuk `/`; jalankan `npm run build` atau gunakan Vite dev.
