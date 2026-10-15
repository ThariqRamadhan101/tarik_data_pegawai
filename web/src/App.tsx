import { useEffect, useMemo, useState } from 'react'
import ColumnPicker from './components/ColumnPicker'
import FilterBar from './components/FilterBar'
import SearchPanel from './components/SearchPanel'
import SelectionTable from './components/SelectionTable'
import {
  downloadSelection,
  EMPTY_FILTERS,
  errorText,
  getColumns,
  getFacets,
  getMeta,
  getRows,
  type Facets,
  type Filters,
  type Meta,
  type Row,
} from './lib/api'
import { sortRows, type SortState } from './lib/sort'

const LS_KOLOM = 'pegawai-finder-kolom'
const LS_IDS = 'pegawai-finder-terpilih'
const LS_DB = 'pegawai-finder-db'

const DEFAULT_KOLOM = [
  'NAMA LENGKAP',
  'NIP',
  'STATUS PEGAWAI',
  'GOLONGAN',
  'DESKRIPSI GOLONGAN',
  'NAMA JABATAN',
  'UNIT ORGANISASI',
  'UNIT KERJA / SATUAN KERJA',
]

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? null : (JSON.parse(raw) as T)
  } catch {
    return null
  }
}

export default function App() {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [facets, setFacets] = useState<Facets>({
    unitOrganisasi: [],
    unitKerja: [],
    namaJabatan: [],
    jenisJabatan: [],
    statusPegawai: [],
    golongan: [],
    propinsi: [],
    potensiMenjabat: [],
    potensiPpk: [],
    potensiBendahara: [],
    potensiPpspm: [],
  })
  const [picked, setPicked] = useState<string[]>([])
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [ids, setIds] = useState<number[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [sort, setSort] = useState<SortState | null>(null)
  const [rowsLoading, setRowsLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Muat metadata + daftar kolom sekali di awal; rekonsiliasi localStorage.
  useEffect(() => {
    let cancel = false
    Promise.all([getMeta(), getColumns(), getFacets()])
      .then(([m, cols, fac]) => {
        if (cancel) return
        setMeta(m)
        setColumns(cols)
        setFacets(fac)

        const savedCols = load<string[]>(LS_KOLOM)
        if (savedCols !== null) {
          setPicked(savedCols.filter((c) => cols.includes(c)))
        } else {
          setPicked(DEFAULT_KOLOM.filter((c) => cols.includes(c)))
        }

        // id pegawai melekat pada hasil ekstraksi tertentu: bila DB diganti,
        // buang daftar terpilih lama (id bisa menunjuk orang lain).
        if (localStorage.getItem(LS_DB) === m.generatedAt) {
          setIds((load<number[]>(LS_IDS) ?? []).filter((n) => Number.isInteger(n)))
        } else {
          localStorage.removeItem(LS_IDS)
          localStorage.removeItem(LS_DB)
        }
      })
      .catch((e) => {
        if (!cancel) setError(errorText(e))
      })
    return () => {
      cancel = true
    }
  }, [])

  // Persistensi pilihan user.
  useEffect(() => {
    localStorage.setItem(LS_KOLOM, JSON.stringify(picked))
  }, [picked])
  useEffect(() => {
    if (!meta) return
    localStorage.setItem(LS_IDS, JSON.stringify(ids))
    localStorage.setItem(LS_DB, meta.generatedAt)
  }, [ids, meta])

  // Ambil baris terpilih sesuai kolom terpilih (urutan = urutan tambah).
  useEffect(() => {
    if (!ids.length || !picked.length) {
      setRows([])
      return
    }
    let cancel = false
    setRowsLoading(true)
    getRows(ids, picked)
      .then((r) => {
        if (!cancel) setRows(r)
      })
      .catch((e) => {
        if (!cancel) setError(errorText(e))
      })
      .finally(() => {
        if (!cancel) setRowsLoading(false)
      })
    return () => {
      cancel = true
    }
  }, [ids, picked])

  const togglePicked = (col: string) =>
    setPicked((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col],
    )

  const addIds = (newIds: number[]) =>
    setIds((prev) => [...prev, ...newIds.filter((n) => !prev.includes(n))])

  // Tampilan Daftar Terpilih mengikuti sort aktif; download pun pakai urutan ini.
  const displayRows = useMemo(() => sortRows(rows, sort), [rows, sort])

  /** Klik header: asc -> desc -> kembali ke urutan tambah. */
  const headerSort = (field: string) =>
    setSort((prev) =>
      prev?.field !== field
        ? { field, dir: 'asc' }
        : prev.dir === 'asc'
          ? { field, dir: 'desc' }
          : null,
    )

  const download = async () => {
    setExporting(true)
    setError(null)
    try {
      await downloadSelection(
        displayRows.map((r) => r.id),
        picked,
      )
    } catch (e) {
      setError(errorText(e))
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 bg-slate-800 px-4 py-3 text-white">
        <h1 className="text-base font-semibold">Cari & Pilih Pegawai</h1>
        {meta && (
          <span className="text-xs text-slate-300">
            {meta.source} · {meta.rows.toLocaleString('id-ID')} baris ·{' '}
            {meta.columns} kolom · diextrak {meta.generatedAt}
          </span>
        )}
        <span className="ml-auto rounded-full bg-blue-600 px-3 py-1 text-sm font-medium">
          {ids.length} terpilih
        </span>
      </header>

      {error && (
        <div className="flex items-center gap-3 bg-red-100 px-4 py-2 text-sm text-red-700">
          <span className="flex-1">{error}</span>
          <button
            onClick={() => setError(null)}
            className="rounded px-2 py-0.5 hover:bg-red-200"
          >
            ✕
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 border-r border-slate-200 bg-white">
          <ColumnPicker
            columns={columns}
            picked={picked}
            onToggle={togglePicked}
            onClear={() => setPicked([])}
            onReset={() =>
              setPicked(DEFAULT_KOLOM.filter((c) => columns.includes(c)))
            }
          />
        </aside>

        <main className="flex min-w-0 flex-1 flex-col gap-4 overflow-hidden p-4">
          <FilterBar facets={facets} filters={filters} onChange={setFilters} />
          <SearchPanel fields={picked} filters={filters} onAdd={addIds} />
          <SelectionTable
            fields={picked}
            rows={displayRows}
            count={ids.length}
            sort={sort}
            loading={rowsLoading}
            exporting={exporting}
            onRemove={(id) => setIds((prev) => prev.filter((n) => n !== id))}
            onClear={() => setIds([])}
            onDownload={download}
            onHeaderSort={headerSort}
            onSortReset={() => setSort(null)}
          />
        </main>
      </div>
    </div>
  )
}
