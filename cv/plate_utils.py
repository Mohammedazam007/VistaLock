"""Plate text normalization, Indian format validation, and OCR error correction.
 
Pure Python, no ML dependencies, so it is fast to test.
"""
import re
from dataclasses import dataclass
 
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP",
    "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL",
    "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UA", "UK", "UP", "WB",
}
 
# Characters OCR commonly confuses. Used only when the position demands the other class.
_LETTER_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
                    "Z": "2", "S": "5", "B": "8", "G": "6"}
_DIGIT_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G"}
 
_STANDARD_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}$")
_BH_RE = re.compile(r"^\d{2}BH\d{4}[A-Z]{1,2}$")
 
 
def normalize(text: str) -> str:
    """Uppercase and strip everything except A-Z and 0-9."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())
 
 
def is_valid_plate(plate: str) -> bool:
    """Strict Indian format check: standard (state+district+series+number) or BH series."""
    if _BH_RE.match(plate):
        return True
    return bool(_STANDARD_RE.match(plate)) and plate[:2] in STATE_CODES
 
 
def _fix_char(ch: str, kind: str):
    """Return (char, cost) to satisfy `kind` ('L' letter, 'D' digit, or a literal letter), else None."""
    if kind == "L":
        if ch.isalpha():
            return ch, 0
        return (_DIGIT_TO_LETTER[ch], 1) if ch in _DIGIT_TO_LETTER else None
    if kind == "D":
        if ch.isdigit():
            return ch, 0
        return (_LETTER_TO_DIGIT[ch], 1) if ch in _LETTER_TO_DIGIT else None
    # literal letter (used for the BH series)
    if ch == kind:
        return ch, 0
    return (kind, 1) if _DIGIT_TO_LETTER.get(ch) == kind else None
 
 
def _templates(length: int):
    """Yield (template, shape_penalty) for every plausible plate layout of this length."""
    for d in (1, 2):
        for s in (1, 2, 3):
            n = length - 2 - d - s
            if 1 <= n <= 4:
                yield list("L" * 2 + "D" * d + "L" * s + "D" * n), abs(d - 2) + abs(n - 4) + (s == 3)
    if length in (9, 10):
        yield list("DD") + ["B", "H"] + list("DDDD") + list("L" * (length - 8)), 0
 
 
@dataclass(frozen=True)
class Corrected:
    plate: str
    fixes: int  # how many characters were swapped (O->0 etc.)
 
 
def correct_plate(text: str):
    """Turn raw OCR text into a valid Indian plate, fixing position-based confusions.
 
    Returns Corrected or None if no valid plate can be formed.
    """
    s = normalize(text)
    if not 8 <= len(s) <= 11:
        return None
    best = None
    for template, penalty in _templates(len(s)):
        out, cost, ok = [], 0, True
        for ch, kind in zip(s, template):
            fixed = _fix_char(ch, kind)
            if fixed is None:
                ok = False
                break
            out.append(fixed[0])
            cost += fixed[1]
        if not ok:
            continue
        candidate = "".join(out)
        if not is_valid_plate(candidate):
            continue
        key = (cost, penalty)
        if best is None or key < best[0]:
            best = (key, Corrected(candidate, cost))
    return best[1] if best else None
 
 
def _box_info(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(ys) - min(ys)
 
 
def candidates_from_ocr(detections, max_boxes: int = 6):
    """Build plate candidates from EasyOCR-style detections [(bbox, text, conf), ...].
 
    Tries every single box, plus pairs of boxes (two-line bike plates, or plates the OCR
    split in two). Returns {plate: confidence}, keeping the best confidence per plate.
    Confidence is the mean box confidence, reduced 10% per corrected character.
    """
    dets = sorted(detections, key=lambda d: -d[2])[:max_boxes]
    found = {}
 
    def consider(texts, confs):
        result = correct_plate("".join(texts))
        if result is None:
            return
        conf = (sum(confs) / len(confs)) * (0.9 ** result.fixes)
        if conf > found.get(result.plate, 0.0):
            found[result.plate] = conf
 
    for bbox, text, conf in dets:
        consider([text], [conf])
 
    for i in range(len(dets)):
        for j in range(i + 1, len(dets)):
            (b1, t1, c1), (b2, t2, c2) = dets[i], dets[j]
            x1, y1, h1 = _box_info(b1)
            x2, y2, h2 = _box_info(b2)
            stacked = abs(y1 - y2) > 0.6 * (h1 + h2) / 2
            first, second = ((t1, t2) if y1 <= y2 else (t2, t1)) if stacked else \
                            ((t1, t2) if x1 <= x2 else (t2, t1))
            consider([first, second], [c1, c2])
    return found
 