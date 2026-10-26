import { useEffect, useRef, useState } from 'react'
import {
  errorText,
  hasActiveFilters,
  search,
  searchIds,
  type Filters,
  type Row,
} from '../lib/api'

interface Props {
  /** Kolom yang ditampilkan di tabel hasil (urutan user). */
  fields: string[]
  /** Filter dinamis per kolom dari FilterBar; q boleh kosong bila ada filter. */
  filters: Filters
  onAdd: (ids: number[]) => void
}

const DISPLAY_LIMIT = 200 // baris tampil per halaman hasil; total cocok bisa ribuan

function cell(row: Row, col: string): string {
  const v = row[col]
  return v == null ? '' : String(v)
}

/**
 * Kotak pencarian: beberapa kata dipisah spasi, SEMUA harus cocok
 * (peniruan formula Excel TEXTSPLIT + SEARCH + BYROW). Beberapa query sekaligus
 * dipisah ';' -> di-OR-kan (mis. "agus prasarana strategis; budi sumber daya air").
 * Digabungkan dengan filter dari FilterBar.
 */
export default function SearchPanel({ fields, filters, onAdd }: Props) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<Row[]>([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [addingAll, setAddingAll] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const seq = useRef(0)

  const hasFilter = hasActiveFilters(filters)

  const chips: [string, string[]][] = Object.entries(filters).filter(
    ([, vals]) => vals.length > 0,
  )

  // Debounce 300ms; respons lama diabaikan (seq guard).
  useEffect(() => {
    const text = q.trim()
    if (!text && !hasFilter) {
      setResults([])
      setCount(0)
      setSearched(false)
      setError(null)
      return
    }
    const mySeq = ++seq.current
    setLoading(true)
    const t = setTimeout(() => {
      search(text, filters, DISPLAY_LIMIT)
        .then((r) => {
          if (mySeq !== seq.current) return
          setResults(r.rows)
          setCount(r.count)
          setSearched(true)
          setError(null)
        })
        .catch((e) => {
          if (mySeq !== seq.current) return
          setError(errorText(e))
        })
        .finally(() => {
          if (mySeq === seq.current) setLoading(false)
        })
    }, 300)
    return () => clearTimeout(t)
  }, [q, hasFilter, filters])

  const add = (ids: number[]) => {
    if (ids.length) onAdd(ids)
  }

  /** Tambah SEMUA yang cocok (bisa ribuan, mis. satu unit utuh) - bukan hanya yang tampil. */
  const addAll = async () => {
    setAddingAll(true)
    setError(null)
    try {
      add(await searchIds(q.trim(), filters))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setAddingAll(false)
    }
  }

  return (
    <section className="flex flex-col rounded-lg border border-slate-200 bg-white shadow-sm lg:min-h-0 lg:flex-[3]">
      <div className="border-b border-slate-200 px-3 py-2.5 lg:px-4 lg:py-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder='Cari Nama/NIP/Unit Organisasi'
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-200"
            autoFocus
          />
          <button
            onClick={addAll}
            disabled={!count || addingAll}
            className="w-full whitespace-nowrap rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 lg:w-auto"
            title="Tambahkan SEMUA yang cocok (bisa ribuan, mis. satu unit utuh) ke daftar terpilih"
          >
            {addingAll
              ? 'Menambah…'
              : `Tambah semua (${count.toLocaleString('id-ID')})`}
          </button>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500 lg:gap-2">
          {(loading || searched) && (
            <span>
              {loading
                ? 'Mencari…'
                : `${count.toLocaleString('id-ID')} cocok — menampilkan ${results.length} teratas`}
            </span>
          )}
          {chips.map(([label, vals]) =>
            vals.length ? (
              <span
                key={label}
                className="rounded bg-slate-200 px-1.5 py-0.5"
                title={vals.join(', ')}
              >
                {label}: {vals.length === 1 ? vals[0] : `${vals.length} nilai`}
              </span>
            ) : null,
          )}
        </div>
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </div>

      <div className="lg:min-h-0 lg:flex-1 lg:overflow-auto">
        {!fields.length && (
          <p className="p-4 text-sm text-slate-500">
            Centang minimal satu kolom di panel kiri.
          </p>
        )}
        {fields.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  {fields.map((f) => (
                    <th
                      key={f}
                      className="min-w-[120px] border-b px-3 py-2 font-medium"
                      title={f}
                    >
                      {f}
                    </th>
                  ))}
                  <th className="border-b px-2 py-2 font-medium">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id} className="odd:bg-white even:bg-slate-50">
                    {fields.map((f) => (
                      <td
                        key={f}
                        className="min-w-[120px] truncate border-b border-slate-100 px-3 py-1.5"
                        title={cell(r, f)}
                      >
                        {cell(r, f)}
                      </td>
                    ))}
                    <td className="border-b border-slate-100 px-2 py-1.5">
                      <button
                        onClick={() => add([r.id])}
                        className="rounded bg-slate-200 px-2 py-1 text-xs font-medium hover:bg-blue-600 hover:text-white"
                        title="Tambahkan ke daftar terpilih"
                      >
                        + Tambah
                      </button>
                    </td>
                  </tr>
                ))}
                {searched && !results.length && !loading && (
                  <tr>
                    <td
                      colSpan={fields.length + 1}
                      className="px-4 py-6 text-center text-sm text-slate-500"
                    >
                      Tidak ada yang cocok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
