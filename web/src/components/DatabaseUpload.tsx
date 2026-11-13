import { useEffect, useRef, useState } from 'react'
import { errorText, uploadDatabase, type UploadResult } from '../lib/api'

const MAX_UPLOAD = 50 * 1024 * 1024 // sama dengan batas server

interface Props {
  onClose: () => void
  /** Dipanggil setelah upload sukses agar App memuat ulang meta/kolom. */
  onUpdated: () => Promise<void> | void
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Modal update database dari file xlsx EHRM.
 * Upload mengganti seluruh DB; server membuat backup dan menjalankan
 * extract + enrich sebelum mengganti file DB aktif.
 */
export default function DatabaseUpload({ onClose, onUpdated }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const choose = (f: File | null) => {
    setError(null)
    setResult(null)
    if (!f) {
      setFile(null)
      return
    }
    if (!f.name.toLowerCase().endsWith('.xlsx')) {
      setFile(null)
      setError('Pilih file .xlsx (bukan .xls/.csv).')
      return
    }
    if (f.size === 0) {
      setFile(null)
      setError('File kosong.')
      return
    }
    if (f.size > MAX_UPLOAD) {
      setFile(null)
      setError(`Ukuran file maksimal ${formatBytes(MAX_UPLOAD)}.`)
      return
    }
    setFile(f)
  }

  const submit = async () => {
    if (!file || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await uploadDatabase(file)
      setResult(r)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      await onUpdated()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-title"
        className="max-h-[90dvh] w-full max-w-lg overflow-y-auto rounded-xl bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 id="upload-title" className="text-sm font-semibold">
            Perbarui Database dari Excel
          </h2>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            aria-label="Tutup"
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3 px-4 py-4 text-sm">
          <p className="text-slate-600">
            Pilih file <b>.xlsx</b> dengan sheet <code>laporan-pegawai</code> dan
            struktur kolom yang sama dengan ekspor EHRM.
          </p>

          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            <p className="font-medium">Database aktif akan diganti.</p>
            <p className="mt-1">
              DB lama dibackup otomatis dan file sumber lama tetap tersimpan.
              Daftar terpilih serta filter akan dikosongkan setelah upload
              berhasil.
            </p>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
            disabled={busy}
            className="block w-full cursor-pointer rounded-md border border-slate-300 bg-white text-sm file:mr-3 file:cursor-pointer file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-slate-700 hover:file:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
          />

          {file && (
            <p className="text-xs text-slate-500">
              {file.name} · {formatBytes(file.size)}
            </p>
          )}

          {error && (
            <p className="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-700">
              {error}
            </p>
          )}

          {result && (
            <div className="rounded border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800">
              <p className="font-medium">
                Berhasil: {result.rows.toLocaleString('id-ID')} baris,{' '}
                {result.columns} kolom.
              </p>
              {result.source && <p className="mt-1">Sumber: {result.source}</p>}
              {result.backup && <p>Backup: {result.backup}</p>}
              {result.warnings.length > 0 && (
                <ul className="mt-1 list-disc pl-4">
                  {result.warnings.map((w, i) => (
                    <li key={`${i}-${w}`}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Tutup
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!file || busy}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? 'Memproses…' : 'Upload & Proses'}
          </button>
        </div>
      </div>
    </div>
  )
}
