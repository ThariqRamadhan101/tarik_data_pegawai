import { useMemo, useState } from 'react'

interface Props {
  /** Semua kolom di database (urut skema). */
  columns: string[]
  /** Kolom terpilih user - urutan array = urutan tampil di tabel & unduhan. */
  picked: string[]
  onToggle: (col: string) => void
  onClear: () => void
  onReset: () => void
}

/**
 * Panel pemilih kolom. Semua kolom database ditawarkan (termasuk kolom
 * enrichment yang ditambahkan lewat ALTER TABLE - otomatis muncul di sini).
 */
export default function ColumnPicker({
  columns,
  picked,
  onToggle,
  onClear,
  onReset,
}: Props) {
  const [filter, setFilter] = useState('')
  const visible = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return f ? columns.filter((c) => c.toLowerCase().includes(f)) : columns
  }, [columns, filter])

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-200 px-3 py-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Kolom Ditampilkan</h2>
          <span className="text-xs text-slate-500">{picked.length} dipilih</span>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          Urutan centang = urutan kolom.
        </p>
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Cari kolom…"
          className="mt-2 w-full rounded border border-slate-300 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
        />
        <div className="mt-2 flex gap-2 text-xs">
          <button
            onClick={onReset}
            className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100"
          >
            Reset default
          </button>
          <button
            onClick={onClear}
            className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100"
          >
            Kosongkan
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {visible.length === 0 && (
          <p className="text-xs text-slate-500">Tidak ada kolom cocok.</p>
        )}
        {visible.map((c) => (
          <label
            key={c}
            className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-slate-100"
          >
            <input
              type="checkbox"
              checked={picked.includes(c)}
              onChange={() => onToggle(c)}
              className="accent-blue-600"
            />
            <span className="truncate" title={c}>
              {c}
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}
