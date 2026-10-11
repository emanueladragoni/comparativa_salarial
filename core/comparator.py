"""Lógica de análisis, independiente de Streamlit.

`SalaryComparator` mantiene el estado de UNA sesión. La interfaz crea una instancia
por sesión y la guarda en st.session_state; nunca se comparte entre sesiones.
Cada registro se identifica internamente por `fila_origen` (fila del CSV), porque
los IDs duplicados se señalan pero no se eliminan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from . import roles as R
from .bands import BandStore, position_vs_band
from .config import (EXPERIENCE_KINDS, MARKET_EXPERIENCE_KIND, POINT_STAT_TYPES,
                     TECH_KEYWORDS, AnalysisSettings)
from .experience import (Band, assign_band, parse_band_label, parse_band_set,
                         parse_experience, parse_interval_notation)
from .market import MarketRegistry
from .money import mixed_format_warning, normalize_money_series, parse_percent
from .privacy import shareable
from .schema import (StructureReport, department_key, drop_fully_empty_rows, role_key,
                     validate_structure)
from .stats import describe, describe_groups, gap_pct, pct_diff

KIND_COL = {"total": "exp_total", "puesto": "exp_puesto",
            "tecnología/especialidad": "exp_tecnologia", "no especificada": "exp_no_especificada"}

LIMITATIONS = [
    "Las diferencias observadas son descriptivas: no prueban por sí solas inequidad ni discriminación.",
    "Faltan factores relevantes: responsabilidades reales, nivel profesional formal, retribución variable, "
    "complementos, antigüedad, desempeño, formación y fecha de incorporación.",
    "Se asume jornada completa para todos los salarios (confirmado); si no fuera así, las comparaciones se distorsionan.",
    "La experiencia procede de texto libre; solo se usa cuando es explícita o ha sido validada.",
    "Con grupos pequeños, medias y medianas son inestables; un solo salario puede mover mucho el resultado.",
    "Las guías de mercado usan metodologías, muestras y estadísticos distintos (media, moda, intervalos); "
    "por eso se muestran por fuente y no se promedian.",
    "El salario interno es fijo bruto anual; si la guía publica total bruto anual, la comparación no es homogénea.",
    "La aplicación no evalúa desempeño ni propone subidas o reducciones salariales.",
]


@dataclass
class LoadResult:
    structure: StructureReport
    money_issues: int = 0
    warnings: list[str] = field(default_factory=list)


class SalaryComparator:
    def __init__(self, settings: AnalysisSettings | None = None):
        self.settings = settings or AnalysisSettings()
        self.raw: pd.DataFrame | None = None
        self.mapping: dict[str, str | None] = {}
        self.employees: pd.DataFrame = pd.DataFrame()
        self.experience_review: pd.DataFrame = pd.DataFrame()
        self.catalog: pd.DataFrame = pd.DataFrame(columns=R.CATALOG_COLUMNS)
        self.market_map: pd.DataFrame = pd.DataFrame(columns=R.MAPPING_COLUMNS)
        self.registry = MarketRegistry()
        self.bands = BandStore()
        self.decisions: list[str] = []
        self.load_result: LoadResult | None = None

    # ------------------------------------------------------------------ datos
    def load_employees(self, df: pd.DataFrame, mapping: dict[str, str | None]) -> LoadResult:
        """Valida y normaliza. Elimina SOLO filas totalmente vacías; los duplicados se señalan."""
        df, n_empty = drop_fully_empty_rows(df)
        rep = validate_structure(df, mapping)
        rep.empty_rows_removed = n_empty
        self.raw, self.mapping = df, mapping          # se conserva el índice original (fila_origen)
        res = LoadResult(rep)
        self.load_result = res
        if not rep.ok:
            self.employees = pd.DataFrame()
            return res
        self.employees = self._normalize(self.raw, mapping, res)
        self.experience_review = self._build_experience_review()
        self.catalog = R.propose_catalog(self.employees["rol"], self.catalog)
        return res

    def _normalize(self, df: pd.DataFrame, m: dict, res: LoadResult) -> pd.DataFrame:
        col = lambda k: df[m[k]] if m.get(k) else pd.Series([""] * len(df), index=df.index)  # noqa: E731
        out = pd.DataFrame({
            "fila_origen": df.index.to_numpy() + 2,
            "id": col("id").astype(str).str.strip(),
            "departamento_original": col("departamento").astype(str),
            "rol_original": col("rol").astype(str),
            "rol": col("rol").map(role_key),
            "genero": col("genero").astype(str).str.strip(),
            "experiencia_texto": col("experiencia").astype(str).str.strip(),
            "tecnologias_texto": col("tecnologias").astype(str).str.strip(),
        })
        out["dep_key"] = out["departamento_original"].map(department_key)
        display = (out.assign(_d=out["departamento_original"].str.strip().str.replace(r"\s+", " ", regex=True))
                   .groupby("dep_key")["_d"].agg(lambda s: s.value_counts().index[0]))
        out["departamento"] = out["dep_key"].map(display)

        sal = normalize_money_series(col("salario"))
        out["salario_original"], out["salario"] = sal["original"], sal["valor"]
        out["salario_estado"], out["salario_nota"] = sal["estado"], sal["nota"]
        out["salario_validado_manual"] = None
        warn = mixed_format_warning(sal)
        if warn:
            res.warnings.append(f"Columna salarial: {warn}")
        bad = sal["estado"].isin(["ambiguo", "inválido"])
        res.money_issues = int(bad.sum())
        if bad.any():
            res.warnings.append(f"{int(bad.sum())} importes ambiguos o inválidos: requieren revisión.")
        if (sal["estado"] == "vacío").any():
            res.warnings.append(f"{int((sal['estado'] == 'vacío').sum())} empleados sin salario en la columna de análisis.")

        if m.get("salario_anterior"):
            prev = normalize_money_series(col("salario_anterior"))
            out["salario_anterior"], out["salario_anterior_estado"] = prev["valor"], prev["estado"]
        if m.get("ipc"):
            ipc = col("ipc").map(parse_percent)
            out["ipc"] = ipc.map(lambda t: t[0])
            out["ipc_estado"] = ipc.map(lambda t: t[1])
        if m.get("salario_anterior") and m.get("ipc"):
            exp = pd.to_numeric(out["salario_anterior"], errors="coerce") * (1 + pd.to_numeric(out["ipc"], errors="coerce"))
            diff = pd.to_numeric(out["salario"], errors="coerce") - exp
            out["coherencia_ipc"] = ""
            mask = diff.abs() > 1
            out.loc[mask, "coherencia_ipc"] = "Salario ≠ anterior × (1+IPC): revisar (no se corrige)"
            if mask.any():
                res.warnings.append(f"{int(mask.sum())} empleados con salario no coincidente con anterior × (1+IPC) "
                                    "(puede deberse a revisiones salariales; solo informativo).")
        return out.reset_index(drop=True)

    def money_review(self) -> pd.DataFrame:
        e = self.employees
        if e.empty:
            return e
        m = e["salario_estado"].isin(["ambiguo", "inválido"]) | e["salario_validado_manual"].notna()
        return e.loc[m, ["fila_origen", "id", "salario_original", "salario_estado", "salario_nota",
                         "salario_validado_manual"]]

    def resolve_money(self, row_key: int, value: float | None, who: str = "") -> None:
        i = self.employees.index[self.employees["fila_origen"] == int(row_key)]
        self.employees.loc[i, "salario_validado_manual"] = value
        self.employees.loc[i, "salario"] = value
        if value is not None:
            self.employees.loc[i, "salario_estado"] = "validado manualmente"
            self.decisions.append(f"Importe de la fila {row_key} validado manualmente por {who or 'usuaria'}.")

    # -------------------------------------------------- experiencia y tecnología
    def _build_experience_review(self) -> pd.DataFrame:
        rows = []
        for r in self.employees.itertuples():
            items = parse_experience(r.experiencia_texto, r.rol)
            rec = {"fila_origen": r.fila_origen, "id": r.id, "rol": r.rol,
                   "experiencia_original": r.experiencia_texto,
                   **{c: "" for c in KIND_COL.values()}, "explicito": "", "validado": False, "notas": ""}
            by_kind: dict[str, list] = {}
            for it in items:
                by_kind.setdefault(it.kind, []).append(it)
            explicit, notes = [], []
            for kind, its in by_kind.items():
                if len(its) > 1:
                    notes.append(f"Varias menciones de tipo «{kind}»: definir manualmente")
                    continue
                it = its[0]
                rec[KIND_COL[kind]] = it.interval.to_text()
                if it.kind_explicit:
                    explicit.append(kind)
                if it.interval.exactness in ("aproximado", "límite inferior desconocido"):
                    notes.append(f"{kind}: {it.interval.exactness}")
            if r.experiencia_texto and not items:
                notes.append("Texto sin cifra de experiencia interpretable")
            rec["explicito"] = ", ".join(explicit)
            rec["notas"] = "; ".join(notes)
            text = " ".join([r.rol_original, r.experiencia_texto, r.tecnologias_texto]).upper()
            rec["tecnologias_propuestas"] = ", ".join(
                k for k in TECH_KEYWORDS if re.search(rf"(?<![A-Z0-9]){re.escape(k)}(?![A-Z0-9])", text))
            rec["tecnologias_validadas"] = ""
            rows.append(rec)
        return pd.DataFrame(rows)

    def update_experience_review(self, edited: pd.DataFrame) -> list[str]:
        """Aplica ediciones; devuelve errores de notación sin aplicar las celdas erróneas."""
        errors = []
        edited = edited.copy()
        for i, r in edited.iterrows():
            for c in KIND_COL.values():
                try:
                    parse_interval_notation(r[c])
                except ValueError as ex:
                    errors.append(f"Fila {r['fila_origen']} (ID {r['id']}): {ex}")
                    edited.at[i, c] = self.experience_review.loc[
                        self.experience_review["fila_origen"] == r["fila_origen"], c].iloc[0]
        self.experience_review = edited.reset_index(drop=True)
        return errors

    def bulk_unspecified_as(self, kind: str, ids: list[str], who: str) -> int:
        """Decisión explícita de la usuaria: tratar la experiencia no especificada como `kind`."""
        er = self.experience_review
        tgt = KIND_COL[kind]
        m = er["id"].isin(ids) & (er["exp_no_especificada"] != "") & (er[tgt] == "")
        er.loc[m, tgt] = er.loc[m, "exp_no_especificada"]
        er.loc[m, "validado"] = True
        self.decisions.append(f"{who or 'Usuaria'} trató la experiencia no especificada como «{kind}» "
                              f"para {int(m.sum())} registros.")
        return int(m.sum())

    def accept_proposed_technologies(self, ids: list[str], who: str) -> None:
        er = self.experience_review
        m = er["id"].isin(ids)
        er.loc[m, "tecnologias_validadas"] = er.loc[m, "tecnologias_propuestas"]
        self.decisions.append(f"{who or 'Usuaria'} aceptó tecnologías propuestas para {int(m.sum())} registros.")

    def experience_of(self, row_key: int, kind: str):
        er = self.experience_review
        if er.empty:
            return None
        row = er[er["fila_origen"] == int(row_key)]
        if row.empty:
            return None
        r = row.iloc[0]
        usable = bool(r["validado"]) or kind in [k.strip() for k in str(r["explicito"]).split(",")]
        if not usable:
            return None
        return parse_interval_notation(r[KIND_COL[kind]])

    def techs_of(self, row_key: int) -> list[str]:
        er = self.experience_review
        if er.empty:
            return []
        row = er[er["fila_origen"] == int(row_key)]
        return [] if row.empty else [t for t in str(row.iloc[0]["tecnologias_validadas"]).split(",") if t.strip()]

    # ------------------------------------------------------- equivalencias
    def set_catalog(self, df: pd.DataFrame) -> list[str]:
        self.catalog = df.reset_index(drop=True)
        return R.validate_catalog(self.catalog)

    def set_market_mapping(self, df: pd.DataFrame) -> None:
        self.market_map = df.reset_index(drop=True)

    def propose_market_mapping(self) -> None:
        self.market_map = R.propose_market_mapping(
            self.catalog, self.registry.active_references(only_validated=False), self.market_map)

    def grouped_employees(self) -> pd.DataFrame:
        e = self.employees.copy()
        if e.empty:
            return e
        res = [R.resolve_group(r.rol, self.techs_of(r.fila_origen), self.catalog) for r in e.itertuples()]
        e["grupo"], e["grupo_estado"] = [x[0] for x in res], [x[1] for x in res]
        info = (self.catalog[self.catalog["estado"] == "confirmada"]
                .drop_duplicates("grupo_equivalente")
                .set_index("grupo_equivalente")[["familia_profesional", "especialidad", "nivel_responsabilidad"]])
        return e.join(info, on="grupo")

    # ------------------------------------------------------ análisis interno
    def _valid(self) -> pd.DataFrame:
        e = self.grouped_employees()
        if e.empty:
            return e
        return e[e["grupo"].notna() & e["salario"].notna()]

    def compare_within_departments(self) -> pd.DataFrame:
        e = self._valid()
        if e.empty:
            return pd.DataFrame()
        return describe_groups(e, ["departamento", "grupo"], "salario")

    def compare_across_departments(self) -> pd.DataFrame:
        e = self._valid()
        if e.empty:
            return pd.DataFrame()
        multi = e.groupby("grupo")["dep_key"].nunique()
        e = e[e["grupo"].isin(multi[multi >= 2].index)]
        if e.empty:
            return pd.DataFrame()
        t = describe_groups(e, ["grupo", "departamento"], "salario")
        overall = e.groupby("grupo")["salario"].median()
        t["mediana_grupo_total"] = t["grupo"].map(overall)
        t["dif_mediana_vs_grupo_pct"] = [pct_diff(m, o) for m, o in zip(t["mediana"], t["mediana_grupo_total"])]
        return t

    def internal_bands(self) -> list[Band]:
        return parse_band_set(self.settings.internal_experience_bands) if self.settings.internal_experience_bands else []

    def compare_by_experience(self) -> pd.DataFrame:
        e = self._valid()
        bands = self.internal_bands()
        if e.empty or not bands:
            return pd.DataFrame()
        kind = self.settings.internal_experience_kind
        labels = []
        for r in e.itertuples():
            lbl, status = assign_band(self.experience_of(r.fila_origen, kind), bands)
            labels.append(lbl or f"no comparable ({status})")
        e = e.assign(banda_experiencia=labels)
        return describe_groups(e, ["grupo", "banda_experiencia"], "salario")

    def gender_analysis(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Solo agregado. Devuelve (estadísticos por género, brechas)."""
        e = self._valid()
        w, m = set(self.settings.women_values), set(self.settings.men_values)
        if e.empty or not w or not m:
            return pd.DataFrame(), pd.DataFrame()
        e = e.assign(genero_grupo=e["genero"].map(lambda g: "Mujeres" if g in w else ("Hombres" if g in m else None)))
        e = e[e["genero_grupo"].notna()]
        overall = describe_groups(e.assign(grupo="(toda la plantilla analizada)"), ["grupo", "genero_grupo"], "salario")
        by_group = describe_groups(e, ["grupo", "genero_grupo"], "salario")
        stats = pd.concat([overall, by_group], ignore_index=True)
        return stats, self._gaps(stats)

    @staticmethod
    def _gaps(stats: pd.DataFrame, threshold: int = 0) -> pd.DataFrame:
        rows = []
        for g, sub in stats.groupby("grupo", sort=False):
            h = sub[sub["genero_grupo"] == "Hombres"]
            mu = sub[sub["genero_grupo"] == "Mujeres"]
            if h.empty or mu.empty:
                continue
            nh, nm = int(h["n"].iloc[0]), int(mu["n"].iloc[0])
            ok = nh >= threshold and nm >= threshold
            rows.append({"grupo": g,
                         "n_hombres": nh if nh >= threshold else f"<{threshold}",
                         "n_mujeres": nm if nm >= threshold else f"<{threshold}",
                         "brecha_media_pct": gap_pct(h["media"].iloc[0], mu["media"].iloc[0]) if ok else None,
                         "brecha_mediana_pct": gap_pct(h["mediana"].iloc[0], mu["mediana"].iloc[0]) if ok else None,
                         "divulgacion": "" if ok else "suprimido (n<umbral)"})
        return pd.DataFrame(rows)

    def gender_shareable(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        stats, _ = self.gender_analysis()
        if stats.empty:
            return stats, stats
        k = self.settings.min_group_size
        return shareable(stats, "n", k, ["grupo"]), self._gaps(stats, k)

    # ------------------------------------------------------------ mercado
    def _refs_for_group(self, group: str) -> pd.DataFrame:
        refs = self.registry.active_references(only_validated=True)
        mp = self.market_map[(self.market_map["estado"] == "confirmada") & (self.market_map["grupo_equivalente"] == group)]
        if refs.empty or mp.empty:
            return refs.iloc[0:0]
        keep = []
        for r in mp.itertuples():
            sel = (refs["fuente"] == r.fuente) & (refs["rol_original"] == r.rol_original)
            if str(r.edicion).strip():
                sel &= refs["edicion"].astype(str) == str(r.edicion)
            keep.append(refs[sel])
        if not keep:
            return refs.iloc[0:0]
        out = pd.concat(keep, ignore_index=True)
        return out.loc[~out.astype(str).duplicated()].reset_index(drop=True)

    def select_compatible_references(self, row_key: int, _grouped: pd.DataFrame | None = None,
                                     _cache: dict | None = None) -> pd.DataFrame:
        """Para un registro (fila de origen): referencias de su grupo con su estado de compatibilidad."""
        e = self.grouped_employees() if _grouped is None else _grouped
        row = e[e["fila_origen"] == int(row_key)]
        if row.empty or pd.isna(row.iloc[0]["grupo"]):
            return pd.DataFrame()
        r = row.iloc[0]
        if _cache is not None:
            if r["grupo"] not in _cache:
                _cache[r["grupo"]] = self._refs_for_group(r["grupo"])
            refs = _cache[r["grupo"]]
        else:
            refs = self._refs_for_group(r["grupo"])
        if refs.empty:
            return pd.DataFrame()
        s = self.settings
        exp_iv = self.experience_of(r["fila_origen"], MARKET_EXPERIENCE_KIND)
        out, seen_nc = [], set()
        for (fuente, rol_m, ubic, stat), g in refs.groupby(
                ["fuente", "rol_original", "ubicacion", "tipo_estadistico"], dropna=False):
            if ubic:
                if s.reference_location is None:
                    key = (fuente, rol_m, "loc")
                    if key not in seen_nc:
                        seen_nc.add(key)
                        out.append({**g.iloc[0].to_dict(), "estado": "ubicación de referencia no seleccionada"})
                    continue
                if ubic != s.reference_location:
                    continue
            elif not s.use_unlocated_references:
                continue
            band_rows = g[g["banda_experiencia_original"] != ""]
            if band_rows.empty:
                candidates = g
            else:
                bands = [Band(l, parse_band_label(l)) for l in band_rows["banda_experiencia_original"].unique()]
                lbl, status = assign_band(exp_iv, bands)
                if lbl is None:
                    st = ("experiencia en el puesto no validada" if exp_iv is None else status)
                    out.append({**g.iloc[0].to_dict(), "banda_experiencia_original": "",
                                "estado": f"no comparable por experiencia: {st}"})
                    continue
                candidates = band_rows[band_rows["banda_experiencia_original"] == lbl]
            for _, ref in candidates.iterrows():
                st = "comparable"
                if not ref["disponible"]:
                    st = "no disponible en la fuente (NA)"
                elif ref["moneda"] != "EUR" or ref["unidad"] != "EUR/año":
                    st = "moneda o unidad no comparable"
                elif ref["concepto_retributivo"] != s.internal_concept:
                    st = ("comparable con advertencia: concepto distinto" if s.allow_concept_mismatch
                          else f"concepto distinto ({s.internal_concept} vs {ref['concepto_retributivo']}): no comparado")
                out.append({**ref.to_dict(), "estado": st})
        return pd.DataFrame(out)

    @staticmethod
    def _compare_one(salary: float, ref: pd.Series) -> dict:
        res = {"referencia": None, "dif_eur": None, "dif_pct": None, "posicion": "",
               "limite_inferior": None, "limite_superior": None, "dif_vs_inferior_eur": None,
               "dif_vs_inferior_pct": None, "dif_vs_superior_eur": None, "dif_vs_superior_pct": None,
               "posicion_en_intervalo_pct": None}
        if ref["tipo_estadistico"] in POINT_STAT_TYPES:
            v = float(ref["valor"])
            res.update(referencia=v, dif_eur=salary - v, dif_pct=pct_diff(salary, v))
            res["posicion"] = "por debajo" if salary < v else ("igual" if salary == v else "por encima")
            return res
        lo = None if pd.isna(ref["valor_min"]) else float(ref["valor_min"])
        hi = None if pd.isna(ref["valor_max"]) else float(ref["valor_max"])
        res.update(limite_inferior=lo, limite_superior=hi)
        if lo is not None:
            res.update(dif_vs_inferior_eur=salary - lo, dif_vs_inferior_pct=pct_diff(salary, lo))
        if hi is not None:
            res.update(dif_vs_superior_eur=salary - hi, dif_vs_superior_pct=pct_diff(salary, hi))
        if lo is not None and hi is not None:
            res["posicion"] = "por debajo" if salary < lo else ("por encima" if salary > hi else "dentro")
            res["posicion_en_intervalo_pct"] = (salary - lo) / (hi - lo) * 100 if hi > lo else None
        elif lo is not None:
            res["posicion"] = ("por debajo del límite inferior" if salary < lo
                               else "por encima del límite inferior (sin límite superior publicado)")
        elif hi is not None:
            res["posicion"] = ("por encima del límite superior" if salary > hi
                               else "por debajo del límite superior (sin límite inferior publicado)")
        return res

    def compare_market_individual(self, ids: list[str] | None = None,
                                  rows_keys: list[int] | None = None) -> pd.DataFrame:
        e = self.grouped_employees()
        if e.empty:
            return pd.DataFrame()
        full = e
        e = e[e["grupo"].notna() & e["salario"].notna()]
        if ids is not None:
            e = e[e["id"].isin([str(i) for i in ids])]
        if rows_keys is not None:
            e = e[e["fila_origen"].isin([int(k) for k in rows_keys])]
        rows, cache = [], {}
        for r in e.itertuples():
            for _, ref in self.select_compatible_references(r.fila_origen, full, cache).iterrows():
                base = {"fila_origen": r.fila_origen, "id": r.id, "departamento": r.departamento,
                        "rol": r.rol, "grupo": r.grupo, "salario": r.salario,
                        "fuente": ref["fuente"], "edicion": ref["edicion"],
                        "version_id": ref.get("version_id", ""), "pagina": ref["pagina"],
                        "rol_mercado": ref["rol_original"], "ubicacion": ref["ubicacion"] or "sin ubicación",
                        "banda_experiencia": ref["banda_experiencia_original"],
                        "tipo_estadistico": ref["tipo_estadistico"],
                        "concepto": ref["concepto_retributivo"], "estado": ref["estado"],
                        "alerta_fuente": ref.get("alerta_revision", "")}
                if ref["estado"].startswith("comparable"):
                    base.update(self._compare_one(float(r.salario), ref))
                rows.append(base)
        return pd.DataFrame(rows)

    def compare_market_aggregated(self, individual: pd.DataFrame | None = None) -> pd.DataFrame:
        ind = self.compare_market_individual() if individual is None else individual
        if ind.empty:
            return pd.DataFrame()
        ind = ind[ind["estado"].str.startswith("comparable")]
        if ind.empty:
            return pd.DataFrame()
        keys = ["grupo", "fuente", "edicion", "rol_mercado", "ubicacion", "banda_experiencia",
                "tipo_estadistico", "concepto"]
        rows = []
        for k, g in ind.groupby(keys, dropna=False):
            d = describe(g["salario"])
            rec = {**dict(zip(keys, k)), "n": d["n"], "media_interna": d["media"],
                   "mediana_interna": d["mediana"]}
            if g["tipo_estadistico"].iloc[0] in POINT_STAT_TYPES:
                ref = g["referencia"].iloc[0]
                rec.update(referencia=ref, dif_mediana_eur=d["mediana"] - ref,
                           dif_mediana_pct=pct_diff(d["mediana"], ref),
                           mediana_dif_individual_pct=float(pd.to_numeric(g["dif_pct"]).median()))
            else:
                rec.update(limite_inferior=g["limite_inferior"].iloc[0], limite_superior=g["limite_superior"].iloc[0])
                for pos in ("por debajo", "dentro", "por encima"):
                    rec[f"n_{pos.replace(' ', '_')}"] = int((g["posicion"] == pos).sum())
            rows.append(rec)
        return pd.DataFrame(rows)

    def market_shareable(self) -> pd.DataFrame:
        agg = self.compare_market_aggregated()
        if agg.empty:
            return agg
        out = shareable(agg, "n", self.settings.min_group_size)
        for c in [c for c in out.columns if c.startswith("n_")]:
            out[c] = out[c].astype("float64")
            out.loc[out["divulgacion"] != "", c] = float("nan")
        return out

    # ----------------------------------------------------- bandas
    def group_info(self, group: str) -> dict:
        conf = self.catalog[(self.catalog["estado"] == "confirmada") & (self.catalog["grupo_equivalente"] == group)]
        if conf.empty:
            return {"grupo_equivalente": group}
        f = conf.iloc[0]
        return {"grupo_equivalente": group, "roles_internos": "; ".join(sorted(set(conf["rol_interno"]))),
                "familia_profesional": f["familia_profesional"], "especialidad": f["especialidad"],
                "nivel_responsabilidad": f["nivel_responsabilidad"]}

    def band_candidates(self, group: str) -> pd.DataFrame:
        refs = self._refs_for_group(group)
        if refs.empty:
            return refs
        info = self.group_info(group)

        def norm(lbl):
            iv = parse_band_label(lbl) if lbl else None
            return iv.to_text() if iv else (lbl or "sin banda")
        return refs.assign(nivel_responsabilidad=info.get("nivel_responsabilidad", ""),
                           banda_experiencia_norm=refs["banda_experiencia_original"].map(norm))

    def groups_without_band_data(self) -> pd.DataFrame:
        groups = sorted(set(self.catalog.loc[self.catalog["estado"] == "confirmada", "grupo_equivalente"]))
        rows = []
        for g in groups:
            faltan = []
            mp = self.market_map[(self.market_map["grupo_equivalente"] == g) & (self.market_map["estado"] == "confirmada")]
            if mp.empty:
                faltan.append("equivalencia de mercado confirmada")
            elif self._refs_for_group(g).empty:
                faltan.append("referencias validadas en versiones activas")
            if faltan:
                rows.append({"grupo_equivalente": g, "estado": "banda pendiente de definición",
                             "faltan": "; ".join(faltan)})
        return pd.DataFrame(rows)

    # ---------------------------------------------------- vista individual
    def individual_view(self, emp_id: str, row_key: int | None = None) -> dict:
        """Uso restringido a personas autorizadas. No incluye el género.
        Si el ID está duplicado, indica `row_key` (fila de origen)."""
        e = self.grouped_employees()
        row = e[e["fila_origen"] == int(row_key)] if row_key is not None else e[e["id"] == str(emp_id)]
        if row.empty:
            raise KeyError("Empleado no encontrado")
        if len(row) > 1:
            raise ValueError("ID duplicado: selecciona la fila de origen.")
        r = row.iloc[0]
        info = {k: r[k] for k in ("id", "departamento", "rol", "grupo", "grupo_estado", "salario",
                                  "salario_original", "salario_estado")}
        info["fila_origen"] = int(r["fila_origen"])
        info["experiencia_puesto"] = (lambda iv: iv.to_text() if iv else "no validada")(
            self.experience_of(r["fila_origen"], MARKET_EXPERIENCE_KIND))
        out = {"empleado": info, "grupo_interno": None, "grupo_departamento": None,
               "mercado": pd.DataFrame(), "bandas": []}
        if pd.isna(r["grupo"]) or pd.isna(r["salario"]):
            return out
        s = float(r["salario"])
        v = self._valid()
        for key, sub in (("grupo_interno", v[v["grupo"] == r["grupo"]]),
                         ("grupo_departamento", v[(v["grupo"] == r["grupo"]) & (v["dep_key"] == r["dep_key"])])):
            d = describe(sub["salario"])
            d["dif_vs_mediana_eur"] = s - d["mediana"] if d["mediana"] is not None else None
            d["dif_vs_mediana_pct"] = pct_diff(s, d["mediana"])
            out[key] = d
        out["mercado"] = self.compare_market_individual(rows_keys=[int(r["fila_origen"])])
        exp_iv = self.experience_of(r["fila_origen"], MARKET_EXPERIENCE_KIND)
        for _, b in self.bands.approved_for(r["grupo"]).iterrows():
            pos = position_vs_band(s, b)
            labels = [x for x in str(b["banda_experiencia"]).split("; ") if x and x != "sin banda"]
            applies = "sí"
            if labels:
                ivs = [Band(l, parse_band_label(l)) for l in labels]
                lbl, st = assign_band(exp_iv, ivs)
                applies = "sí" if lbl else f"no determinada ({st})"
            out["bandas"].append({"band_id": b["band_id"], "version": b["version"],
                                  "banda_experiencia": b["banda_experiencia"], "aplica_por_experiencia": applies,
                                  **pos})
        return out

    # ---------------------------------------------------- advertencias
    def warnings(self) -> list[str]:
        w = []
        if self.load_result:
            w += self.load_result.structure.warnings + self.load_result.warnings
        if not self.experience_review.empty:
            pend = (~self.experience_review["validado"].astype(bool)).sum()
            w.append(f"{int(pend)} registros de experiencia sin validar (solo se usa la experiencia explícita o validada).")
        if len(self.catalog):
            n = int((self.catalog["estado"] != "confirmada").sum())
            if n:
                w.append(f"{n} roles sin equivalencia confirmada: excluidos de los análisis.")
        if not self.settings.allow_concept_mismatch:
            w.append("Las referencias con concepto distinto al salario interno no se comparan "
                     "(activa la opción explícitamente si decides hacerlo).")
        if self.settings.reference_location is None and self.registry.available_locations():
            w.append("No hay ubicación de referencia seleccionada: las referencias con ciudad no se usan.")
        return w + LIMITATIONS


assert set(KIND_COL) == set(EXPERIENCE_KINDS)
