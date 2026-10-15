import { useEffect, useRef, useState } from 'react'
import { EMPTY_FILTERS, hasActiveFilters, type Facets, type Filters } from '../lib/api'

interface Props {
  facets: Facets
  filters: Filters
  onChange: (f: Filters) => void
}

const BTN_CLS =
  'rounded-md border border-slate-300 bg-white px-2 py-1.5 text-left text-sm hover:border-slate-400 focus:border-blue-500 focus:outline-none'

interface MultiProps {
  label: string
  options: string[]
  selected: string[]
  onChange: (next: string[]) => void
  /** Lebar total (dropdown absolute mengikuti lebar ini). */
  width?: string
}

/**
 * Dropdown multi-pilihan: daftar checkbox + kotak cari (untuk daftar panjang
 * seperti 665 nama jabatan). Nilai OR di dalam grup; antar grup selalu AND.
 */
function MultiSelect({ label, options, selected, onChange, width = 'w-64' }: MultiProps) {
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
  const shown = needle
    ? options.filter((o) => o.toUpperCase().includes(needle))
    : options

  return (
    <div ref={rootRef} className={`relative flex flex-col gap-0.5 ${width}`}>
      <span className="text-xs font-medium text-slate-600">
        {label}
        {selected.length > 0 && (
          <span className="ml-1 font-semibold text-blue-600">({selected.length})</span>
        )}
      </span>
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
        <div className="absolute left-0 top-full z-20 mt-1 w-full rounded-md border border-slate-300 bg-white shadow-lg">
          {options.length > 8 && (
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Cari…"
              autoFocus
              className="w-full border-b border-slate-200 px-2 py-1.5 text-sm focus:outline-none"
            />
          )}
          <div className="max-h-60 overflow-auto py-1">
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
              <p className="px-2 py-1.5 text-sm text-slate-400">Tidak ada yang cocok.</p>
            )}
          </div>
          <div className="border-t border-slate-200 px-2 py-1.5 text-xs">
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-slate-500 hover:text-slate-700"
            >
              Kosongkan
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Filter terstruktur di atas kotak pencarian: unit organisasi, unit kerja,
 * jabatan (nilai persis), status pegawai, golongan, propinsi - semua
 * multi-pilihan; antar grup selalu digabung AND.
 */
export default function FilterBar({ facets, filters, onChange }: Props) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch })

  return (
    <div className="flex shrink-0 flex-wrap items-start gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <MultiSelect
        label="Unit Organisasi"
        options={facets.unitOrganisasi}
        selected={filters.unit}
        onChange={(v) => set({ unit: v })}
        width="w-72"
      />
      <MultiSelect
        label="Unit Kerja / Satuan Kerja"
        options={facets.unitKerja}
        selected={filters.unitKerja}
        onChange={(v) => set({ unitKerja: v })}
        width="w-72"
      />
      <MultiSelect
        label="Jenis Jabatan"
        options={facets.jenisJabatan}
        selected={filters.jenisJabatan}
        onChange={(v) => set({ jenisJabatan: v })}
        width="w-44"
      />
      <MultiSelect
        label="Jabatan"
        options={facets.namaJabatan}
        selected={filters.jabatanNilai}
        onChange={(v) => set({ jabatanNilai: v })}
        width="w-72"
      />
      <MultiSelect
        label="Status Pegawai"
        options={facets.statusPegawai}
        selected={filters.status}
        onChange={(v) => set({ status: v })}
        width="w-44"
      />
      <MultiSelect
        label="Golongan"
        options={facets.golongan}
        selected={filters.golongan}
        onChange={(v) => set({ golongan: v })}
        width="w-40"
      />
      <MultiSelect
        label="Propinsi"
        options={facets.propinsi}
        selected={filters.propinsi}
        onChange={(v) => set({ propinsi: v })}
        width="w-56"
      />
      <MultiSelect
        label="Potensi Menjabat"
        options={facets.potensiMenjabat}
        selected={filters.potensiMenjabat}
        onChange={(v) => set({ potensiMenjabat: v })}
        width="w-40"
      />
      <MultiSelect
        label="Potensi PPK"
        options={facets.potensiPpk}
        selected={filters.potensiPpk}
        onChange={(v) => set({ potensiPpk: v })}
        width="w-36"
      />
      <MultiSelect
        label="Potensi Bendahara"
        options={facets.potensiBendahara}
        selected={filters.potensiBendahara}
        onChange={(v) => set({ potensiBendahara: v })}
        width="w-44"
      />
      <MultiSelect
        label="Potensi PPSPM"
        options={facets.potensiPpspm}
        selected={filters.potensiPpspm}
        onChange={(v) => set({ potensiPpspm: v })}
        width="w-40"
      />

      {hasActiveFilters(filters) && (
        <button
          onClick={() => onChange({ ...EMPTY_FILTERS })}
          className="mt-5 rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          Reset filter
        </button>
      )}
    </div>
  )
}
