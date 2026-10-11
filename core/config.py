"""Configuración por defecto y decisiones metodológicas confirmadas por la usuaria.

Cada constante documenta su origen. Ningún valor de este módulo contiene datos de
empleados; puede versionarse en el repositorio sin riesgo de confidencialidad.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Decisiones confirmadas (respuestas 1-19, octubre 2026) -------------------
EMPLOYEE_LOCATION_USED = False          # (1) No se usa ubicación de empleados.
FULL_TIME_ASSUMED = True                # (2) Todos los salarios son de jornada completa.
TECH_TAGS_PROPOSED_FROM_TEXT = True     # (3) Se proponen etiquetas, requieren validación.
DEPARTMENT_KEY = "cadena_completa"      # (4) Se agrupa por la cadena completa.
UNSPECIFIED_EXPERIENCE_KIND = "no especificada"   # (5)
MARKET_EXPERIENCE_KIND = "puesto"       # (6) Las guías miden experiencia en el puesto.
DEFAULT_MARKET_CONCEPT = "total bruto anual"      # (9)
INTERNAL_SALARY_CONCEPT = "fijo bruto anual"      # La columna principal es salario fijo.
DEFAULT_MIN_GROUP_SIZE = 5              # (11) Umbral para informes compartibles.
AUTH_SESSION_MINUTES = 30               # (17) Caducidad de la autorización individual.

RESPONSIBILITY_LEVELS = [               # (7) Escala propuesta, editable en la interfaz.
    "Sin definir", "Junior", "Mid", "Senior", "Lead",
    "Team Coordinator", "Team Lead", "Head of Department",
]

EXPERIENCE_KINDS = ["total", "puesto", "tecnología/especialidad", "no especificada"]

STAT_TYPES = ["media", "moda", "mediana", "valor_referencia", "intervalo"]
POINT_STAT_TYPES = {"media", "moda", "mediana", "valor_referencia"}

CONCEPTS = ["total bruto anual", "fijo bruto anual", "no especificado"]

EQUIVALENCE_STATES = ["propuesta", "confirmada", "rechazada"]
BAND_STATES = ["pendiente de validación", "aprobada", "pendiente de definición", "descartada"]

# Ciudades que el extractor reconoce como cabeceras. Ampliable sin tocar la lógica.
KNOWN_LOCATIONS = [
    "Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao", "Málaga", "Malaga",
    "Zaragoza", "Alicante", "Murcia", "Palma", "Las Palmas", "Valladolid",
    "Vigo", "A Coruña", "Coruña", "Oviedo", "Pamplona", "San Sebastián",
    "Granada", "Santander", "Tenerife", "Canarias", "Galicia", "Asturias",
    "País Vasco", "Andalucía", "Cataluña", "Remoto", "Nacional", "España",
]

# Etiquetas tecnológicas propuestas a partir del texto (siempre requieren validación).
TECH_KEYWORDS = [
    "SAP", "ABAP", "S/4HANA", "HANA", "FIORI", "BASIS", "ARIBA", "SUCCESSFACTORS",
    "SSFF", "BTP", "CPI", "SALESFORCE", "SERVICENOW", "JAVA", "PYTHON", ".NET",
    "C#", "JAVASCRIPT", "TYPESCRIPT", "ANGULAR", "REACT", "VUE", "NODE", "AZURE",
    "AWS", "GCP", "KUBERNETES", "DOCKER", "LINUX", "WINDOWS", "SQL", "POWER BI",
    "TABLEAU", "DATABRICKS", "SPARK", "SAP BW", "QLIK", "INTUNE", "M365",
    "OFFICE 365", "CITRIX", "VMWARE", "CISCO", "FORTINET", "SIEM", "SOC",
    "DEVOPS", "TERRAFORM", "ANSIBLE", "JIRA", "SHAREPOINT", "POWER APPS",
    "POWER AUTOMATE", "RPA", "UIPATH", "IOS", "ANDROID", "FLUTTER", "PHP",
    "GO", "KOTLIN", "SCALA", "MDM", "CRM", "ERP",
]


@dataclass
class AnalysisSettings:
    """Ajustes de una sesión; viven en memoria dentro de st.session_state."""
    min_group_size: int = DEFAULT_MIN_GROUP_SIZE
    internal_concept: str = INTERNAL_SALARY_CONCEPT
    allow_concept_mismatch: bool = False        # Requiere decisión explícita.
    reference_location: str | None = None       # None = no seleccionada.
    use_unlocated_references: bool = True       # Michael Page (sin ubicación), confirmado.
    women_values: list[str] = field(default_factory=list)
    men_values: list[str] = field(default_factory=list)
    internal_experience_bands: str = ""         # p. ej. "<2; 2-5; >5" (lo define la usuaria).
    internal_experience_kind: str = MARKET_EXPERIENCE_KIND
