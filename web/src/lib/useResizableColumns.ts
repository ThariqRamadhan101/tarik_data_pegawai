import { useState, type MouseEvent as ReactMouseEvent } from 'react'

/**
 * Lebar kolom drag-resize untuk tabel (session-only, per tabel).
 * Dipakai tabel hasil pencarian dan daftar terpilih yang nilainya panjang.
 */
export function useResizableColumns() {
  const [widths, setWidths] = useState<Record<string, number>>({})

  const resetWidth = (field: string) =>
    setWidths((prev) => {
      if (!(field in prev)) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })

  const startResize = (e: ReactMouseEvent, field: string) => {
    e.preventDefault()
    e.stopPropagation()
    const th = (e.currentTarget as HTMLElement).closest('th')
    const startW = th?.offsetWidth ?? 160
    const startX = e.clientX
    const onMove = (ev: MouseEvent) => {
      const w = Math.max(60, Math.min(1200, startW + ev.clientX - startX))
      setWidths((prev) => ({ ...prev, [field]: w }))
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const thStyle = (field: string) =>
    widths[field] ? { width: widths[field] } : undefined

  const tdStyle = (field: string) =>
    widths[field]
      ? {
          width: widths[field],
          minWidth: widths[field],
          maxWidth: widths[field],
        }
      : undefined

  return { startResize, resetWidth, thStyle, tdStyle }
}
