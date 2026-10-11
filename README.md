# Aplicación de análisis salarial (v1, ejecución local)

Analiza la equidad interna, compara con guías de mercado (por fuente, sin promediarlas) y gestiona bandas salariales versionadas. Los datos de empleados se procesan **solo en memoria** y por sesión.

## Estructura

```
app.py                  Interfaz Streamlit (navegación)
ui/                     Páginas de la interfaz (sin lógica de negocio)
core/
  config.py             Decisiones confirmadas y ajustes
  schema.py             Lectura del CSV, mapeo de columnas, validación estructural
  money.py              Formatos monetarios (conserva el original y marca ambigüedades)
  experience.py         Experiencia como intervalos y asignación inequívoca de bandas
  roles.py              Equivalencias internas y correspondencias de mercado
  market.py             Esquema y validación de referencias, versiones
  stats.py              Estadísticos y fórmulas
  privacy.py            Umbral mínimo, supresión complementaria, avisos de exportación
  bands.py              Propuestas de bandas, aprobación y versionado inmutable
  comparator.py         Clase SalaryComparator
  auth.py / session.py  Autorización local, aislamiento y limpieza de la sesión
extraction/
  pdf_extractor.py      Orquestador (capa de texto → OCR → carga manual)
  parsers.py            Interpretación de celdas y cabeceras
  ocr_local.py          Tesseract local (opcional)
templates/              Plantillas CSV (mercado, equivalencias, correspondencias, bandas)
tests/                  Pruebas (datos ficticios mínimos)
docs/METODOLOGIA.md     Fórmulas, decisiones y limitaciones
scripts/hash_password.py Genera el hash de la contraseña
```

## Instalación

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

**OCR opcional** (necesario para guías sin capa de texto): instala Tesseract con el paquete de idioma español (`spa`). Si no está disponible, esas guías se cargan con `templates/plantilla_referencias_mercado.csv`.

## Configurar el acceso a la vista individual

```bash
python scripts/hash_password.py          # genera el hash (mínimo 12 caracteres)
```

Guárdalo **fuera del repositorio** de una de estas formas:
- Variable de entorno: `SALARY_APP_PASSWORD_HASH="pbkdf2_sha256$..."`
- Archivo `.streamlit/secrets.toml` (incluido en `.gitignore`):
  ```toml
  [auth]
  password_hash = "pbkdf2_sha256$..."
  ```

## Ejecución

```bash
streamlit run app.py
```

La aplicación solo escucha en `localhost` (ver `.streamlit/config.toml`), sin telemetría y sin mostrar trazas de error en el navegador.

## Flujo de una revisión salarial

1. **Datos:** carga el CSV, revisa la asignación de columnas (puedes elegir otra columna salarial), valida y resuelve los importes ambiguos.
2. **Experiencia:** valida la experiencia en el puesto y las tecnologías.
3. **Equivalencias:** agrupa y confirma los roles; mapea los roles de mercado; descarga ambas tablas para la próxima revisión.
4. **Guías:** extrae los PDF o carga CSV validados, registra las versiones, activa las que correspondan y elige la ciudad de referencia.
5. **Análisis agregado:** los informes compartibles aplican el umbral.
6. **Vista individual:** requiere acceso autorizado.
7. **Bandas:** propón, edita, aprueba y exporta; impórtalas en la siguiente revisión.
8. **Limpiar sesión** al terminar.

Las referencias, equivalencias y bandas **no contienen datos personales**: guárdalas en el repositorio documental de RR. HH. (no en el del código) para reutilizarlas.

## Pruebas

```bash
python -m pytest -q
```

Cubren validación y normalización, experiencia y bandas, cálculos, control de divulgación, extracción con un PDF ficticio, versionado de bandas y aislamiento de sesiones (incluidas comprobaciones de que no hay cachés compartidas, escrituras en disco, llamadas de red ni registros con datos).
