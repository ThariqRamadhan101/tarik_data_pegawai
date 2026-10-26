import { useCallback, useEffect, useRef, useState } from 'react'
import {
  EMPTY_FILTERS,
  getFacets,
  hasActiveFilters,
  type Facets,
  type Filters,
} from '../lib/api'

interface Props {
  /** Semua kolom data yang tersedia (dari /api/columns). */
  columns: string[]
  filters: Filters
  onChange: (f: Filters) => void
}

const BTN_CLS =
  'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-left text-sm hover:border-slate-400 focus:border-blue-500 focus:outline-none'
const SELECT_CLS =
  'max-w-[16rem] truncate rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm hover:border-slate-400 focus:border-blue-500 focus:outline-none'

/** Kolom yang sudah terpasang sebagai filter saat halaman pertama dibuka. */
const DEFAULT_FILTER_COLUMNS = [
  'UNIT ORGANISASI',
  'UNIT KERJA / SATUAN KERJA',
  'JENIS JABATAN',
  'NAMA JABATAN',
  'STATUS PEGAWAI',
  'GOLONGAN',
  'PROPINSI',
  'POTENSI MENJABAT',
  'POTENSI PPK',
  'POTENSI BENDAHARA',
  'POTENSI PPSPM',
]

interface MultiProps {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  /** Bila diisi, tampilkan tombol × untuk melepas kolom filter ini. */
  onRemove?: () => void
  /** Pilihan masih diambil dari server. */
  loading?: boolean
  /** Lebar total (dropdown absolute mengikuti lebar ini). */
  width?: string
}

/**
 * Dropdown multi-pilihan: daftar checkbox + kotak cari (untuk daftar panjang
 * seperti 665 nama jabatan). Nilai OR di dalam grup; antar grup selalu AND.
 */
