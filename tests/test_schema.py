import pandas as pd

from core.schema import clean_column_names, drop_fully_empty_rows, suggest_mapping, validate_structure


def test_columns_and_empty_rows(raw_employees):
    df = clean_column_names(raw_employees)
    assert "Experiencia" in df.columns
    assert suggest_mapping(list(df.columns))["salario"] == "Salario 2026"
    clean, n = drop_fully_empty_rows(df)
    assert n == 1 and len(clean) == 6


def test_duplicates_flagged_not_removed(comparator):
    rep = comparator.load_result.structure
    assert len(rep.duplicate_ids) == 2
    assert (comparator.employees["id"] == "5").sum() == 2


def test_missing_required_column():
    rep = validate_structure(pd.DataFrame({"a": [1]}), {"id": None})
    assert not rep.ok
