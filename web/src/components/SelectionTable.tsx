import { type Row } from '../lib/api'
import type { SortState } from '../lib/sort'
interface Props {
  fields: string[]
  /** Baris TELAH diurutkan sesuai `sort` oleh App (download pun pakai urutan ini). */
  rows: Row[]
  /** ids terpilih (urutan tambah) - rows mungkin lebih sedikit bila kolom belum dipilih. */
  count: number
  sort: SortState | null
  loading: boolean
  exporting: boolean
  onRemove: (id: number) => void
  onClear: () => void
  onDownload: () => void
  onHeaderSort: (field: string) => void
  onSortReset: () => void
}

function cell(row: Row, col: string): string {
  const v = row[col]
  return v == null ? '' : String(v)
}

/** Daftar pegawai terpilih (dari hasil pencarian), siap diunduh ke Excel. */
export default function SelectionTable({
  fields,
  rows,
  count,
  sort,
  loading,
  exporting,
  onRemove,
  onClear,
  onDownload,
  onHeaderSort,
  onSortReset,
}: Props) {
  return (
    <section className="flex flex-col rounded-lg border border-slate-200 bg-white shadow-sm lg:min-h-0 lg:flex-[2]">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
        <h2 className="text-sm font-semibold">Daftar Terpilih</h2>
        <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
          {count} pegawai
        </span>
        {sort && (
          <button
            onClick={onSortReset}
            className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-200"
            title="Kembalikan ke urutan tambah"
          >
            Urut: {sort.field} {sort.dir === 'asc' ? '▲' : '▼'} · ↺ urutan tambah
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <button
            onClick={onClear}
            disabled={!count || exporting}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Kosongkan
          </button>
          <button
            onClick={onDownload}
            disabled={!count || !fields.length || exporting}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            title="Unduh daftar ini sebagai file Excel"
          >
            {exporting ? 'Menyiapkan…' : '⬇ Download Excel'}
          </button>
        </div>
      </div>

      <div className="lg:min-h-0 lg:flex-1 lg:overflow-auto">
        {!fields.length && (
          <p className="p-4 text-sm text-slate-500">
            Centang kolom di panel kiri untuk menampilkan daftar terpilih.
          </p>
        )}
        {fields.length > 0 && count === 0 && (
          <p className="p-4 text-sm text-slate-500">
            Belum ada pegawai. Cari di atas lalu klik <b>+ Tambah</b>.
          </p>
        )}
        {fields.length > 0 && count > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="border-b px-2 py-2 font-medium">Aksi</th>
                  {fields.map((f) => (
                    <th
                      key={f}
                      className="min-w-[120px] border-b font-medium"
                      title={f}
                    >
                      <button
                        onClick={() => onHeaderSort(f)}
                        className="flex w-full items-center gap-1 px-3 py-2 hover:bg-slate-100"
                        title={
                          sort?.field === f && sort.dir === 'asc'
                            ? 'Urutkan Z→A'
                            : 'Urutkan A→Z'
                        }
                      >
                        {f}
                        <span className="text-[10px] text-blue-700">
                          {sort?.field === f ? (sort.dir === 'asc' ? '▲' : '▼') : ''}
                        </span>
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="odd:bg-white even:bg-slate-50">
                    <td className="border-b border-slate-100 px-2 py-1.5">
                      <button
                        onClick={() => onRemove(r.id)}
                        className="rounded bg-slate-200 px-2 py-1 text-xs font-medium hover:bg-red-600 hover:text-white"
                        title="Hapus dari daftar"
                      >
                        ✕
                      </button>
                    </td>
                    {fields.map((f) => (
                      <td
                        key={f}
                        className="min-w-[120px] truncate border-b border-slate-100 px-3 py-1.5"
                        title={cell(r, f)}
                      >
                        {cell(r, f)}
                      </td>
                    ))}
                  </tr>
                ))}
                {loading && (
                  <tr>
                    <td
                      colSpan={fields.length + 1}
                      className="px-4 py-4 text-center text-sm text-slate-500"
                    >
                      Memuat…
                    </td>
                  </tr>
                )}
                {!loading && rows.length < count && (
                  <tr>
                    <td
                      colSpan={fields.length + 1}
                      className="px-4 py-3 text-center text-xs text-amber-600"
                    >
                      {count - rows.length} id tidak ditemukan di database -
                      kemungkinan data sudah diekstrak ulang. Cari ulang.
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
