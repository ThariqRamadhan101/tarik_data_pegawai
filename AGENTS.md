# AGENTS.md — tarik_data_pegawai

Alat lokal: xlsx `laporan-pegawai` (EHRM) -> SQLite -> webapp cari/pilih -> export xlsx. App terkait: `../formasi` (lihat `AGENTS.md`-nya).

## Perintah

Windows PowerShell: `python` + `npm.cmd` (ExecutionPolicy memblokir `npm.ps1`). Linux: `python3` + `npm`; `python` tidak ada dan `.venv/` **tidak** berisi pandas — jangan diaktifkan. Pakai Python sistem (`pandas` + `openpyxl`); tidak ada `requirements.txt`.

```bash
python3 scripts/extract_pegawai.py   # xlsx mtime terbaru -> database/pegawai.db (DB dibuat ulang)
python3 scripts/enrich_pegawai.py    # WAJIB setelah extract; dedup NIP + 15 kolom turunan
cd web && npm install && npm run build   # tsc -b && vite build -> web/dist
cd web && npm run lint                   # eslint
python3 server/server.py             # 127.0.0.1:8000; API read-only + static web/dist
python3 scripts/smoke_test.py        # server harus hidup; BASE hardcoded :8000
```

Urutan verifikasi: `extract -> enrich -> build -> lint -> smoke_test`; tidak ada unit test/lint Python. `smoke_test.py` butuh data nyata (DB kosong/parsial FAIL; mis. Bina Marga >200 id, 250+ unit kerja) dan tidak mengikuti `server.py --port`. `tsc -b` strict + `verbatimModuleSyntax` (`import type`) + `noUnused*` — build gagal bila dilanggar. Dev: `python3 server/server.py` + `cd web && npm run dev` (Vite 0.0.0.0:5174, proxy `/api` -> 8000, `strictPort`).

Workbook **tidak ada di repo** (gitignore, PII). Checkout segar: salin `laporan-pegawai-*.xlsx` ke `database/pegawai/` dan sertifikat ke `database/sertifikat/`, lalu `extract -> enrich`; tanpa DB server menolak start. Override: `--xlsx/--db` (extract), `--db` (enrich/server), `--host/--port` (server).

## Data & DB

- `extract_pegawai.py` — sheet `laporan-pegawai` -> tabel `pegawai`; sumber = `laporan-pegawai-*.xlsx` dengan mtime terbaru di `database/pegawai/` **atau** `database/unggahan/`. **Menghapus/membuat ulang file DB**; xlsx sumber tidak diubah. Semua nilai TEXT: NIP dan `TANGGAL LAHIR`/`TMT *` string `dd-mm-yyyy` — jangan parse angka/tanggal. `id` = kunci baris; `finder_text` = uppercase gabungan `FINDER_FIELDS` saja.
- `enrich_pegawai.py` — idempotent (`ADD COLUMN` toleran duplikat, `UPDATE` penuh). Dedup NIP (pertahankan `id` terkecil; NIP kosong tak disentuh; update `meta.rows`), lalu 15 kolom TEXT. Aturan lengkap ada di docstring; yang mudah salah:
  - `UNIT KERJA / SATUAN KERJA` & `PROPINSI2` hanya memecah baris Sekretariat DJPS per wilayah dari `Pelaksanaan Prasarana Strategis <wilayah>` di `JABATAN LENGKAP`; romawi I/II/III (nomor PPK) dilewati. Satuan fallback ke nama sekretariat; `PROPINSI2` kosong bila tak match. Baris lain salin `UNIT KERJA`/`PROPINSI`.
  - `URUTAN UNIT ORGANISASI` 1-10; `URUTAN UNKER / SATKER PS` 1-40 — tuple berisi 40 entri, walau docstring/print skrip masih menulis "1-39". Hanya untuk `UNIT ORGANISASI` = DJ Prasarana Strategis (nama "Direktorat Kepatuhan Intern" juga dipakai ditjen lain).
  - `POTENSI PPK` = PNT dan (PBJ/PPK); `POTENSI BENDAHARA` = BNT; `POTENSI PPSPM` = SNT. `POTENSI MENJABAT`: struktural/lainnya `tidak`; perbendaharaan `ya` iff `JABATAN LENGKAP` memuat PELAKSANA/PETUGAS/PENATA TEKNIK; fungsional/pelaksana `tidak` iff `JABATAN RANGKAP` memuat DIREKTUR/SEKRETARIS/KEPALA/BENDAHARA/BENDAHARAWAN/PEJABAT; jenis tak dikenal kosong.
  - `TEKNIK PS` dari `RIWAYAT PENDIDIKAN` (normalisasi spasi/tanda baca) vs `KATA_TEKNIK_PS`, else `tidak`; `JENIS JABATAN2` = salinan `JENIS JABATAN`, diganti `JABATAN PERBENDAHARAAN` bila `JABATAN RANGKAP` memuat KEPALA/BENDAHARA/PEJABAT (BENDAHARAWAN ikut cocok).
  - Sertifikat: nama file hardcoded di `database/sertifikat/` (`rev4_...` sheet `AKTIF` header baris 4; `SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx` sheet `PBJ`/`PPK` header baris 3). Tidak ada file -> peringatan + kolom kosong. NIP dinormalisasi (trim, buang `.0`) untuk pencocokan.
- Jangan hand-ALTER 15 kolom enrich — pakai skrip. Kolom ad-hoc lain: `ALTER TABLE pegawai ADD COLUMN <nama> TEXT` + `UPDATE`; `/api/columns` membaca `PRAGMA table_info`, jadi otomatis muncul di picker.

## Server/API

