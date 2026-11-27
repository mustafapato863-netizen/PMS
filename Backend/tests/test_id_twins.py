from utils.id_twins import find_id_twin_rows, normalize_name


def r(key, emp, name="Test  Person", score=90.7, team="t1", month="May"):
    return {"key": key, "employee_id": emp, "name": name, "year": 2026, "month": month, "team_id": team, "level": "Employee", "score": score}


def test_bare_twin_of_prefixed_row_is_excluded():
    assert find_id_twin_rows([r(1, "SGHD70136"), r(2, "70136", name="test person")]) == [2]


def test_different_score_name_team_or_month_is_not_a_twin():
    base = r(1, "SGHD70136")
    assert find_id_twin_rows([base, r(2, "70136", score=80)]) == []
    assert find_id_twin_rows([base, r(2, "70136", name="Other Person")]) == []
    assert find_id_twin_rows([base, r(2, "70136", team="t2")]) == []
    assert find_id_twin_rows([base, r(2, "70136", month="June")]) == []


def test_same_digits_under_other_prefix_letters_never_merge():
    assert find_id_twin_rows([r(1, "SGHA70136"), r(2, "SGHD70136")]) == []


def test_lone_bare_or_lone_prefixed_rows_stay():
    assert find_id_twin_rows([r(1, "70136")]) == []
    assert find_id_twin_rows([r(1, "SGHD70136")]) == []


def test_score_decimal_formats_match():
    assert find_id_twin_rows([r(1, "SGHD1", score="90.70"), r(2, "1", score=90.7)]) == [2]


def test_normalize_name():
    assert normalize_name("  Mohamed   Hussein ") == "mohamed hussein"
