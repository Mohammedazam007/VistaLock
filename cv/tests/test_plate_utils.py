import pytest
from plate_utils import normalize, is_valid_plate, correct_plate, candidates_from_ocr
 
 
def box(x, y, w=200, h=50):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
 
 
def test_normalize():
    assert normalize("ts 09-ab 1234") == "TS09AB1234"
 
 
@pytest.mark.parametrize("plate", ["TS09AB1234", "KA01A1234", "MH12DE1433", "DL1CAB1234", "22BH1234AA"])
def test_valid(plate):
    assert is_valid_plate(plate)
 
 
@pytest.mark.parametrize("plate", ["ZZ09AB1234", "TS09AB12345", "1234567890", "TS09", "TSO9AB1234"])
def test_invalid(plate):
    assert not is_valid_plate(plate)
 
 
@pytest.mark.parametrize("raw,expected,fixes", [
    ("TS09AB1234", "TS09AB1234", 0),
    ("ts 09 ab 1234", "TS09AB1234", 0),
    ("TSO9AB1234", "TS09AB1234", 1),   # O read instead of 0
    ("TS09AB123A", None, None),        # trailing letter is not a digit and A is not confusable
    ("TS09A81234", "TS09AB1234", 1),   # 8 read instead of B
    ("MH12DE143S", "MH12DE1435", 1),   # S read instead of 5
    ("T509AB1234", "TS09AB1234", 1),   # 5 read instead of S in the state code
    ("HELLO WORLD", None, None),
])
def test_correct(raw, expected, fixes):
    result = correct_plate(raw)
    if expected is None:
        assert result is None
    else:
        assert result.plate == expected and result.fixes == fixes
 
 
def test_candidates_single_box():
    found = candidates_from_ocr([(box(0, 0), "TS09AB1234", 0.9), (box(0, 100), "SUNRISE", 0.8)])
    assert list(found) == ["TS09AB1234"]
    assert found["TS09AB1234"] == pytest.approx(0.9)
 
 
def test_candidates_two_line_plate():
    dets = [(box(0, 0), "TS09", 0.9), (box(0, 60), "AB1234", 0.8)]   # top line, bottom line
    assert "TS09AB1234" in candidates_from_ocr(dets)
 
 
def test_candidates_pair_order_is_by_position_not_input_order():
    dets = [(box(0, 60), "AB1234", 0.8), (box(0, 0), "TS09", 0.9)]   # bottom listed first
    assert "TS09AB1234" in candidates_from_ocr(dets)
 
 
def test_fixes_reduce_confidence():
    found = candidates_from_ocr([(box(0, 0), "TSO9AB1234", 0.9)])
    assert found["TS09AB1234"] == pytest.approx(0.81)
 