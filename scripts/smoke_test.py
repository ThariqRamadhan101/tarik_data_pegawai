"""Smoke test API server (tanpa menampilkan isi baris - PII).

Jalankan server dulu:  python server/server.py
Lalu:                 python scripts/smoke_test.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"


def get(path: str):
    return urllib.request.urlopen(BASE + path, timeout=30)


def get_json(path: str) -> dict:
    with get(path) as r:
        return json.load(r)


def main() -> int:
    fails: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'OK ' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail else ""))
        if not ok:
            fails.append(name)

    try:
        with get("/") as r:
            check("GET / (index)", r.status == 200, r.headers.get("Content-Type", ""))
    except Exception as e:  # noqa: BLE001
        check("GET / (index)", False, str(e))

    try:
        meta = get_json("/api/meta")
        check(
            "/api/meta",
            meta.get("rows", 0) > 0 and bool(meta.get("source")),
            f"rows={meta.get('rows')}",
        )
        cols = get_json("/api/columns")["columns"]
        check("/api/columns", len(cols) >= 50, f"{len(cols)} kolom")
        check(
            "/api/columns tanpa kolom sistem",
            "id" not in cols and "finder_text" not in cols,
        )

        # Facet untuk dropdown filter.
        facets = get_json("/api/facets")
        check(
            "/api/facets unit organisasi",
            len(facets["UNIT ORGANISASI"]) >= 10
            and "" not in facets["UNIT ORGANISASI"],
            f"{len(facets['UNIT ORGANISASI'])} nilai",
        )
        check(
            "/api/facets unit kerja / satuan kerja",
            len(facets["UNIT KERJA / SATUAN KERJA"]) >= 250,
            f"{len(facets['UNIT KERJA / SATUAN KERJA'])} nilai",
        )
        # Facet baru untuk filter multi-pilihan.
        for key, minima in [
            ("NAMA JABATAN", 500),
            ("JENIS JABATAN", 5),
            ("STATUS PEGAWAI", 2),
            ("GOLONGAN", 10),
            ("PROPINSI", 20),
            ("POTENSI MENJABAT", 2),
            ("POTENSI PPK", 2),
            ("POTENSI BENDAHARA", 2),
            ("POTENSI PPSPM", 2),
        ]:
            check(
                "/api/facets " + key.lower(),
                len(facets.get(key, [])) >= minima,
                f"{len(facets.get(key, []))} nilai",
            )

        check(
            "/api/facets teknik ps",
            set(facets.get("TEKNIK PS", [])) == {"ya", "tidak"},
            f"{facets.get('TEKNIK PS')}",
        )
        check(
            "/api/facets jenis jabatan2",
            "JABATAN PERBENDAHARAAN" in facets.get("JENIS JABATAN2", []),
            f"{len(facets.get('JENIS JABATAN2', []))} nilai",
        )

        # Facet selektif (lazy-load dari FilterBar): hanya kolom yang diminta.
        one = get_json(
            "/api/facets?column=" + urllib.parse.quote("UNIT ORGANISASI")
        )
        check(
            "/api/facets satu kolom (lazy)",
            list(one.keys()) == ["UNIT ORGANISASI"],
            f"{len(one)} kolom",
        )

        # Kolom enrichment (skrip enrich_pegawai.py) tersedia di API.
        enrich_cols = [
            "UNIT KERJA / SATUAN KERJA", "POTENSI MENJABAT",
            "SERTIFIKAT PNT", "SERTIFIKAT SNT", "SERTIFIKAT BNT",
            "SERTIFIKAT PBJ", "SERTIFIKAT PPK",
            "POTENSI PPK", "POTENSI BENDAHARA", "POTENSI PPSPM",
            "PROPINSI2", "TEKNIK PS", "JENIS JABATAN2",
            "URUTAN UNIT ORGANISASI", "URUTAN UNKER / SATKER PS",
        ]
        check(
            "/api/columns memuat kolom enrichment",
            all(c in cols for c in enrich_cols),
            f"{sum(c in cols for c in enrich_cols)}/{len(enrich_cols)} kolom",
        )

        UNIT = "Direktorat Jenderal Sumber Daya Air"

        # Filter unit saja (tanpa kata kunci) harus tetap menghasilkan baris.
        r = get_json("/api/search?unit=" + urllib.parse.quote(UNIT))
        check(
            "/api/search filter unit saja",
            0 < len(r["rows"]) <= 50
            and all(row["UNIT ORGANISASI"] == UNIT for row in r["rows"]),
            f"{len(r['rows'])} hasil",
        )

        # Filter jabatan saja (berisi kata).
        r = get_json("/api/search?jabatan=perencana")
        check(
            "/api/search filter jabatan saja",
            0 < len(r["rows"])
            and all(
                "PERENCANA" in (row["NAMA JABATAN"] or "").upper()
                for row in r["rows"]
            ),
            f"{len(r['rows'])} hasil",
        )

        # AND: tiap baris memenuhi unit DAN jabatan.
        r_and = get_json(
            "/api/search?unit="
            + urllib.parse.quote(UNIT)
            + "&jabatan=perencana&mode=and"
        )
        check(
            "/api/search unit+jabatan AND",
            bool(r_and["rows"])
            and all(
                row["UNIT ORGANISASI"] == UNIT
                and "PERENCANA" in (row["NAMA JABATAN"] or "").upper()
                for row in r_and["rows"]
            ),
            f"{len(r_and['rows'])} hasil",
        )

        # OR: tiap baris memenuhi unit ATAU jabatan (dan hasilnya >= AND).
        r_or = get_json(
            "/api/search?unit="
            + urllib.parse.quote(UNIT)
            + "&jabatan=perencana&mode=or"
        )
        check(
            "/api/search unit+jabatan OR",
            bool(r_or["rows"])
            and all(
                row["UNIT ORGANISASI"] == UNIT
                or "PERENCANA" in (row["NAMA JABATAN"] or "").upper()
                for row in r_or["rows"]
            )
            and len(r_or["rows"]) >= len(r_and["rows"]),
            f"{len(r_or['rows'])} hasil",
        )

        # Tanpa kondisi apa pun -> kosong (bukan dump 37k baris).
        check("/api/search tanpa kondisi", get_json("/api/search?q=")["rows"] == [])

        # Respons search menyertakan total `count` (bisa ribuan, tampil terbatas).
        r = get_json("/api/search?q=ag&limit=5")
        check(
            "/api/search menyertakan count",
            r.get("count", 0) >= len(r["rows"]) > 0,
            f"count={r.get('count')}, rows={len(r['rows'])}",
        )

        # Filter multi-value: unit diulang -> OR dalam grup.
        unor2 = facets["UNIT ORGANISASI"][:2]
        if len(unor2) == 2:
            r = get_json(
                "/api/search?"
                + urllib.parse.urlencode([("unit", unor2[0]), ("unit", unor2[1])])
            )
            check(
                "/api/search unit multi-value",
                bool(r["rows"])
                and all(row["UNIT ORGANISASI"] in unor2 for row in r["rows"]),
                f"{r['count']} cocok",
            )

        # jabatan_nilai: pencocokan nilai persis NAMA JABATAN.
        nv = facets["NAMA JABATAN"][0]
        r = get_json("/api/search?" + urllib.parse.urlencode({"jabatan_nilai": nv}))
        check(
            "/api/search jabatan_nilai persis",
            bool(r["rows"])
            and all(row["NAMA JABATAN"] == nv for row in r["rows"]),
            f"{r['count']} cocok",
        )

        # Filter status pegawai / golongan / propinsi / jenis jabatan / potensi (nilai persis).
        for key, col in [
            ("status", "STATUS PEGAWAI"),
            ("golongan", "GOLONGAN"),
            ("propinsi", "PROPINSI"),
            ("jenis_jabatan", "JENIS JABATAN"),
            ("potensi_menjabat", "POTENSI MENJABAT"),
            ("potensi_ppk", "POTENSI PPK"),
            ("potensi_bendahara", "POTENSI BENDAHARA"),
            ("potensi_ppspm", "POTENSI PPSPM"),
        ]:
            v = facets[col][0]
            r = get_json("/api/search?" + urllib.parse.urlencode({key: v}))
            check(
                "/api/search " + key,
                bool(r["rows"]) and all(row[col] == v for row in r["rows"]),
                f"{r['count']} cocok",
            )

        # Nilai enrichment konsisten di hasil search (kolom unit/satuan kerja
        # kosong hanya bila UNIT KERJA sumber memang kosong).
        r = get_json("/api/search?q=ag")
        check(
            "/api/search enrichment konsisten",
            bool(r["rows"])
            and all(
                row["UNIT KERJA / SATUAN KERJA"] or not row["UNIT KERJA"]
                for row in r["rows"]
            )
            and all(
                row["POTENSI MENJABAT"] in ("", "ya", "tidak") for row in r["rows"]
            )
            and all(row["TEKNIK PS"] in ("ya", "tidak") for row in r["rows"])
            and all(
                row["JENIS JABATAN2"] == "JABATAN PERBENDAHARAAN"
                if any(
                    k in (row["JABATAN RANGKAP"] or "").upper()
                    for k in ("KEPALA", "BENDAHARA", "PEJABAT")
                )
                else row["JENIS JABATAN2"] == (row["JENIS JABATAN"] or "").strip()
                for row in r["rows"]
            ),
            f"{len(r['rows'])} baris",
        )

        # Filter kolom enrichment baru (nilai persis) harus bekerja.
        for col, val in [("TEKNIK PS", "ya"),
                         ("JENIS JABATAN2", "JABATAN PERBENDAHARAAN")]:
            r = get_json("/api/search?" + urllib.parse.urlencode({col: val}))
            check(
                "/api/search " + col,
                r["count"] > 0
                and all(row[col] == val for row in r["rows"]),
                f"{r['count']} cocok",
            )

        # Skala besar: satu unit utuh (mis. Bina Marga, ~14k baris) lewat /api/ids.
        BIG = "Direktorat Jenderal Bina Marga"
        big_url = "/api/search?q=&unit=" + urllib.parse.quote(BIG) + "&limit=200"
        r_big = get_json(big_url)
        ids_all = get_json("/api/ids?q=&unit=" + urllib.parse.quote(BIG))
        check(
            "/api/ids satu unit utuh (tanpa limit tampil)",
            ids_all["count"] == r_big["count"] == len(ids_all["ids"])
            and len(ids_all["ids"]) > 200
            and all(isinstance(n, int) for n in ids_all["ids"]),
            f"{ids_all['count']} ids",
        )

        # /api/rows di-chunk 500 seperti klien (URL tetap pendek).
        got = 0
        for i in range(0, len(ids_all["ids"]), 500):
            part = ids_all["ids"][i : i + 500]
            qq = urllib.parse.urlencode(
                {"ids": ",".join(map(str, part)), "fields": "NAMA LENGKAP,NIP"}
            )
            got += len(get_json("/api/rows?" + qq)["rows"])
        check("/api/rows chunked ~14k ids", got == len(ids_all["ids"]), f"{got} baris")

        # Export satu unit utuh tetap valid.
        body = json.dumps(
            {"ids": ids_all["ids"], "fields": ["NAMA LENGKAP", "NIP", "UNIT KERJA"]}
        ).encode()
        req = urllib.request.Request(
            BASE + "/api/export",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            check(
                "/api/export satu unit utuh",
                resp.status == 200 and data[:2] == b"PK" and len(data) > 100_000,
                f"{len(data) // 1024} KB",
            )

        # Pencarian multi-keyword AND + karakter spesial LIKE.
        r = get_json("/api/search?q=" + urllib.parse.quote("balai pelaksanaan jalan"))
        check("/api/search multi-keyword", 0 < len(r["rows"]) <= 50, f"{len(r['rows'])} hasil")
        r = get_json("/api/search?q=" + urllib.parse.quote("zzzz-tidak-ada"))
        check("/api/search nihil", r["rows"] == [])
        r = get_json("/api/search?q=" + urllib.parse.quote("100% _x"))
        check("/api/search karakter spesial", isinstance(r["rows"], list))

        # Query multi ';' -> OR antar segmen (AND tetap di dalam segmen):
        # segmen nihil tak mengubah hasil, gabungan >= tiap segmen sendiri.
        c_ag = get_json("/api/search?q=ag")["count"]
        c_balai = get_json("/api/search?q=balai")["count"]
        c_nihil_seg = get_json(
            "/api/search?q=" + urllib.parse.quote("zzzz-tidak-ada;ag")
        )["count"]
        c_union = get_json(
            "/api/search?q=" + urllib.parse.quote("ag;balai")
        )["count"]
        check(
            "/api/search query multi ; (OR antar segmen)",
            c_ag > 0
            and c_nihil_seg == c_ag
            and c_union >= max(c_ag, c_balai),
            f"count={c_union} (ag={c_ag}, balai={c_balai})",
        )

        # /api/rows mempertahankan urutan ids.
        ids = [row["id"] for row in get_json("/api/search?q=ag")["rows"][:3]]
        q = urllib.parse.urlencode(
            {"ids": ",".join(map(str, ids)), "fields": "NAMA LENGKAP,NIP,UNIT KERJA"}
        )
        rows = get_json("/api/rows?" + q)["rows"]
        check(
            "/api/rows urut sesuai ids",
            [row["id"] for row in rows] == ids,
            f"{len(rows)} baris",
        )

        # Export xlsx valid.
        body = json.dumps(
            {"ids": ids, "fields": ["NAMA LENGKAP", "NIP", "UNIT KERJA"]}
        ).encode()
        req = urllib.request.Request(
            BASE + "/api/export",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            check(
                "/api/export xlsx",
                resp.status == 200 and data[:2] == b"PK",
                f"{len(data)} bytes",
            )

        # Request valid ditolak dengan 400.
        for name, path in [
            ("400 ids bukan angka", "/api/rows?ids=abc&fields=NIP"),
            ("400 kolom tak dikenal", "/api/rows?ids=1&fields=bukan_kolom"),
        ]:
            try:
                get(path)
                check(name, False, "seharusnya 400")
            except urllib.error.HTTPError as e:
                check(name, e.code == 400, str(e.code))
    except Exception as e:  # noqa: BLE001
        check("api reachable", False, str(e))

    print(("SEMUA LULUS" if not fails else f"GAGAL: {', '.join(fails)}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
