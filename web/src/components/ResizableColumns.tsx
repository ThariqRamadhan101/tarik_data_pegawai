import type { MouseEvent as ReactMouseEvent } from 'react'

/** Gagang geser di tepi kanan header; klik 2x = kembali ke lebar otomatis. */
export function ResizeHandle({
  field,
  onResize,
  onReset,
}: {
  field: string
  onResize: (e: ReactMouseEvent, field: string) => void
  onReset: (field: string) => void
}) {
  return (
    <span
      onMouseDown={(e) => onResize(e, field)}
      onDoubleClick={(e) => {
        e.stopPropagation()
        onReset(field)
      }}
      onClick={(e) => e.stopPropagation()}
      className="absolute right-0 top-0 h-full w-2 cursor-col-resize hover:bg-blue-300"
      title="Geser untuk ubah lebar kolom (klik 2x untuk reset)"
    />
  )
}
