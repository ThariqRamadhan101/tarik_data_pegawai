"""Server lokal: JSON API (SQLite) + static files dari web/dist.

Tanpa dependency eksternal (http.server + sqlite3 + openpyxl sudah cukup).

Endpoints:
  GET  /api/meta                     -> sumber & waktu generate DB
  GET  /api/columns                  -> daftar kolom (dari PRAGMA table_info)
  GET  /api/search?q=..&limit=..     -> pencarian multi-keyword AND (logika Finder Excel)
  GET  /api/rows?ids=1,2,3&fields=A,B-> baris terpilih, kolom terpilih
  POST /api/export  {ids, fields}    -> unduh xlsx daftar terpilih
  GET  /...                          -> static web/dist (SPA)

Jalankan setelah build frontend:
  python scripts/extract_pegawai.py
  cd web && npm.cmd install && npm.cmd run build
  python server/server.py            -> http://localhost:8000

Dev: jalankan `python server/server.py` + `cd web && npm.cmd run dev`
(Vite proxy /api -> localhost:8000).
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
import sys
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "database" / "pegawai.db"
WEB_DIST = ROOT / "web" / "dist"

MAX_LIMIT = 200          # batas baris tampil per pencarian (UI menampilkan teratas)
MAX_ROWS = 40_000        # batas ids untuk /api/rows dan /api/export (> total 37.924 baris)
MAX_ALL_IDS = 40_000     # batas /api/ids
MAX_BODY = 10 * 1024 * 1024

db_path: Path = DEFAULT_DB


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def open_db() -> sqlite3.Connection:
    if not db_path.is_file():
        raise FileNotFoundError(
            f"{db_path} tidak ada - jalankan: python scripts/extract_pegawai.py"
        )
    con = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def data_columns(con: sqlite3.Connection) -> list[str]:
    """Kolom yang boleh dilihat user (semua kecuali kolom sistem)."""
    rows = con.execute("PRAGMA table_info(pegawai)").fetchall()
    return [r["name"] for r in rows if r["name"] not in ("id", "finder_text")]


def validate_fields(con: sqlite3.Connection, fields: list[str]) -> list[str]:
    allowed = set(data_columns(con))
    bad = [f for f in fields if f not in allowed]
    if bad:
        raise ValueError(f"Kolom tidak dikenal: {', '.join(bad)}")
    return fields


def parse_csv(value: str) -> list[str]:
    return [v for v in value.split(",") if v]


def parse_ids(values: list[int]) -> list[int]:
    ids: list[int] = []
    for v in values:
        if not isinstance(v, int):
            raise ValueError("ids harus berisi angka")
        ids.append(v)
    if len(ids) > MAX_ROWS:
        raise ValueError(f"Maksimal {MAX_ROWS} baris per request")
    return ids


def escape_like(token: str) -> str:
    return token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def in_condition(col: str, values: list[str]) -> tuple[str, list[str]] | None:
    """Kondisi exact-match multi-nilai: UPPER(kolom) IN (?, ...). None bila kosong."""
    vals = [v.strip().upper() for v in values if v and v.strip()]
    if not vals:
        return None
    marks = ",".join("?" for _ in vals)
    return f"UPPER({quote_ident(col)}) IN ({marks})", vals


def build_conditions(
    q: str,
    unit: list[str] | None = None,
    unit_kerja: list[str] | None = None,
    jabatan: str = "",
    jabatan_nilai: list[str] | None = None,
    status: list[str] | None = None,
    golongan: list[str] | None = None,
    propinsi: list[str] | None = None,
    jenis_jabatan: list[str] | None = None,
    potensi_menjabat: list[str] | None = None,
    potensi_ppk: list[str] | None = None,
    potensi_bendahara: list[str] | None = None,
    potensi_ppspm: list[str] | None = None,
    mode: str = "and",
) -> tuple[str, list[str]]:
    """Susun WHERE (tanpa ranking) untuk q + grup filter multi-pilihan.

    q boleh berisi beberapa query dipisah ';' - tiap segmen di-OR-kan sebagai
    alternatif, di dalam segmen SEMUA kata harus cocok (AND, gaya Finder).
    Tiap grup filter (multi-nilai persis, jabatan per-kata berisi) di-OR di
    dalam grup, antar grup digabung mode 'and' (default) atau 'or'.
    Mengembalikan ('', []) bila tanpa kondisi.
    """
    if mode not in ("and", "or"):
        raise ValueError("mode harus 'and' atau 'or'")

    # Query multi-segmen: 'a b; c d' -> (a AND b) OR (c AND d).
    seg_groups: list[str] = []
    params: list[str] = []
    for seg in q.split(";"):
        toks = [k.upper() for k in seg.split() if k.strip()]
        if not toks:
            continue
        seg_groups.append(
            "("
            + " AND ".join(
                "UPPER(finder_text) LIKE ? ESCAPE '\\'" for _ in toks
            )
            + ")"
        )
        params.extend(f"%{escape_like(t)}%" for t in toks)
    where_parts = (
        ["(" + " OR ".join(seg_groups) + ")"]
        if len(seg_groups) > 1
        else list(seg_groups)
    )

    # Grup filter.
    filters: list[tuple[str, list[str]]] = []
    for col, values in (
        ("UNIT ORGANISASI", unit),
        ("UNIT KERJA / SATUAN KERJA", unit_kerja),
        ("NAMA JABATAN", jabatan_nilai),
        ("STATUS PEGAWAI", status),
        ("GOLONGAN", golongan),
        ("PROPINSI", propinsi),
        ("JENIS JABATAN", jenis_jabatan),
        ("POTENSI MENJABAT", potensi_menjabat),
        ("POTENSI PPK", potensi_ppk),
        ("POTENSI BENDAHARA", potensi_bendahara),
        ("POTENSI PPSPM", potensi_ppspm),
    ):
        cond = in_condition(col, values or [])
        if cond:
            filters.append(cond)
    for t in (k.upper() for k in jabatan.split() if k.strip()):
        filters.append(
            (
                "UPPER(\"NAMA JABATAN\") LIKE ? ESCAPE '\\'",
                [f"%{escape_like(t)}%"],
            )
        )

    if not where_parts and not filters:
        return "", []

    if filters:
        conds = [c for c, _ in filters]
        fparams = [p for _, ps in filters for p in ps]
        if mode == "or" and len(filters) > 1:
            where_parts.append("(" + " OR ".join(conds) + ")")
            params.extend(fparams)
        else:
            where_parts.extend(conds)
            params.extend(fparams)

    return " AND ".join(where_parts), params


def search_rows(
    con: sqlite3.Connection,
    q: str,
    unit: list[str] | None = None,
    unit_kerja: list[str] | None = None,
    jabatan: str = "",
    jabatan_nilai: list[str] | None = None,
    status: list[str] | None = None,
    golongan: list[str] | None = None,
    propinsi: list[str] | None = None,
    jenis_jabatan: list[str] | None = None,
    potensi_menjabat: list[str] | None = None,
    potensi_ppk: list[str] | None = None,
    potensi_bendahara: list[str] | None = None,
    potensi_ppspm: list[str] | None = None,
    mode: str = "and",
    limit: int = 50,
) -> list[dict]:
    """Pencarian: q (multi-segmen ';', AND per segmen) + filter, ranking, limit."""
    where, params = build_conditions(
        q, unit, unit_kerja, jabatan, jabatan_nilai, status, golongan,
        propinsi, jenis_jabatan, potensi_menjabat, potensi_ppk,
        potensi_bendahara, potensi_ppspm, mode,
    )
    if not where:
        return []

    fields = data_columns(con)
    select = ", ".join(quote_ident(f) for f in fields)

    # Ranking: NIP eksak -> NIP prefix -> nama depan -> sisanya (urut abjad).
    # Pakai segmen ';' pertama sebagai acuan ranking.
    # Placeholder ? murni (gaya qmark) supaya binding sqlite3 tidak campur gaya.
    # Tanpa q (filter saja) semua baris rank sama - langsung urut nama.
    flat = q.split(";")[0].strip()
    rank = (
        "CASE WHEN ? = '' THEN 0 "
        "WHEN UPPER(\"NIP\") = ? THEN 0 "
        "WHEN UPPER(\"NIP\") LIKE ? ESCAPE '\\' THEN 1 "
        "WHEN UPPER(\"NAMA LENGKAP\") LIKE ? ESCAPE '\\' THEN 2 "
        "ELSE 3 END"
    )
    rank_params = [flat, flat, f"{escape_like(flat)}%", f"{escape_like(flat)}%"]

    sql = (
        f"SELECT id, {select}, {rank} AS _rank FROM pegawai "
        f"WHERE {where} ORDER BY _rank, UPPER(\"NAMA LENGKAP\") LIMIT ?"
    )
    cur = con.execute(sql, rank_params + params + [limit])
    out = []
    for r in cur.fetchall():
        d = dict(r)
        d.pop("_rank", None)
        out.append(d)
    return out


def all_matching_ids(
    con: sqlite3.Connection,
    q: str,
    unit: list[str] | None = None,
    unit_kerja: list[str] | None = None,
    jabatan: str = "",
    jabatan_nilai: list[str] | None = None,
    status: list[str] | None = None,
    golongan: list[str] | None = None,
    propinsi: list[str] | None = None,
    jenis_jabatan: list[str] | None = None,
    potensi_menjabat: list[str] | None = None,
    potensi_ppk: list[str] | None = None,
    potensi_bendahara: list[str] | None = None,
    potensi_ppspm: list[str] | None = None,
    mode: str = "and",
) -> list[int]:
    """SEMUA id yang cocok (tanpa limit baris tampil) - untuk 'tambah semua'."""
    where, params = build_conditions(
        q, unit, unit_kerja, jabatan, jabatan_nilai, status, golongan,
        propinsi, jenis_jabatan, potensi_menjabat, potensi_ppk,
        potensi_bendahara, potensi_ppspm, mode,
    )
    if not where:
        return []
    cur = con.execute(
        f"SELECT id FROM pegawai WHERE {where} LIMIT {MAX_ALL_IDS}", params
    )
    return [r["id"] for r in cur.fetchall()]


def count_matching(
    con: sqlite3.Connection,
    q: str,
    unit: list[str] | None = None,
    unit_kerja: list[str] | None = None,
    jabatan: str = "",
    jabatan_nilai: list[str] | None = None,
    status: list[str] | None = None,
    golongan: list[str] | None = None,
    propinsi: list[str] | None = None,
    jenis_jabatan: list[str] | None = None,
    potensi_menjabat: list[str] | None = None,
    potensi_ppk: list[str] | None = None,
    potensi_bendahara: list[str] | None = None,
    potensi_ppspm: list[str] | None = None,
    mode: str = "and",
) -> int:
    where, params = build_conditions(
        q, unit, unit_kerja, jabatan, jabatan_nilai, status, golongan,
        propinsi, jenis_jabatan, potensi_menjabat, potensi_ppk,
        potensi_bendahara, potensi_ppspm, mode,
    )
    if not where:
        return 0
    return con.execute(
        f"SELECT COUNT(*) FROM pegawai WHERE {where}", params
    ).fetchone()[0]


def api_facets() -> dict:
    """Nilai distinct untuk filter multi-pilihan (tanpa nilai kosong)."""
    con = open_db()
    try:
        out: dict[str, list[str]] = {}
        for col in (
            "UNIT ORGANISASI", "UNIT KERJA / SATUAN KERJA", "NAMA JABATAN",
            "JENIS JABATAN", "STATUS PEGAWAI", "GOLONGAN", "PROPINSI",
            "POTENSI MENJABAT", "POTENSI PPK", "POTENSI BENDAHARA", "POTENSI PPSPM",
        ):
            rows = con.execute(
                f"SELECT DISTINCT {quote_ident(col)} AS v FROM pegawai ORDER BY v"
            ).fetchall()
            out[col] = [r["v"] for r in rows if r["v"]]
        return out
    finally:
        con.close()


def fetch_rows(
    con: sqlite3.Connection, ids: list[int], fields: list[str]
) -> list[dict]:
    if not fields:
        fields = data_columns(con)
    validate_fields(con, fields)
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    select = ", ".join(quote_ident(f) for f in fields)
    cur = con.execute(
        f"SELECT id, {select} FROM pegawai WHERE id IN ({marks})", ids
    )
    by_id = {r["id"]: dict(r) for r in cur.fetchall()}
    # Pertahankan urutan ids (urutan penambahan user).
    return [by_id[i] for i in ids if i in by_id]


def build_export(ids: list[int], fields: list[str]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    con = open_db()
    try:
        rows = fetch_rows(con, ids, fields)
    finally:
        con.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "Terpilih"
    ws.append(fields)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(f, "") for f in fields])

    for i, f in enumerate(fields, start=1):
        width = max(len(str(f)) + 2, 12)
        for r in rows[:200]:  # sampling untuk lebar kolom
            width = min(max(width, len(str(r.get(f, ""))) + 2), 60)
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    import io

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def api_meta() -> dict:
    con = open_db()
    try:
        meta = dict(con.execute("SELECT key, value FROM meta").fetchall())
        return {
            "source": meta.get("source"),
            "generatedAt": meta.get("generated_at"),
            "rows": int(meta.get("rows", 0)),
            "columns": int(meta.get("columns", 0)),
        }
    finally:
        con.close()


def api_columns() -> dict:
    con = open_db()
    try:
        return {"columns": data_columns(con)}
    finally:
        con.close()


def filter_cond(qs: dict[str, list[str]]) -> dict:
    """Ambil parameter filter dari query string.

    Nilai multi boleh diulang (?unit=A&unit=B) -> OR dalam grup.
    `jabatan` (kata kunci berisi) tetap tunggal - kompatibilitas lama.
    """

    def multi(key: str) -> list[str]:
        return [v.strip() for v in qs.get(key, []) if v.strip()]

    return dict(
        unit=multi("unit"),
        unit_kerja=multi("unit_kerja"),
        jabatan=qs.get("jabatan", [""])[0],
        jabatan_nilai=multi("jabatan_nilai"),
        status=multi("status"),
        golongan=multi("golongan"),
        propinsi=multi("propinsi"),
        jenis_jabatan=multi("jenis_jabatan"),
        potensi_menjabat=multi("potensi_menjabat"),
        potensi_ppk=multi("potensi_ppk"),
        potensi_bendahara=multi("potensi_bendahara"),
        potensi_ppspm=multi("potensi_ppspm"),
        mode=qs.get("mode", ["and"])[0].lower(),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "PegawaiServer/1.0"

    # --- helpers -------------------------------------------------------
    def send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(
        self, body: bytes, content_type: str, filename: str | None = None
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        # Jangan log query string (bisa memuat kata kunci pencarian).
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # --- routing -------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/meta":
                self.send_json(api_meta())
            elif path == "/api/columns":
                self.send_json(api_columns())
            elif path == "/api/facets":
                self.send_json(api_facets())
            elif path == "/api/search":
                q = qs.get("q", [""])[0]
                limit = min(
                    int(qs.get("limit", ["50"])[0]), MAX_LIMIT
                )
                cond = filter_cond(qs)
                con = open_db()
                try:
                    rows = search_rows(con, q, limit=limit, **cond)
                    count = count_matching(con, q, **cond)
                    self.send_json({"query": q, "count": count, "rows": rows})
                finally:
                    con.close()
            elif path == "/api/ids":
                # SEMUA id yang cocok (tanpa limit tampil) - dipakai tombol
                # "Tambah semua yang cocok" untuk mengambil satu unit utuh.
                q = qs.get("q", [""])[0]
                cond = filter_cond(qs)
                con = open_db()
                try:
                    ids = all_matching_ids(con, q, **cond)
                    self.send_json({"count": len(ids), "ids": ids})
                finally:
                    con.close()
            elif path == "/api/rows":
                ids = [int(x) for x in parse_csv(qs.get("ids", [""])[0])]
                fields = parse_csv(qs.get("fields", [""])[0])
                ids = parse_ids(ids)
                con = open_db()
                try:
                    self.send_json({"rows": fetch_rows(con, ids, fields)})
                finally:
                    con.close()
            elif path.startswith("/api/"):
                self.send_json({"error": "endpoint tidak dikenal"}, 404)
            else:
                self.serve_static(path)
        except (ValueError, KeyError) as e:
            self.send_json({"error": str(e)}, 400)
        except FileNotFoundError as e:
            self.send_json({"error": str(e)}, 503)
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/export":
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_BODY:
                    self.send_json({"error": "body terlalu besar"}, 413)
                    return
                payload = json.loads(self.rfile.read(length) or b"{}")
                ids = parse_ids(payload.get("ids", []))
                con = open_db()
                try:
                    fields = validate_fields(
                        con, [str(f) for f in payload.get("fields", [])]
                    )
                finally:
                    con.close()
                if not fields:
                    raise ValueError("fields kosong - pilih kolom dulu")
                if not ids:
                    raise ValueError("belum ada pegawai terpilih")
                body = build_export(ids, fields)
                fname = f"pegawai-terpilih-{date.today().isoformat()}.xlsx"
                self.send_bytes(
                    body,
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet",
                    fname,
                )
            else:
                self.send_json({"error": "endpoint tidak dikenal"}, 404)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    # --- static --------------------------------------------------------
    def serve_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        target = (WEB_DIST / path.lstrip("/")).resolve()
        if not target.is_relative_to(WEB_DIST.resolve()):
            self.send_json({"error": "path tidak valid"}, 400)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            hint = (
                "Frontend belum di-build. Jalankan: "
                "cd web && npm.cmd install && npm.cmd run build"
            )
            if path == "/index.html" and not WEB_DIST.exists():
                self.send_json({"error": hint}, 503)
            else:
                self.send_json({"error": "tidak ditemukan"}, 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in (
            "application/javascript",
            "application/json",
        ):
            ctype += "; charset=utf-8"
        self.send_bytes(target.read_bytes(), ctype)


def main() -> None:
    global db_path
    ap = argparse.ArgumentParser(description="Server webapp pegawai")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        sys.exit(
            f"{db_path} tidak ada - jalankan: python scripts/extract_pegawai.py"
        )

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Server:  http://{args.host}:{args.port}")
    print(f"Database: {db_path}")
    if not (WEB_DIST / "index.html").is_file():
        print(
            "Frontend belum di-build -> pakai dev server Vite "
            "(cd web && npm.cmd run dev) atau "
            "(cd web && npm.cmd run build)."
        )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")


if __name__ == "__main__":
    main()
