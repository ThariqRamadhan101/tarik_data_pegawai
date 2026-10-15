# AGENTS.md — tarik_data_pegawai

## What this is

Local tool to pull, search, and pick employee ("pegawai") data:

1. EHRM export xlsx in `database/pegawai/` → extracted into SQLite `database/pegawai.db`
   (fast search + room for enrichment columns), then `scripts/enrich_pegawai.py`
   adds 10 derived/enriched TEXT columns from the raw certificate workbooks in
   `database/sertifikat/` + naming rules.
2. Webapp (`web/` React+Vite+TS+Tailwind + `server/server.py`) — pick which columns
   to show, search employees by multi-keyword (name/NIP/unit; several queries at
   once separated by `;` are OR-alternatives) plus multi-select filters
   (Unit Organisasi / Unit Kerja-Satuan Kerja / Jabatan / Jenis Jabatan / Status
   Pegawai / Golongan / Propinsi / Potensi Menjabat / Potensi PPK / Potensi Bendahara /
   Potensi PPSPM — always AND-combined across groups, OR within a group), build a
   selection list (sortable columns, sort order kept in the Excel download).

No git. Related code elsewhere in the workspace (don't duplicate it here):

- `../../scripts/crawl_ehrm` — Python CLI that crawls EHRM (`ehrm.pu.go.id`) into
  local SQLite; see its `AGENTS.md` for token/auth gotchas.
- `../formasi` — Vite/React app joining formasi + pegawai data; see its `AGENTS.md`
  (same Windows/npm quirks and workbook rules apply here).

## Commands (Windows / PowerShell)

Use `npm.cmd`, not `npm` — ExecutionPolicy blocks the `npm.ps1` shim.

```powershell
python scripts/extract_pegawai.py       # newest database/pegawai/*.xlsx -> database/pegawai.db (run FIRST, or after a new export drops in)
python scripts/enrich_pegawai.py        # 10 enrichment columns (sertifikat + aturan) -> wajib ulang SETIAP re-extract
cd web; npm.cmd install; npm.cmd run build   # tsc -b && vite build -> web/dist
python server/server.py                 # http://localhost:8000  (API + serves web/dist)

# development: server.py must be running, then in web/:
npm.cmd run dev                         # Vite dev server, proxies /api -> 127.0.0.1:8000
npm.cmd run lint
python scripts/smoke_test.py            # API smoke test (server must be running; prints OK/FAIL + counts only, no row data)
```

Required order to verify changes: `extract` → `enrich` → `npm.cmd run build` →
`npm.cmd run lint` → `python scripts/smoke_test.py`. **No unit-test suite** —
build + lint + smoke test are the verification.

## Architecture

- `scripts/extract_pegawai.py` — sheet `laporan-pegawai` → table `pegawai`. Re-runs
  are idempotent (table rebuilt, source name/timestamp recorded in `meta`); the source
  workbook is never modified. **But re-extract deletes and recreates the DB file** —
  enrichment columns are lost; re-run `scripts/enrich_pegawai.py` after every
  re-extract.
- `scripts/enrich_pegawai.py` — **re-runnable/idempotent** (ALTER TABLE, tolerate
  duplicate column, then full UPDATE of every row each run); **print counts only,
  never row contents (PII)**. Builds 10 TEXT columns:
  `UNIT KERJA / SATUAN KERJA` (copy `UNIT KERJA`, except sekretariat rows take the
  wilayah from
  `JABATAN LENGKAP` "Pelaksanaan Prasarana Strategis {wilayah}", fallback to the
  sekretariat name itself), `POTENSI MENJABAT` (rule by `JENIS JABATAN` +
  keywords → "ya"/"tidak"/"": struktural/lainnya selalu "tidak"; perbendaharaan
  "ya" bila `JABATAN LENGKAP` memuat kata teknik; fungsional/pelaksana "tidak"
  bila `JABATAN RANGKAP` memuat kata pimpinan
  (direktur/sekretaris/kepala/bendahara/pejabat), selain itu "ya"), `SERTIFIKAT PNT/SNT/BNT/PBJ/PPK`
  (certificate NUMBER as value, empty = doesn't have, multiple joined `"; "`), and
  derived `POTENSI PPK`/`POTENSI BENDAHARA`/`POTENSI PPSPM` ("ya" iff the matching
  cert column is filled; PPK also needs PNT). Sertifikat sources: sheet AKTIF of
  `rev4_Database Sertifikat Kompetensi …xlsx` (header row 4, NIP/jenis/nomor →
  PNT/SNT/BNT) and sheets PBJ/PPK of `SERTIFIKAT PBJ DAN PPK TA. 2026.xlsx`
  (header row 3, NIP col G / nomor col B; skip empty template rows). NIPs are
  normalized (trim, strip `.0`) on both sides; NIP is not unique in `pegawai`, so
  UPDATE matches every row with that NIP. `meta.enriched_at` is recorded. Renames
  the legacy `SATUAN KERJA` column automatically if a previous version created it.
- Every value is stored as **TEXT** — `NIP` and dates (`TANGGAL LAHIR`, `TMT *`, …)
  are `dd-mm-yyyy` strings in the source; never parse them as dates/numbers.
- Hidden system columns (not offered in the UI): `id` (row key — **not NIP**; NIP is
  not unique: 37.924 rows / 37.596 distinct NIPs) and `finder_text` (UPPER concat of
  name/NIP/jabatan/unit/… used for search).
- **Ad-hoc enrichment = add a column, no code change:** `sqlite3 database/pegawai.db
  "ALTER TABLE pegawai ADD COLUMN <nama> TEXT"`. `/api/columns` reads
  `PRAGMA table_info`, so the new column automatically appears in the UI column
  picker; fill values with any UPDATE script. The 10 standard columns are owned by
  `scripts/enrich_pegawai.py` — use that instead of hand ALTERing (and see the
  re-extract warning above).
- `server/server.py` — **stdlib only** (http.server + sqlite3; openpyxl for export —
  no pip installs). Opens the DB read-only. Endpoints: `/api/meta`, `/api/columns`,
  `/api/facets` (distinct values for the 11 filter groups: `UNIT ORGANISASI`,
  `UNIT KERJA / SATUAN KERJA`, `NAMA JABATAN`, `JENIS JABATAN`, `STATUS PEGAWAI`,
  `GOLONGAN`, `PROPINSI`, `POTENSI MENJABAT`, `POTENSI PPK`, `POTENSI BENDAHARA`,
  `POTENSI PPSPM`),
  `/api/search?q=&limit=&<filter params>&mode=` (multi-keyword AND: every
  space-separated token must appear in `finder_text`, case-insensitive — the Excel
  Finder `TEXTSPLIT`+`SEARCH` formula. **`;` separates alternative queries, OR'd
  together** (`"agus prasarana strategis; budi sumber daya air"` = segment1 OR
  segment2; ranking uses the first segment). Ranked: exact NIP → NIP prefix → name
  prefix. Response has `count` (total matches, can be thousands) + `rows`
  (top `limit`,
  MAX_LIMIT 200). `q` is ANDed with the filter group. Filter params:
  `unit`/`unit_kerja`/`jabatan_nilai`/`jenis_jabatan`/`status`/`golongan`/`propinsi`/`potensi_menjabat`/`potensi_ppk`/`potensi_bendahara`/`potensi_ppspm`
  are exact UPPER `IN` matches and **multi-value — repeat the param**
  (`?unit=A&unit=B` = OR
  inside the group; built by `URLSearchParams.append` in `web/src/lib/api.ts`;
  `unit_kerja` filters the derived `UNIT KERJA / SATUAN KERJA` column);
  legacy `jabatan` stays a single per-token-contains keyword on `NAMA JABATAN`; the
  group combines by `mode` `and` (default) or `or` — API-level only, the webapp UI
  always uses AND and never sends `mode`; filter-only search works with empty `q`),
  `/api/ids?<same params as search>` (ALL matching ids, no display limit — powers
  "Tambah semua yang cocok" for pulling a whole unit, e.g. 14k rows),
  `/api/rows?ids=&fields=`
  (fields validated against `PRAGMA table_info`, order preserved; up to MAX_ROWS
  40_000 ids per call — the web client chunks at 500 ids/request to keep URLs short),
  `POST /api/export`
  `{ids, fields}` → xlsx download (server-side, openpyxl; `ids` order = Excel row
  order; MAX_ROWS 40_000), plus static `web/dist`.
- `web/src/App.tsx` — `DEFAULT_KOLOM` shows the default columns
  (`NAMA LENGKAP`, `NIP`, `STATUS PEGAWAI`, `GOLONGAN`, `DESKRIPSI GOLONGAN`,
  `NAMA JABATAN`, `UNIT ORGANISASI`, `UNIT KERJA / SATUAN KERJA`). State in
  `localStorage`: **column picks persist across re-extracts** (pruned if a column
  vanishes — and an old saved pick predating the enrichment columns keeps the old
  pick; use the picker's reset to pick up `DEFAULT_KOLOM`); **selected row ids
  are keyed by `meta.generatedAt`** and discarded automatically after a
  re-extract (ids would point at different people). Session-only state (reset on
  reload): filter bar (`web/src/components/FilterBar.tsx` — eleven `MultiSelect`
  dropdowns: checkbox list + search box for long lists like the 664 jabatan values)
  and column sorting of the selection list
  (`web/src/lib/sort.ts` — click header asc → desc → insertion order;
  `displayRows` order is what `/api/export` receives, so the Excel matches the
  on-screen order). Note: the served port is Windows `SO_REUSEADDR`-friendly —
  if a stale `server.py` is already listening on :8000, a second instance starts
  anyway and requests randomly hit the old code; kill stale processes first
  (`Get-NetTCPConnection -LocalPort 8000 -State Listen`).
- The full 37.924-row dataset (~54 MB DB) never reaches the browser: search results
  show the top 200 (`DISPLAY_LIMIT` in `web/src/components/SearchPanel.tsx`; the
  button shows the full `count`); "Tambah semua yang cocok" fetches **all** matching
  ids via `/api/ids` — selection rows are then loaded in 500-id chunks (`ROWS_CHUNK`
  in `web/src/lib/api.ts`), so pulling a whole 14k-row unit works and only the picked
  columns cross the wire.

## Gotchas

- **PII.** The source workbooks **and `database/pegawai.db`** contain NIK/KTP, NPWP,
  phone, address, email of real people. Treat both as confidential: never commit them
  (`.gitignore` lists the PII files under `database/`), never paste row contents into
  prompts, logs, or test output (print counts/status only — `scripts/smoke_test.py`
  follows this).
- System Python already has `pandas` + `openpyxl` (no venv needed on this machine).
  The server needs nothing beyond stdlib + openpyxl.
- Don't hand-edit or re-zip the `.xlsx` (OOXML zip; corrupts easily — see
  `../formasi/AGENTS.md` "Workbook gotchas"). Use openpyxl/pandas instead.
- No script in the workspace **writes** `laporan-pegawai-<epoch-ms>.xlsx` — a new file
  in `database/pegawai/` comes from a manual EHRM export; just drop it there and
  re-extract (commands above pick the newest by mtime).
- New exports arrive as new epoch-named files; old ones stay as history — extract
  never deletes or overwrites anything in `database/pegawai/` (it only rebuilds the
  DB passed via `--db`).
