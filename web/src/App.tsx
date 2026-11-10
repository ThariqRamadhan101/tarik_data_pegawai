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
  getMeta,
  getRows,
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
  'PROPINSI',
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
  const [picked, setPicked] = useState<string[]>([])
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [ids, setIds] = useState<number[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [sort, setSort] = useState<SortState | null>(null)
  const [rowsLoading, setRowsLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Muat metadata + daftar kolom sekali di awal; rekonsiliasi localStorage.
  useEffect(() => {
    let cancel = false
    Promise.all([getMeta(), getColumns()])
      .then(([m, cols]) => {
        if (cancel) return
        setMeta(m)
        setColumns(cols)

        const savedCols = load<string[]>(LS_KOLOM)
        if (savedCols !== null && savedCols.length > 0) {
          setPicked(savedCols.filter((c) => cols.includes(c)))
        } else {
          // First load (no localStorage, or user cleared all picks): ceklis semua DEFAULT_KOLOM.
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
    <div className="flex min-h-dvh flex-col bg-slate-50 lg:h-dvh lg:overflow-hidden">
      {/* Header - fixed */}
      <header className="flex shrink-0 items-center gap-2 bg-slate-800 px-3 py-2.5 text-white shadow-md">
        {/* Hamburger button - mobile only */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="rounded-lg p-1.5 hover:bg-slate-700 lg:hidden"
          aria-label="Buka panel kolom"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
        
        <h1 className="truncate text-sm font-semibold lg:text-base">Cari & Pilih Pegawai</h1>
        {meta && (
          <span className="hidden truncate text-xs text-slate-400 lg:inline">
            {meta.rows.toLocaleString('id-ID')} baris
          </span>
        )}
        <span className="ml-auto shrink-0 rounded-full bg-blue-600 px-2.5 py-1 text-xs font-medium lg:px-3 lg:text-sm">
          {ids.length} terpilih
        </span>
      </header>

      {/* Main content */}
      <div className="flex flex-col lg:flex-1 lg:flex-row lg:overflow-hidden">
        {/* Desktop sidebar - always visible on lg+ */}
        <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:flex lg:flex-col">
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

        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="absolute right-0 top-0 h-full w-80 max-w-[85vw] bg-white shadow-xl">
              <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                <h2 className="text-sm font-semibold">Pilih Kolom</h2>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="rounded-lg p-1.5 hover:bg-slate-100"
                  aria-label="Tutup"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <ColumnPicker
                columns={columns}
                picked={picked}
                onToggle={(col) => {
                  togglePicked(col)
                }}
                onClear={() => setPicked([])}
                onReset={() =>
                  setPicked(DEFAULT_KOLOM.filter((c) => columns.includes(c)))
                }
              />
            </div>
          </div>
        )}

        {/* Main scrollable area */}
        <main className="flex min-w-0 flex-col gap-3 p-3 lg:flex-1 lg:gap-4 lg:overflow-hidden lg:p-4">
          {error && (
            <div className="flex shrink-0 items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <span className="flex-1">{error}</span>
              <button
                onClick={() => setError(null)}
                className="shrink-0 rounded p-1 hover:bg-red-100"
                aria-label="Tutup error"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )}

          <FilterBar columns={columns} filters={filters} onChange={setFilters} />

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
