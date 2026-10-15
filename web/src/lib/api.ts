/** Klien JSON API server/server.py (Python stdlib). */

export type Row = Record<string, string | number | null> & { id: number }

export interface Meta {
  source: string
  generatedAt: string
  rows: number
  columns: number
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { error?: string }
      if (body.error) msg = body.error
    } catch {
      /* respons bukan JSON - pakai status saja */
    }
    throw new Error(msg)
  }
  return (await res.json()) as T
}

export async function getMeta(): Promise<Meta> {
  return request<Meta>('/api/meta')
}

export async function getColumns(): Promise<string[]> {
  const r = await request<{ columns: string[] }>('/api/columns')
  return r.columns
}

/** Nilai distinct untuk filter multi-pilihan. */
export interface Facets {
  unitOrganisasi: string[]
  unitKerja: string[]
  namaJabatan: string[]
  jenisJabatan: string[]
  statusPegawai: string[]
  golongan: string[]
  propinsi: string[]
  potensiMenjabat: string[]
  potensiPpk: string[]
  potensiBendahara: string[]
  potensiPpspm: string[]
}

export async function getFacets(): Promise<Facets> {
  const r = await request<Record<string, string[]>>('/api/facets')
  return {
    unitOrganisasi: r['UNIT ORGANISASI'] ?? [],
    unitKerja: r['UNIT KERJA / SATUAN KERJA'] ?? [],
    namaJabatan: r['NAMA JABATAN'] ?? [],
    jenisJabatan: r['JENIS JABATAN'] ?? [],
    statusPegawai: r['STATUS PEGAWAI'] ?? [],
    golongan: r['GOLONGAN'] ?? [],
    propinsi: r['PROPINSI'] ?? [],
    potensiMenjabat: r['POTENSI MENJABAT'] ?? [],
    potensiPpk: r['POTENSI PPK'] ?? [],
    potensiBendahara: r['POTENSI BENDAHARA'] ?? [],
    potensiPpspm: r['POTENSI PPSPM'] ?? [],
  }
}

/** Filter multi-pilihan (OR dalam satu grup; antar grup selalu AND). */
export interface Filters {
  unit: string[]
  unitKerja: string[]
  jabatanNilai: string[]
  jenisJabatan: string[]
  status: string[]
  golongan: string[]
  propinsi: string[]
  potensiMenjabat: string[]
  potensiPpk: string[]
  potensiBendahara: string[]
  potensiPpspm: string[]
}

export const EMPTY_FILTERS: Filters = {
  unit: [],
  unitKerja: [],
  jabatanNilai: [],
  jenisJabatan: [],
  status: [],
  golongan: [],
  propinsi: [],
  potensiMenjabat: [],
  potensiPpk: [],
  potensiBendahara: [],
  potensiPpspm: [],
}

export function hasActiveFilters(f: Filters): boolean {
  return (
    f.unit.length > 0 ||
    f.unitKerja.length > 0 ||
    f.jabatanNilai.length > 0 ||
    f.jenisJabatan.length > 0 ||
    f.status.length > 0 ||
    f.golongan.length > 0 ||
    f.propinsi.length > 0 ||
    f.potensiMenjabat.length > 0 ||
    f.potensiPpk.length > 0 ||
    f.potensiBendahara.length > 0 ||
    f.potensiPpspm.length > 0
  )
}

/** Tiap nilai dikirim sebagai param berulang (?unit=A&unit=B). */
function appendFilters(params: URLSearchParams, filters?: Filters) {
  if (!filters) return
  const add = (key: string, vals: string[]) =>
    vals.forEach((v) => params.append(key, v))
  add('unit', filters.unit)
  add('unit_kerja', filters.unitKerja)
  add('jabatan_nilai', filters.jabatanNilai)
  add('jenis_jabatan', filters.jenisJabatan)
  add('status', filters.status)
  add('golongan', filters.golongan)
  add('propinsi', filters.propinsi)
  add('potensi_menjabat', filters.potensiMenjabat)
  add('potensi_ppk', filters.potensiPpk)
  add('potensi_bendahara', filters.potensiBendahara)
  add('potensi_ppspm', filters.potensiPpspm)
}

/** Pencarian multi-keyword AND (semua kata harus cocok), seperti formula Finder Excel.
 * `count` = total yang cocok (bisa ribuan); `rows` = teratas sesuai `limit`. */
export async function search(
  q: string,
  filters?: Filters,
  limit = 50,
): Promise<{ rows: Row[]; count: number }> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  appendFilters(params, filters)
  const r = await request<{ rows: Row[]; count: number }>(
    `/api/search?${params}`,
  )
  return { rows: r.rows, count: r.count }
}

/** SEMUA id yang cocok dengan q + filter (tanpa limit tampil). */
export async function searchIds(q: string, filters?: Filters): Promise<number[]> {
  const params = new URLSearchParams({ q })
  appendFilters(params, filters)
  const r = await request<{ count: number; ids: number[] }>(`/api/ids?${params}`)
  return r.ids
}

const ROWS_CHUNK = 500 // batas ids per request /api/rows (jaga panjang URL / header dev-proxy)

export async function getRows(ids: number[], fields: string[]): Promise<Row[]> {
  const chunks: number[][] = []
  for (let i = 0; i < ids.length; i += ROWS_CHUNK) {
    chunks.push(ids.slice(i, i + ROWS_CHUNK))
  }
  const results = await Promise.all(
    chunks.map(async (chunk) => {
      const params = new URLSearchParams({
        ids: chunk.join(','),
        fields: fields.join(','),
      })
      const r = await request<{ rows: Row[] }>(`/api/rows?${params}`)
      return r.rows
    }),
  )
  return results.flat()
}

/** Minta server menyusun xlsx lalu unduh ke browser. */
export async function downloadSelection(
  ids: number[],
  fields: string[],
): Promise<void> {
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, fields }),
  })
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { error?: string }
      if (body.error) msg = body.error
    } catch {
      /* abaikan */
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pegawai-terpilih-${new Date().toISOString().slice(0, 10)}.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
