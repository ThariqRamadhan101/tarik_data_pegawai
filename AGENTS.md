# AGENTS.md — tarik_data_pegawai

Alat lokal: xlsx `laporan-pegawai` (EHRM) -> SQLite -> webapp cari/pilih pegawai -> export xlsx. App terkait: `../formasi` (lihat `AGENTS.md`-nya).

## Perintah

Windows PowerShell: `python` + `npm.cmd` (ExecutionPolicy memblokir `npm.ps1`). Di Linux/workspace ini: `python3` + `npm`; `python` tidak ada dan `.venv/` **tidak** berisi pandas — jangan diaktifkan. Python sistem sudah punya `pandas` + `openpyxl`.

```powershell
python scripts/extract_pegawai.py           # xlsx terbaru (mtime) di database/pegawai/ -> database/pegawai.db
python scripts/enrich_pegawai.py            # 13 kolom turunan; WAJIB diulang setelah extract
cd web; npm.cmd install; npm.cmd run build  # tsc -b && vite build -> web/dist
python server/server.py                     # 127.0.0.1:8000 (API read-only + static web/dist)
npm.cmd run dev                             # di web/; Vite 0.0.0.0:5174, proxy /api -> 127.0.0.1:8000 (server.py harus nyala)
npm.cmd run lint                            # di web/ (eslint)
python scripts/smoke_test.py                # server harus nyala; OK/FAIL + hitungan, tanpa isi baris
```

Urutan verifikasi: `extract -> enrich -> build -> lint -> smoke_test`; tidak ada unit test. `tsc -b` memakai `strict` + `verbatimModuleSyntax` (pakai `import type`) dan `noUnusedLocals/Parameters` — build gagal bila dilanggar. `smoke_test.py` bergantung pada data nyata (mis. Bina Marga ~14k baris, 250+ unit kerja), jadi DB kosong/parsial akan FAIL.

Workbook **tidak ada di repo** (gitignore, PII). Checkout segar: salin `laporan-pegawai-*.xlsx` ke `database/pegawai/` dan file sertifikat ke `database/sertifikat/`, lalu `extract -> enrich`; tanpa DB, server menolak start.

## Arsitektur

- `scripts/extract_pegawai.py` — sheet `laporan-pegawai` -> tabel `pegawai`; sumber dipilih dari mtime terbaru di `database/pegawai/` (`--xlsx`/`--db` override). **Menghapus/membuat ulang file DB** (kolom enrich hilang); xlsx sumber tidak diubah. Semua nilai TEXT: NIP dan `TANGGAL LAHIR`/`TMT *` adalah string `dd-mm-yyyy` — jangan parse sebagai angka/tanggal. `id` = kunci baris; `finder_text` = gabungan uppercase dari `FINDER_FIELDS` (bukan semua kolom) untuk pencarian.
- `scripts/enrich_pegawai.py` — idempotent (`ADD COLUMN` toleran duplikat, `UPDATE` penuh tiap run). Menambah 13 kolom TEXT: `UNIT KERJA / SATUAN KERJA`, `POTENSI MENJABAT`, `SERTIFIKAT PNT/SNT/BNT/PBJ/PPK` (nomor, `"; "`; kosong = tidak punya), `POTENSI PPK/BENDAHARA/PPSPM`, `PROPINSI2`, `TEKNIK PS`, `JENIS JABATAN2`.
  - `UNIT KERJA / SATUAN KERJA` & `PROPINSI2` hanya memecah baris `Sekretariat Direktorat Jenderal Prasarana Strategis` per wilayah dari pola `Pelaksanaan Prasarana Strategis <wilayah>` di `JABATAN LENGKAP`; romawi I/II/III (nomor PPK) dilewati. `UNIT KERJA / SATUAN KERJA` fallback ke nama sekretariat; `PROPINSI2` kosong bila tidak ada match. Baris lain: salin `UNIT KERJA` / `PROPINSI`.
  - `POTENSI PPK` = `ya` iff PNT **dan** (PBJ atau PPK); `POTENSI BENDAHARA` = BNT; `POTENSI PPSPM` = SNT (ketiganya selalu `ya`/`tidak`). `POTENSI MENJABAT`: struktural/lainnya `tidak`; perbendaharaan `ya` iff `JABATAN LENGKAP` memuat PELAKSANA/PETUGAS/PENATA TEKNIK; fungsional/pelaksana `tidak` iff `JABATAN RANGKAP` memuat kata pimpinan (DIREKTUR/SEKRETARIS/KEPALA/BENDAHARA/PEJABAT), else `ya`; jenis tak dikenal kosong.
  - `TEKNIK PS` = `ya` iff `RIWAYAT PENDIDIKAN` (uppercase; spasi/tanda baca dinormalisasi) memuat salah satu istilah Indonesia/Inggris di `KATA_TEKNIK_PS` (Arsitektur/Architecture, Sipil/Civil, ...), else `tidak`.
  - `JENIS JABATAN2` = salinan `JENIS JABATAN`; diganti `JABATAN PERBENDAHARAAN` bila `JABATAN RANGKAP` memuat `KEPALA`/`BENDAHARA`/`PEJABAT` (case-insensitive substring; `BENDAHARAWAN` ikut cocok).
  - NIP dinormalisasi (trim, buang `.0`); NIP tidak unik -> `UPDATE` mengenai semua baris cocok. Nama file sertifikat hardcoded di `database/sertifikat/` (`rev4_...` sheet `AKTIF` header baris 4; `SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx` sheet `PBJ`/`PPK` header baris 3); jika tidak ada -> peringatan + kolom sertifikat kosong. `meta.enriched_at` dicatat; migrasi legacy `SATUAN KERJA` otomatis (rename, atau drop jika kolom baru sudah ada).
