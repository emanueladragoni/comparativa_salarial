"""Extracción de tablas salariales de guías PDF a formato largo de referencias.

No asume una estructura común entre guías. Por página:
  1. Si hay capa de texto -> palabras con coordenadas (pdfplumber).
  2. Si no la hay y OCR local está disponible -> palabras por OCR (Tesseract).
  3. Si no se obtiene nada fiable -> la página se marca para carga manual (plantilla CSV).
Todo el resultado queda en estado «pendiente» hasta su validación en la vista previa.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from core.market import MARKET_COLUMNS
from . import ocr_local
from .parsers import lines_to_records, page_hints, parse_market_cell, words_to_lines

MIN_TEXT_CHARS = 80


@dataclass
class ExtractionResult:
    records: pd.DataFrame
    pages: pd.DataFrame
    notes: list[str] = field(default_factory=list)


def _page_range(spec: str | None, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    idx: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-")
            idx.update(range(int(a) - 1, min(int(b), n)))
        elif part:
            idx.add(int(part) - 1)
    return sorted(i for i in idx if 0 <= i < n)


def extract_pdf(data: bytes, fuente: str, edicion: str, concepto: str, stat_default: str,
                pages: str | None = None, use_ocr: bool = True,
                tipo_experiencia: str = "puesto", progress=None) -> ExtractionResult:
    import pdfplumber

    rows, page_rows, notes = [], [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        targets = _page_range(pages, len(pdf.pages))
        for k, i in enumerate(targets):
            if progress:
                progress((k + 1) / max(len(targets), 1), f"Página {i + 1}")
            page = pdf.pages[i]
            method, info = "texto", {}
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            text = " ".join(w["text"] for w in words)
            if len(text) < MIN_TEXT_CHARS:
                ok, _ = ocr_local.ocr_available()
                if use_ocr and ok:
                    try:
                        words, info = ocr_local.ocr_page_words(data, i)
                        text, method = info.get("texto", ""), "OCR"
                    except Exception as ex:  # noqa: BLE001
                        words, method = [], f"OCR fallido ({type(ex).__name__})"
                else:
                    words, method = [], "sin capa de texto; OCR no disponible/desactivado"
            hints = page_hints(text)
            recs, pnotes = lines_to_records(words_to_lines(words), i + 1, hints["k_hint"]) if words else ([], [])
            for r in recs:
                cv = parse_market_cell(r.cell_text, hints["k_hint"])
                is_interval = cv.kind in ("intervalo", "abierto_superior", "abierto_inferior")
                alerts = [f"Extraído automáticamente ({method}): validar"] + r.alerts + cv.alerts
                if not is_interval and not stat_default:
                    alerts.append("Tipo de estadístico sin confirmar")
                rows.append({
                    "fuente": fuente, "edicion": edicion, "pagina": str(r.pagina),
                    "rol_original": r.rol_original, "categoria_fuente": r.categoria,
                    "ubicacion": r.ubicacion, "banda_experiencia_original": r.banda,
                    "tipo_experiencia": tipo_experiencia, "moneda": "EUR", "unidad": "EUR/año",
                    "concepto_retributivo": concepto,
                    "tipo_estadistico": "intervalo" if is_interval else (stat_default or ""),
                    "valor": cv.valor, "valor_min": cv.valor_min, "valor_max": cv.valor_max,
                    "limite_abierto": {"abierto_superior": "superior", "abierto_inferior": "inferior"}.get(cv.kind, ""),
                    "disponible": cv.kind != "na", "valor_original": r.cell_text,
                    "variable_original": r.variable, "notas_fuente": "",
                    "alerta_revision": " | ".join(dict.fromkeys(alerts)), "estado_validacion": "pendiente",
                })
            reliable = len(recs) > 0
            page_rows.append({"pagina": i + 1, "metodo": method, "registros": len(recs),
                              "estadistico_detectado": hints["stat_hint"] or "",
                              "rotacion_ocr": info.get("rotacion", ""),
                              "resultado": "revisar vista previa" if reliable
                              else "sin tabla fiable: usar plantilla CSV si contiene datos"})
            notes += [f"p.{i + 1}: {n}" for n in pnotes]
    df = pd.DataFrame(rows, columns=MARKET_COLUMNS)
    df = _attach_page_notes(df, notes)
    return ExtractionResult(df, pd.DataFrame(page_rows), notes)


def _attach_page_notes(df: pd.DataFrame, notes: list[str]) -> pd.DataFrame:
    by_page: dict[str, list[str]] = {}
    for n in notes:
        p, _, txt = n.partition(": ")
        if txt.startswith(("*", "(1)", "(2)", "Nota")):
            by_page.setdefault(p[2:], []).append(txt)
    if by_page and len(df):
        df["notas_fuente"] = df["pagina"].map(lambda p: " / ".join(by_page.get(p, [])))
    return df
