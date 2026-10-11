"""OCR local opcional (Tesseract) para guías escaneadas o sin capa de texto.

- Se ejecuta en la máquina local; no envía nada a servicios externos.
- Nota: pytesseract escribe imágenes temporales de la PÁGINA DE LA GUÍA en el
  directorio temporal del sistema y las borra al terminar. Las guías son
  documentos de mercado, no datos de empleados.
"""
from __future__ import annotations

import re


def ocr_available() -> tuple[bool, str]:
    try:
        import pytesseract
        langs = pytesseract.get_languages(config="")
        return True, "+".join(l for l in ("spa", "eng") if l in langs) or "eng"
    except Exception as ex:  # noqa: BLE001
        return False, f"Tesseract no disponible: {type(ex).__name__}"


def ocr_page_words(pdf_bytes: bytes, page_index: int, dpi: int = 300) -> tuple[list[dict], dict]:
    import pypdfium2 as pdfium
    import pytesseract

    ok, lang = ocr_available()
    if not ok:
        raise RuntimeError(lang)
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        img = pdf[page_index].render(scale=dpi / 72).to_pil()
    finally:
        pdf.close()
    info = {"rotacion": 0, "idioma": lang}
    try:
        osd = pytesseract.image_to_osd(img)
        rot = int(re.search(r"Rotate: (\d+)", osd).group(1))
        if rot:
            img = img.rotate(-rot, expand=True)
            info["rotacion"] = rot
    except Exception:  # noqa: BLE001
        info["rotacion"] = "no detectada"
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 6",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        if not str(txt).strip():
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"x0": x, "x1": x + w, "top": y, "bottom": y + h, "text": str(txt),
                      "conf": float(data["conf"][i])})
    info["texto"] = " ".join(w["text"] for w in words)
    return words, info
