import math

from core.experience import (Band, assign_band, parse_band_label, parse_experience,
                             parse_interval_notation)

HAYS_LIKE = [Band(l, parse_band_label(l)) for l in ["<2 años", "2-5 años", ">5 años"]]
GAPPED = [Band(l, parse_band_label(l)) for l in ["1-3", "4-7", "8+"]]


def one(text):
    items = parse_experience(text)
    assert len(items) == 1
    return items[0]


def test_no_exact_conversion_of_approximations():
    assert one("almost 4 years").interval.low is None
    assert one("around 5 years").interval.exactness == "aproximado"
    iv = one("over 20 years").interval
    assert iv.low == 20 and not iv.low_incl and iv.high == math.inf


def test_kind_only_when_explicit():
    assert one("5 years").kind == "no especificada"
    assert one("2 years in the role").kind == "puesto"
    items = parse_experience("5 years in SAP, 10 years in total")
    assert {i.kind for i in items} == {"tecnología/especialidad", "total"}


def test_band_assignment_is_unequivocal():
    assert assign_band(parse_interval_notation("3"), HAYS_LIKE)[0] == "2-5 años"
    assert assign_band(parse_interval_notation("[6, 7]"), GAPPED)[0] == "4-7"
    assert assign_band(parse_interval_notation("3,5"), GAPPED)[0] is None      # hueco 3-4
    assert assign_band(parse_interval_notation("[3, 4)"), GAPPED)[0] is None   # cruza
    assert assign_band(parse_interval_notation("~5"), HAYS_LIKE)[0] is None
    assert assign_band(parse_interval_notation("(?, 4)"), HAYS_LIKE)[0] is None
    assert assign_band(None, HAYS_LIKE)[1] == "sin dato de experiencia"


def test_interval_notation_roundtrip():
    for t in ["5", "[6, 7]", "(20, ∞)", "[0, 1)", "(?, 4)", "~5"]:
        assert parse_interval_notation(t).to_text() == t
