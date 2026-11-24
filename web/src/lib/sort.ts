import type { Row } from './api'

export interface SortState {
  field: string
  dir: 'asc' | 'desc'
}

/** Nilai sel sebagai teks; null -> ''. */
export function cellText(row: Row, field: string): string {
  const v = row[field]
  return v == null ? '' : String(v)
}

/**
 * Urutkan baris untuk Daftar Terpilih.
 * - case-insensitive & numerik-aware (locale 'id'),
 * - nilai kosong selalu di bawah,
 * - tanpa sort mengembalikan urutan input (urutan tambah) apa adanya.
 * - mendukung multi-kolom via array SortState.
 */
export function sortRows(rows: Row[], sort: SortState | SortState[] | null): Row[] {
  const sorts = Array.isArray(sort) ? sort : sort ? [sort] : []
  if (sorts.length === 0) return rows
  return [...rows].sort((a, b) => {
    for (const s of sorts) {
      const mul = s.dir === 'asc' ? 1 : -1
      const av = cellText(a, s.field)
      const bv = cellText(b, s.field)
      if (!av && bv) return 1
      if (av && !bv) return -1
      const cmp = mul * av.localeCompare(bv, 'id', { numeric: true })
      if (cmp !== 0) return cmp
    }
    return 0
  })
}

/** Default sort untuk download: unor -> unker -> usia (semua numerik asc). */
export const DEFAULT_DOWNLOAD_SORT: SortState[] = [
  { field: 'URUTAN UNIT ORGANISASI', dir: 'asc' },
  { field: 'URUTAN UNKER / SATKER PS', dir: 'asc' },
  { field: 'USIA', dir: 'asc' },
]
