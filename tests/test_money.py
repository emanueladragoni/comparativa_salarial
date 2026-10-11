from core.money import parse_money, parse_percent


def test_formats():
    assert parse_money("52,000.00 €").value == 52000.0
    assert parse_money("67.000,00 €").value == 67000.0
    assert parse_money("1.234.567").value == 1234567
    assert parse_money("38000").value == 38000
    assert parse_money("41200,5").value == 41200.5


def test_ambiguous_and_original_kept():
    p = parse_money("52,000")
    assert p.status == "ambiguo" and p.value is None and p.original == "52,000"
    assert parse_money("52.000").status == "ambiguo"


def test_invalid_and_empty():
    assert parse_money("").status == "vacío"
    assert parse_money("abc").status == "inválido"
    assert parse_money("1,23,4.00").status == "inválido"


def test_percent():
    assert parse_percent("3%") == (0.03, "ok")
    assert parse_percent("3")[1] == "ambiguo"
