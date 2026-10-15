# AGENTS.md — tarik_data_pegawai

Local tool: EHRM `laporan-pegawai` xlsx → SQLite → searchable webapp for picking employees and exporting xlsx.

## Commands (Windows PowerShell)

Use `npm.cmd`, not `npm` (ExecutionPolicy blocks the `npm.ps1` shim).

```powershell
python scripts/extract_pegawai.py       # newest database/pegawai/laporan-pegawai-*.xlsx (by mtime) -> database/pegawai.db
python scripts/enrich_pegawai.py        # 10 derived columns; MUST re-run after every re-extract
cd web; npm.cmd install; npm.cmd run build   # tsc -b && vite build -> web/dist
python server/server.py                 # http://127.0.0.1:8000 (API + serves web/dist)
npm.cmd run dev                         # in web/, Vite dev; server.py must already be running (proxies /api -> 127.0.0.1:8000)
npm.cmd run lint                        # in web/
python scripts/smoke_test.py            # server must be running; prints OK/FAIL + counts only, never row data
```

Order: `extract` → `enrich` → `build` → `lint` → `smoke_test`. No unit-test suite; build + lint + smoke test are the verification. System Python already has `pandas` + `openpyxl` (no venv); server needs stdlib + openpyxl only.

## Architecture

- `scripts/extract_pegawai.py` — sheet `laporan-pegawai` → table `pegawai`. Idempotent but **deletes/recreates the DB file**, so enrichment columns are lost. Source workbook never modified; `--xlsx`/`--db` override defaults. All values stored as **TEXT** (NIP, `TANGGAL LAHIR`/`TMT *` are `dd-mm-yyyy` strings — never parse as number/date).
- `scripts/enrich_pegawai.py` — idempotent (`ADD COLUMN` tolerant of duplicates, full `UPDATE` each run). Adds 10 TEXT columns: `UNIT KERJA / SATUAN KERJA`, `POTENSI MENJABAT`, `SERTIFIKAT PNT/SNT/BNT/PBJ/PPK` (cert number, `"; "`-joined if several, empty = none), `POTENSI PPK`, `POTENSI BENDAHARA`, `POTENSI PPSPM`. Rules:
  - `UNIT KERJA / SATUAN KERJA` = copy `UNIT KERJA`, **hanya untuk baris sekretariat PS** (`Sekretariat Direktorat Jenderal Prasarana Strategis`) diambil wilayah dari `JABATAN LENGKAP` match `Pelaksanaan Prasarana Strategis {wilayah}` (fallback: nama sekretariat). Kecocokan berupa angka romawi (I/II/III — itu nomor `PPK …`, mis. `PPK … Strategis II, … Strategis Jawa Barat`) dilewati; dipakai kecocokan wilayah berikutnya. Renames legacy `SATUAN KERJA` automatically.
  - `POTENSI MENJABAT`: struktural/lainnya → `tidak`; perbendaharaan → `ya` iff `JABATAN LENGKAP` contains `PELAKSANA/PETUGAS/PENATA TEKNIK`; fungsional/pelaksana → `tidak` iff `JABATAN RANGKAP` contains pimpinan word (direktur/sekretaris/kepala/bendahara(pejabat)), else `ya`; unknown jenis → empty.
  - `POTENSI PPK` = `ya` iff PNT **and** (PBJ or PPK) present, else `tidak`; `POTENSI BENDAHARA` = `ya` iff BNT; `POTENSI PPSPM` = `ya` iff SNT (these three are always `ya`/`tidak`, never empty).
  - Sources in `database/sertifikat/`: `rev4_Database Sertifikat Kompetensi …xlsx` sheet `AKTIF` (header row 4, keyed on `NIP` / `JENIS SERTIFIKAT KOMPETENSI` / `NOMOR SERTIFIKAT` → PNT/SNT/BNT) and `SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx` sheets `PBJ`/`PPK` (header row 3, keyed on `NIP` / `Nomor Sertifikat`). NIPs normalized (trim, strip `.0`); NIP is not unique so UPDATE hits every matching row. Records `meta.enriched_at`.