- `server/server.py` — SQLite read-only (`?mode=ro`), stdlib `http.server`; `openpyxl` hanya untuk export. Endpoint: `/api/meta`, `/api/columns`, `/api/facets` (`?column=X` berulang = subset/lazy; tanpa param = semua kolom), `/api/search` (`count` total + `rows` terbatas), `/api/ids` (SEMUA id cocok), `/api/rows?ids=&fields=` (urutan ids dipertahankan), `POST /api/export {ids, fields}` (urutan ids = urutan baris Excel), static `web/dist`. Limit: search `MAX_LIMIT 200`; rows/export/ids `MAX_ROWS`/`MAX_ALL_IDS 40_000`.
- Pencarian `q`: token spasi AND pada `finder_text` (case-insensitive, `%`/`_` di-escape); `;` memecah segmen OR (ranking pakai segmen pertama). Urutan: NIP eksak -> prefix NIP -> prefix nama -> sisanya. `q` kosong tanpa filter -> `[]` (tidak membuang ~38k baris); filter-only tetap jalan. `mode=or` hanya meng-OR-kan grup filter (q tetap AND dengan filter); UI selalu AND.
- Filter: exact match case-insensitive; nilai param berulang = OR dalam kolom, AND antar kolom. Nama param yang bukan sistem dianggap nama kolom, jadi kolom ad-hoc langsung bisa difilter: `?UNIT+ORGANISASI=A&UNIT+ORGANISASI=B` (alias lama `unit`, `unit_kerja`, `jabatan_nilai`, `status`, ... ada di `filter_cond`; `jabatan` = substring per kata).
- Kunci baris `id`, **bukan NIP** (NIP duplikat). `id` + `finder_text` disembunyikan dari `/api/columns` dan UI.
- Kolom ad-hoc tanpa kode: `ALTER TABLE pegawai ADD COLUMN <nama> TEXT` + `UPDATE`; `/api/columns` membaca `PRAGMA table_info`, jadi otomatis muncul di picker. Jangan hand-ALTER 13 kolom milik enrich — pakai skrip enrich.

## Webapp (`web/`)

- `DEFAULT_KOLOM` (`App.tsx`): `NAMA LENGKAP, NIP, STATUS PEGAWAI, GOLONGAN, DESKRIPSI GOLONGAN, NAMA JABATAN, UNIT ORGANISASI, UNIT KERJA / SATUAN KERJA, PROPINSI`; pertama kali dibuka semua dicentang. Urutan `picked` = urutan kolom di tabel & Excel. Pilihan disimpan di localStorage dan dipangkas jika kolom hilang; id terpilih terikat `meta.generatedAt` dan dibuang setelah re-extract.
- `FilterBar.tsx` dinamis: 11 kolom standar terpasang default; user bisa menambah kolom lewat "Tambah filter kolom" dan melepas via ×. Opsi facet di-lazy-load per kolom (~47 KB untuk 11 default vs ~16 MB semua kolom). Tidak ada filter per kolom di header tabel (sengaja).
- Pencarian UI: debounce 300 ms; tampil 200 teratas (`DISPLAY_LIMIT`), "Tambah semua" memakai `/api/ids` lalu `/api/rows` per 500 id (`ROWS_CHUNK`). Sort header **hanya di Daftar Terpilih** (asc -> desc -> urutan tambah); urutan `displayRows` yang diexport.
- Layout: `lg+` dashboard fixed (`h-dvh`, panel scroll internal); `<lg` scroll halaman + panel filter Tampilkan/Sembunyikan + picker kolom lewat hamburger. `server.py` bind `127.0.0.1`; akses HP lewat Vite 5174 (proxy), bukan langsung ke 8000.
- Resize kolom tidak aktif: `ResizableColumns.tsx`/`useResizableColumns.ts` masih ada tetapi tidak diimpor di UI saat ini.

## Gotchas

- **PII**: workbook + `database/pegawai.db` berisi NIK/NPWP/telepon/alamat/email. Jangan commit, jangan paste isi baris ke prompt/log/uji — hitungan saja. Log server masih memuat request line/query. `__pycache__` **tidak** di-ignore — jangan `git add -A`.
- Jangan pakai `scripts/create_empty_db.py` (untracked): skemanya lowercase + `NIP UNIQUE` dan path absolut, tidak kompatibel dengan `extract_pegawai.py`; skema resmi hanya dari extract.
- Stale `:8000` (Windows `SO_REUSEADDR`): dua `server.py` bisa hidup bersama dan request acak ke kode lama. Cek/matikan dulu: `Get-NetTCPConnection -LocalPort 8000 -State Listen`.
- Vite `host 0.0.0.0`, `port 5174`, `strictPort: true`: `npm run dev` **gagal** bila port terpakai, bukan pindah. Linux: `ss -ltnp | grep :5174`; Windows: `Get-NetTCPConnection -LocalPort 5174 -State Listen`.
- Jangan edit/re-zip `.xlsx` manual (OOXML rusak); pakai openpyxl/pandas. Ekspor EHRM baru = file baru `laporan-pegawai-<epoch-ms>.xlsx` (riwayat disimpan; extract hanya rebuild DB).
- `web/dist` tidak ada di checkout segar; `server.py` hanya menyajikan `web/dist`, jadi build dulu atau jalankan Vite dev. Tanpa dist, `/` -> 503 dengan hint.