- `server/server.py` — SQLite read-only (`?mode=ro`) untuk request biasa, stdlib `http.server`; `openpyxl` hanya untuk export. Endpoint & tabel API ada di `README.md`. Limit: `/api/search` `MAX_LIMIT 200`; rows/export/ids 40_000; upload 50 MB.
- `POST /api/upload` menerima body xlsx **mentah** (`application/octet-stream`), bukan multipart. Alur: simpan sementara -> `extract_pegawai.py --xlsx <temp> --db <temp.db>` -> pindahkan sumber ke `database/unggahan/laporan-pegawai-<epoch-ms>.xlsx` -> `enrich_pegawai.py --db <temp.db>` -> backup DB lama ke `pegawai-bak.db` -> `os.replace` ke DB aktif. DB lama hanya tersentuh setelah extract+enrich sukses; jika gagal, file/DB sementara dibersihkan. Sumber upload & backup mengikuti lokasi `--db` (`<dir-db>/unggahan`, `<db>-bak.db`).
- `database/pegawai/` **read-only** di checkout ini; jangan mengandalkannya untuk upload. Sumber upload masuk `database/unggahan/` (gitignored). `extract` membaca kedua folder.
- `q`: spasi = AND pada `finder_text` (`%`/`_` di-escape); `;` = OR antar segmen (ranking pakai segmen pertama). `q` kosong tanpa filter -> `[]`; filter-only tetap jalan. `mode=or` hanya meng-OR grup filter (q tetap AND); UI selalu AND.
- Filter exact case-insensitive; param berulang = OR dalam kolom, AND antar kolom. Param non-sistem = nama kolom, jadi `?UNIT+ORGANISASI=A&UNIT+ORGANISASI=B` langsung bisa. Alias lama (`unit`, `unit_kerja`, `jabatan_nilai`, `status`, ...) ada di `filter_cond`; `jabatan` = substring per kata.
- Urutan `ids` dipertahankan `/api/rows` dan export (urutan ids = urutan baris Excel). `id` + `finder_text` tidak muncul di `/api/columns`/UI.

## Webapp (`web/`)

- `DEFAULT_KOLOM` (`App.tsx`): 9 kolom; pertama buka semua dicentang. Urutan `picked` = urutan kolom tabel & Excel; disimpan localStorage dan dipangkas bila kolom hilang. Id terpilih terikat `meta.generatedAt` dan dibuang setelah re-extract/upload.
- Panel kolom bisa ditutup/dibuka lewat tombol **Kolom** di header (desktop, state `pegawai-finder-kolom-open`); tidak ada tombol × di panel. Mobile tetap lewat hamburger. `FilterBar.tsx`: 11 kolom filter default, panel mulai tertutup (toggle Tampilkan/Sembunyikan + badge "N filter aktif"); 11 facet default dimuat saat mount, kolom tambahan lazy. Tidak ada filter per kolom di header tabel (sengaja).
- Pencarian UI: `;`/baris baru = OR, spasi = AND; debounce 300 ms; tampil 200 teratas (`DISPLAY_LIMIT`), "Tambah semua" pakai `/api/ids` lalu `/api/rows` per 500 id (`ROWS_CHUNK`). Sort header **hanya di Daftar Terpilih** (asc -> desc -> urutan tambah); urutan `displayRows` yang diexport. Kolom **Aksi** selalu paling kiri.
- Upload DB: tombol **Perbarui Data** -> `DatabaseUpload.tsx` (file `.xlsx`, maks 50 MB) -> `uploadDatabase()` di `lib/api.ts`. Setelah sukses App memuat ulang meta/kolom, mengosongkan ids/rows/sort/filters, dan me-remount `FilterBar` + `SearchPanel` lewat key unik `filter-<generatedAt>` / `search-<generatedAt>`. Jangan memberi key yang sama pada dua sibling (React bisa menggandakan panel); ini pernah membuat 4 panel Filter muncul.
- Layout: `lg+` dashboard fixed (`h-dvh`, panel scroll internal); `<lg` scroll halaman + picker kolom lewat hamburger. `useResizableColumns.ts` masih ada tapi tidak diimpor (resize nonaktif). `server.py` bind `127.0.0.1`; akses HP lewat Vite 5174 (proxy), bukan langsung 8000.

## Gotchas

- **PII**: workbook + DB berisi NIK/NPWP/telepon/alamat/email. Jangan commit/paste isi baris ke prompt/log/uji — hitungan saja. Log server memuat request line termasuk query.
- Jangan `git add -A`: `__pycache__` tidak di-ignore dan `.pyc` sudah ter-track.
- Jangan pakai `scripts/create_empty_db.py` (path absolut, skema lowercase + `NIP UNIQUE`, tabel riwayat tak dipakai): tidak kompatibel; skema resmi hanya dari extract.
- Stale `:8000` (Windows `SO_REUSEADDR`): dua `server.py` bisa hidup bersama dan request acak ke kode lama. Cek `Get-NetTCPConnection -LocalPort 8000 -State Listen` dulu. Vite `strictPort`: Linux `ss -ltnp | grep :5174`, Windows `Get-NetTCPConnection -LocalPort 5174 -State Listen`.
- Jangan edit/re-zip `.xlsx` manual (OOXML rusak); pakai openpyxl/pandas. Ekspor EHRM baru = file baru `laporan-pegawai-<epoch-ms>.xlsx` di `database/pegawai/` atau upload lewat webapp.
- `web/dist` gitignored/absen di checkout segar; `server.py` hanya menyajikan `web/dist`, jadi build dulu atau jalankan Vite dev. Tanpa dist, `/` -> 503 dengan hint.
- Upload = **replace penuh** (snapshot baru), bukan merge. DB lama ada di `database/pegawai-bak.db` (tertimpa tiap upload); riwayat sumber ada di `database/pegawai/` + `database/unggahan/`.
