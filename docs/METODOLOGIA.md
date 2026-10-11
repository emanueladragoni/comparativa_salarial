## Decisiones confirmadas

| # | Decisión | Implementación |
|---|---|---|
| 1 | No se usa ubicación de empleados | No se pide columna de ubicación. La ciudad de las guías con desglose geográfico se elige explícitamente; nunca se asigna por defecto. |
| 2 | Jornada completa | No se ajusta por jornada. Si cambiara, las comparaciones se distorsionarían. |
| 3 | Tecnologías propuestas desde el texto | Se proponen a partir de Rol, Experiencia y Tecnologías; solo se usan las «tecnologías validadas». |
| 4 | Departamento = cadena completa | Se unifican solo espacios y mayúsculas para agrupar. |
| 5 | Experiencia sin tipo = «no especificada» | No se usa en comparaciones con mercado hasta su validación. |
| 6 | Guías = experiencia en el puesto | Se compara con la experiencia en el puesto explícita o validada. |
| 7 | Escala de niveles | Sin definir, Junior, Mid, Senior, Lead, Team Coordinator, Team Lead, Head of Department (editable). |
| 8 | Normalización de roles | Solo mayúsculas y espacios. Erratas y variantes quedan como roles distintos hasta que se agrupen y confirmen. |
| 9 | Concepto de las guías | Por defecto, «total bruto anual» (editable por guía). |
| 10 | Guías sin ubicación | Se registran con ubicación vacía («sin ubicación»). |
| 11 | Umbral | n ≥ 5 en informes compartibles, con supresión complementaria y sin mínimos ni máximos. |
| 12 | Dispersión | Desviación típica muestral, IQR (P25–P75 lineal) y CV. |
| 13 | Brecha de género | No ajustada, de media y de mediana, global y por grupo equivalente. |
| 14 | Agregado frente a mercado | Mediana interna frente a la referencia, más la mediana de las diferencias individuales. |
| 15 | Combinación de fuentes | Solo con el mismo concepto, ubicación, nivel y banda de experiencia, y solo valores puntuales. Método elegido explícitamente. La amplitud no tiene valor por defecto. |
| 16 | Aprobación | Se registran nombre, rol (HR / Department Head / Managing Director) y fecha. |
| 17 | Autorización | Contraseña local con hash PBKDF2. En infraestructura corporativa: SSO. |
| 18 | OCR | Tesseract local opcional; si no está disponible, se usa la plantilla CSV. |
| 19 | Pruebas | Datos ficticios mínimos generados en el código de pruebas. |

**Decisión pendiente, visible en la barra lateral:** el salario interno es *fijo* bruto anual y las guías se registran por defecto como *total* bruto anual. Esas referencias **no se comparan** salvo que actives la opción; en ese caso cada resultado queda etiquetado como «comparable con advertencia: concepto distinto».

**Identificación de registros:** cada registro se identifica por su fila en el CSV original (`fila_origen`), porque los IDs duplicados se señalan pero no se eliminan.

## Fórmulas

- **Media:** $\bar{x} = \frac{1}{n}\sum x_i$. **Mediana:** valor central (o promedio de los dos centrales).
- **Desviación típica muestral:** $s=\sqrt{\sum (x_i-\bar{x})^2/(n-1)}$, solo con n ≥ 2. **CV** $= s/\bar{x}\cdot 100$.
- **P25/P75:** interpolación lineal (tipo 7). **IQR** $= P75 - P25$.
- **Diferencia con una referencia puntual** (media, moda, mediana o valor de referencia): € $= s - R$ ; % $= (s-R)/R\cdot100$.
- **Intervalo cerrado [mín, máx]:** posición por debajo / dentro / por encima, diferencias con cada límite y posición en el intervalo $=(s-\text{mín})/(\text{máx}-\text{mín})\cdot100$. **No se usa el punto medio como mediana de mercado.**
- **Intervalo abierto** (p. ej. «>65K»): solo se compara con el límite publicado; no se calcula ninguna posición.
- **Brecha de género:** $(\text{H}-\text{M})/\text{H}\cdot100$, con media y con mediana.
- **Banda interna:** posición respecto a [inferior, superior] y diferencia con el punto medio, en € y en %.

## Experiencia

El texto se interpreta como **intervalo**: «over 20» → (20, ∞), «almost 4» → (?, 4), «6/7» → [6, 7], «around 5» → aproximado. Solo se asigna una banda cuando el intervalo cabe **entero** en una única banda. Si cruza un límite, cae en un hueco entre bandas (p. ej. 3,5 años con bandas 1-3 / 4-7) o es aproximado, queda como «no comparable por experiencia» o «requiere validación».

## Guías de mercado

- Cada dato conserva fuente, edición, página, rol original, ubicación, banda, moneda, unidad, concepto, tipo de estadístico, límites abiertos, disponibilidad (NA) y texto literal.
- Las alertas señalan posibles errores (mínimo mayor que máximo, valores que bajan al subir la experiencia, errores de la capa de texto o baja confianza del OCR) **sin corregirlos**.
- Las referencias se muestran **por fuente y versión**. No se promedian automáticamente.

## Confidencialidad y limitaciones de la arquitectura

- Los datos de empleados viven solo en la memoria de la sesión (`st.session_state`). No se usan las cachés compartidas de Streamlit, ni base de datos, ni APIs externas.
- **No se garantiza un borrado seguro:** «Limpiar sesión» elimina las referencias y fuerza la recolección de memoria, pero Python no sobrescribe la memoria liberada. Pueden quedar restos en RAM, swap, volcados o copias de seguridad del equipo.
- El navegador conserva todo lo que se descarga. Las exportaciones son responsabilidad de quien las realiza.
- Si el proceso falla, podrían aparecer datos en volcados del sistema.
- El OCR (pytesseract) escribe imágenes temporales de las **páginas de la guía** (no de datos de empleados) y las borra después.
- La autorización local es de un único usuario. Para uso multiusuario hacen falta SSO, HTTPS y control de acceso en la infraestructura.
- La aplicación no evalúa el desempeño ni recomienda subidas o reducciones. Las diferencias son descriptivas y no prueban inequidad ni discriminación.