- Row key is `id`, **not NIP** (NIP duplicates exist). `id` + `finder_text` (UPPER concat of NIP/name/jabatan/unit/… for search) are hidden from `/api/columns` and the UI.
- Ad-hoc column = code-free: `ALTER TABLE pegawai ADD COLUMN <nama> TEXT` + UPDATE; `/api/columns` reads `PRAGMA table_info` so it appears in the picker automatically. Don't hand-ALTER the 10 owned columns — use the enrich script.
- `server/server.py` — read-only SQLite, stdlib `http.server`. Endpoints: `/api/meta`, `/api/columns`, `/api/facets` (11 filter groups), `/api/search`, `/api/ids` (ALL matching ids, no display limit), `/api/rows?ids=&fields=` (order preserved, validated vs `PRAGMA`), `POST /api/export {ids, fields}` (ids order = Excel row order), static `web/dist`. Limits: search `MAX_LIMIT 200`, rows/export/ids `MAX_ROWS 40_000`.
  - Search: space-separated tokens AND against `finder_text` (case-insensitive, `%`/`_` escaped); `;` splits OR-alternative segments (ranking uses first segment). Rank: exact NIP → NIP prefix → name prefix → rest. Empty `q` + no filters returns `[]` (never dumps the ~38k-row DB).
  - Filters: `unit` / `unit_kerja` / `jabatan_nilai` / `jenis_jabatan` / `status` / `golongan` / `propinsi` / `potensi_menjabat` / `potensi_ppk` / `potensi_bendahara` / `potensi_ppspm` are exact UPPER `IN` matches, **multi-value by repeating the param** (`?unit=A&unit=B` = OR within group, AND across groups by default). Legacy `jabatan` is single per-token-contains on `NAMA JABATAN`. `mode=or` is API-only; the UI always uses AND. Filter-only search (empty `q`) works.
- `web/src/App.tsx` — `DEFAULT_KOLOM`: `NAMA LENGKAP, NIP, STATUS PEGAWAI, GOLONGAN, DESKRIPSI GOLONGAN, NAMA JABATAN, UNIT ORGANISASI, UNIT KERJA / SATUAN KERJA`. `localStorage`: column picks persist (pruned if a column vanishes; old pre-enrichment picks need picker reset to get `DEFAULT_KOLOM`); selected ids keyed by `meta.generatedAt` and discarded after re-extract. Sort (`web/src/lib/sort.ts`): header click asc → desc → insertion order; `displayRows` order is what gets exported. Scale guards: results show top 200 (`DISPLAY_LIMIT` in `SearchPanel.tsx`), "tambah semua" goes via `/api/ids` + 500-id `/api/rows` chunks (`ROWS_CHUNK` in `web/src/lib/api.ts`) so whole-unit pulls work with only picked columns on the wire. Table headers have a drag handle to resize column widths (`ResizeHandle` + `useResizableColumns`; double-click resets).

Related code (don't duplicate): `../../scripts/crawl_ehrm` (EHRM crawler, token/auth notes in its `AGENTS.md`) and `../formasi` (Vite app joining formasi + pegawai; same Windows/npm and workbook rules).

## Gotchas

- **PII**: workbooks + `database/pegawai.db` contain NIK/NPWP/phone/address/email. Never commit (see `.gitignore`), never paste row contents into prompts/logs/test output — counts only.
- Stale `:8000` listener: Windows `SO_REUSEADDR` lets a second `server.py` start alongside the old one with requests randomly hitting stale code. Kill first: `Get-NetTCPConnection -LocalPort 8000 -State Listen`.
- Never hand-edit or re-zip `.xlsx` (OOXML corrupts easily); use openpyxl/pandas. New EHRM exports arrive as new `laporan-pegawai-<epoch-ms>.xlsx` files (history kept; extract only rebuilds the DB).