function MultiSelect({
  label,
  options,
  selected,
  onChange,
  onRemove,
  loading = false,
  width = 'w-64',
}: MultiProps) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  // Tutup panel saat klik di luar komponen.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const toggle = (v: string) =>
    onChange(
      selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v],
    )

  const needle = text.trim().toUpperCase()
  const MAX_SHOW = 50
  const showAll = needle.length > 0 || options.length <= MAX_SHOW
  const shown = showAll
    ? needle
      ? options.filter((o) => o.toUpperCase().includes(needle))
      : options
    : []
  const emptyMsg =
    options.length > MAX_SHOW && needle.length === 0
      ? "Ketik untuk mencari…"
      : "Tidak ada yang cocok."

  return (
    <div ref={rootRef} className={`relative flex flex-col gap-0.5 ${width}`}>
      <div className="flex items-center gap-1">
        <span
          className="min-w-0 flex-1 truncate text-xs font-medium text-slate-600"
          title={label}
        >
          {label}
          {selected.length > 0 && (
            <span className="ml-1 font-semibold text-blue-600">
              ({selected.length})
            </span>
          )}
        </span>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            title={`Hapus filter ${label}`}
            className="shrink-0 rounded px-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
          >
            ×
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={BTN_CLS}
        title={selected.join(', ') || '(semua)'}
      >
        {selected.length === 0
          ? '(semua)'
          : selected.length <= 2
            ? selected.join(', ')
            : `${selected.length} nilai dipilih`}
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-full rounded-md border border-slate-300 bg-white shadow-lg">
          {!loading && options.length > 8 && (
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Cari…"
              autoFocus
              className="w-full border-b border-slate-200 px-2 py-1.5 text-sm focus:outline-none"
            />
          )}
          <div className="max-h-60 overflow-auto py-1">
            {loading ? (
              <p className="px-2 py-1.5 text-sm text-slate-400">Memuat pilihan…</p>
            ) : (
              <>
                {shown.map((o) => (
                  <label
                    key={o}
                    className="flex cursor-pointer items-start gap-2 px-2 py-1 text-sm hover:bg-slate-50"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(o)}
                      onChange={() => toggle(o)}
                      className="mt-0.5"
                    />
                    <span className="min-w-0 break-words">{o}</span>
                  </label>
                ))}
                {!shown.length && (
                  <p className="px-2 py-1.5 text-sm text-slate-400">{emptyMsg}</p>
                )}
              </>
            )}
          </div>
          {!loading && (
            <div className="border-t border-slate-200 px-2 py-1.5 text-xs">
              <button
                type="button"
                onClick={() => onChange([])}
                className="text-slate-500 hover:text-slate-700"
              >
                Kosongkan
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Filter dinamis: user memilih sendiri kolom mana yang ingin difilter.
 * Nilai OR di dalam satu kolom, AND antar kolom. Opsi filter diambil
 * lazy per kolom (`/api/facets?column=...`) agar payload awal kecil.
 */
export default function FilterBar({ columns, filters, onChange }: Props) {
  const [active, setActive] = useState<string[]>(DEFAULT_FILTER_COLUMNS)
  const [open, setOpen] = useState(false)
  const [facets, setFacets] = useState<Facets>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})
  const requested = useRef<Set<string>>(new Set())

  const loadFacets = useCallback((cols: string[]) => {
    const need = cols.filter((c) => c && !requested.current.has(c))
    if (!need.length) return
    need.forEach((c) => requested.current.add(c))
    setLoading((prev) => {
      const next = { ...prev }
      need.forEach((c) => {
        next[c] = true
      })
      return next
    })
    getFacets(need)
      .then((data) => setFacets((prev) => ({ ...prev, ...data })))
      .catch(() => {
        // Izinkan percobaan ulang saat kolom ini diminta lagi.
        need.forEach((c) => requested.current.delete(c))
      })
      .finally(() => {
        setLoading((prev) => {
          const next = { ...prev }
          need.forEach((c) => {
            delete next[c]
          })
          return next
        })
      })
  }, [])

  // Muat opsi untuk kolom default begitu daftar kolom tersedia.
  useEffect(() => {
    if (!columns.length) return
    loadFacets(DEFAULT_FILTER_COLUMNS.filter((c) => columns.includes(c)))
  }, [columns, loadFacets])

  const activeCols = active.filter((c) => columns.includes(c))
  const available = columns.filter((c) => !active.includes(c))

  const addColumn = (col: string) => {
    if (!col) return
    setActive((prev) => (prev.includes(col) ? prev : [...prev, col]))
    loadFacets([col])
    setOpen(true)
  }

  const removeColumn = (col: string) => {
    setActive((prev) => prev.filter((c) => c !== col))
    if (filters[col]) {
      const next = { ...filters }
      delete next[col]
      onChange(next)
    }
  }

  const setValues = (col: string, vals: string[]) => {
    const next = { ...filters }
    if (vals.length === 0) delete next[col]
    else next[col] = vals
    onChange(next)
  }

  return (
    <div className="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-3 shadow-sm lg:px-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Filter</h2>
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 lg:hidden"
          aria-expanded={open}
          aria-controls="filter-body"
        >
          {open ? 'Sembunyikan' : 'Tampilkan'}
        </button>
        {hasActiveFilters(filters) && (
          <button
            onClick={() => onChange({ ...EMPTY_FILTERS })}
            className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-100"
          >
            Reset filter
          </button>
        )}
        <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-500">
          <span className="whitespace-nowrap">Tambah filter kolom</span>
          <select
            value=""
            onChange={(e) => addColumn(e.target.value)}
            className={SELECT_CLS}
            title="Pilih kolom yang ingin difilter"
          >
            <option value="">Pilih kolom…</option>
            {available.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        id="filter-body"
        className={`${open ? 'flex' : 'hidden'} flex-wrap items-start gap-3 lg:flex`}
      >
        {activeCols.map((col) => (
          <MultiSelect
            key={col}
            label={col}
            options={facets[col] ?? []}
            selected={filters[col] ?? []}
            onChange={(v) => setValues(col, v)}
            onRemove={() => removeColumn(col)}
            loading={!!loading[col]}
          />
        ))}
        {activeCols.length === 0 && (
          <p className="text-xs text-slate-500">
            Belum ada kolom filter. Pilih kolom di atas untuk memulai.
          </p>
        )}
      </div>
    </div>
  )
}
