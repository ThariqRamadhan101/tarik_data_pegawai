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
 */
export function sortRows(rows: Row[], sort: SortState | null): Row[] {
  if (!sort) return rows
  const mul = sort.dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    const av = cellText(a, sort.field)
    const bv = cellText(b, sort.field)
    if (!av && bv) return 1
    if (av && !bv) return -1
    return mul * av.localeCompare(bv, 'id', { numeric: true })
  })
}
