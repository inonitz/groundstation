"""Hebrew -> English target lexicon: a deterministic safety net UNDER Gemma's target_en (live 2026-09-09 block B:
"כמה מגירות" -> Gemma wrote target_en "cabin", "כמה שידות" -> "desks"; SAM3 then counted 0 in front of the drawers).
Only fixes a CLEAR miss: when the Hebrew names a lexicon noun and Gemma's target contains none of that noun's
English aliases, the first lexicon noun replaces the target. Attribute phrases Gemma got right ("red car" for
"מכונית אדומה") are untouched because "car" is an alias hit. Extend as cases appear; keep it nouns only."""
import re

HE2EN = {
    # room / furniture
    "ארון": "cabinet", "ארונות": "cabinet", "מגירה": "drawer", "מגירות": "drawer", "שידה": "dresser", "שידות": "dresser",
    "מדף": "shelf", "מדפים": "shelf", "מסך": "screen", "מסכים": "screen", "טלוויזיה": "television", "טלוויזיות": "television",
    "חלון": "window", "חלונות": "window", "דלת": "door", "דלתות": "door", "כיסא": "chair", "כיסאות": "chair", "כסא": "chair",
    "כסאות": "chair", "שולחן": "table", "שולחנות": "table", "ספה": "sofa", "ספות": "sofa", "מיטה": "bed", "מיטות": "bed",
    "מנורה": "lamp", "מנורות": "lamp", "מחשב": "computer", "מחשבים": "computer", "מקלדת": "keyboard", "טלפון": "phone",
    "בקבוק": "bottle", "בקבוקים": "bottle", "כוס": "cup", "כוסות": "cup", "תיק": "bag", "תיקים": "bag", "גיטרה": "guitar",
    "גיטרות": "guitar", "ספר": "book", "ספרים": "book", "מראה": "mirror", "שטיח": "rug", "וילון": "curtain", "וילונות": "curtain",
    "מקרר": "refrigerator", "תנור": "oven", "כיור": "sink", "מזגן": "air conditioner", "מצלמה": "camera", "מצלמות": "camera",
    # people / animals
    "אדם": "person", "בנאדם": "person", "בן אדם": "person", "אנשים": "person", "איש": "man", "אישה": "woman", "אשה": "woman",
    "ילד": "child", "ילדים": "child", "ילדה": "girl", "חייל": "soldier", "חיילים": "soldier", "כלב": "dog", "כלבים": "dog",
    "חתול": "cat", "חתולים": "cat",
    # outdoors / vehicles
    "רכב": "car", "רכבים": "car", "מכונית": "car", "מכוניות": "car", "משאית": "truck", "משאיות": "truck", "אוטובוס": "bus",
    "אופניים": "bicycle", "אופנוע": "motorcycle", "רחפן": "drone", "רחפנים": "drone", "עץ": "tree", "עצים": "tree",
    "בניין": "building", "בניינים": "building", "בית": "house", "בתים": "house", "גג": "roof", "גגות": "roof", "מדרגות": "stairs",
    "מרפסת": "balcony", "מרפסות": "balcony", "גדר": "fence", "שער": "gate", "תמרור": "sign", "שלט": "sign", "כביש": "road",
    "נשק": "weapon", "רובה": "rifle", "רובים": "rifle", "אנטנה": "antenna", "אנטנות": "antenna",
}
EN_ALIASES = {
    "cabinet": ["cabinet", "cupboard", "closet", "wardrobe", "hutch"], "drawer": ["drawer", "dresser"],
    "dresser": ["dresser", "drawer", "chest"], "screen": ["screen", "monitor", "display", "tv", "television"],
    "television": ["television", "tv", "screen"], "person": ["person", "people", "man", "woman", "human", "guy", "soldier"],
    "man": ["man", "person", "guy"], "woman": ["woman", "person", "lady"], "child": ["child", "kid", "boy", "girl"],
    "car": ["car", "vehicle", "van", "truck"], "sign": ["sign", "signpost"], "phone": ["phone", "smartphone", "cellphone"],
    "house": ["house", "home", "building"], "rifle": ["rifle", "gun", "weapon"], "weapon": ["weapon", "gun", "rifle"],
}
_PREFIX = r"(?:ו?(?:ש?[הבלמכ]|כש)?)?"
_PAT = re.compile("(?:^|[\\s,.!?:;\"'])" + _PREFIX + "(" + "|".join(sorted(map(re.escape, HE2EN), key=len, reverse=True)) + ")(?=$|[\\s,.!?:;\"'])")


def find_nouns(he_text):
    """Lexicon nouns in the Hebrew text, in order of appearance: [(hebrew, english), ...]."""
    return [(m.group(1), HE2EN[m.group(1)]) for m in _PAT.finditer(he_text or "")]


def fix_target(he_text, target_en):
    """Returns (target_en, note). note is None when nothing changed."""
    found = find_nouns(he_text)
    if not found:
        return target_en, None
    t = (target_en or "").lower()
    for _, en in found:
        for alias in EN_ALIASES.get(en, [en]) + [en, en + "s"]:
            if re.search(r"\b" + re.escape(alias) + r"s?\b", t):
                return target_en, None
    en = found[0][1]
    return en, f"lexicon:{target_en!r}->{en!r}"
