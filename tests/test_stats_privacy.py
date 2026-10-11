import math

import pandas as pd

from core.privacy import shareable
from core.stats import describe, gap_pct


def test_describe():
    d = describe(pd.Series([10, 20, 30, 40]))
    assert d["n"] == 4 and d["media"] == 25 and d["mediana"] == 25
    assert math.isclose(d["desv_tipica"], 12.909944, rel_tol=1e-6)
    assert d["p25"] == 17.5 and d["p75"] == 32.5 and d["iqr"] == 15
    assert describe(pd.Series([5]))["desv_tipica"] is None


def test_gap():
    assert gap_pct(100, 90) == 10


def test_suppression_primary_and_complementary():
    df = pd.DataFrame({"grupo": ["G", "G", "H"], "genero_grupo": ["M", "F", "M"],
                       "n": [7, 2, 6], "media": [1.0, 2.0, 3.0], "min": [1.0, 1.0, 1.0]})
    out = shareable(df, "n", 5, ["grupo"])
    assert "min" not in out.columns
    assert out.loc[1, "divulgacion"].startswith("suprimido (n<")
    assert out.loc[0, "divulgacion"] == "suprimido (complementaria)"
    assert pd.isna(out.loc[0, "media"]) and out.loc[2, "media"] == 3.0
