import re

GRID_COLS = 12
PAGE_ROWS = 20
MAX_PAGES = 8

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
PAGE_MARGIN_MM = 12.0
CELL_GAP_MM = 2.0

CONTENT_WIDTH_MM = PAGE_WIDTH_MM - 2 * PAGE_MARGIN_MM
CONTENT_HEIGHT_MM = PAGE_HEIGHT_MM - 2 * PAGE_MARGIN_MM
COL_WIDTH_MM = CONTENT_WIDTH_MM / GRID_COLS
ROW_HEIGHT_MM = CONTENT_HEIGHT_MM / PAGE_ROWS

DEFAULT_PRIMARY_COLOR = "#173f3d"
DEFAULT_ACCENT_COLOR = "#287c7a"
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

REPORT_FONTS: dict[str, dict] = {
    "gothic": {
        "label": "고딕(기본)",
        "regular": [
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic-Regular.ttf",
            "C:/Windows/Fonts/malgun.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        ],
        "bold": [
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic-Bold.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
        ],
        "css_stack": '"NanumGothic", "Nanum Gothic", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif',
        "office": ["NanumGothic", "Malgun Gothic", "Arial"],
    },
    "myeongjo": {
        "label": "명조(바탕)",
        "regular": [
            "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf",
            "/usr/share/fonts/truetype/nanum/NanumMyeongjo-Regular.ttf",
            "C:/Windows/Fonts/batang.ttc",
        ],
        "bold": [
            "/usr/share/fonts/truetype/nanum/NanumMyeongjoBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumMyeongjo-Bold.ttf",
        ],
        "css_stack": '"NanumMyeongjo", "Nanum Myeongjo", "Batang", "Apple SD Gothic Neo", serif',
        "office": ["NanumMyeongjo", "Batang", "Times New Roman"],
    },
    "barun": {
        "label": "바른고딕(본문용)",
        "regular": [
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic-Regular.ttf",
            "C:/Windows/Fonts/malgunsl.ttf",
        ],
        "bold": [
            "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumBarunGothic-Bold.ttf",
            "C:/Windows/Fonts/malgun.ttf",
        ],
        "css_stack": '"NanumBarunGothic", "Nanum Barun Gothic", "Malgun Gothic", sans-serif',
        "office": ["NanumBarunGothic", "Malgun Gothic", "Arial"],
    },
}
DEFAULT_FONT_KEY = "gothic"


def clamp_rect(x, y, w, h) -> tuple[int, int, int, int]:
    width = _as_int(w, 1)
    height = _as_int(h, 1)
    width = max(1, min(width, GRID_COLS))
    height = max(1, min(height, PAGE_ROWS))

    left = _as_int(x, 0)
    top = _as_int(y, 0)
    left = max(0, min(left, GRID_COLS - width))
    top = max(0, min(top, PAGE_ROWS - height))
    return left, top, width, height


def normalize_hex_color(value, fallback: str) -> str:
    text = str(value or "").strip()
    return text.lower() if HEX_COLOR_RE.match(text) else fallback


def normalize_font_key(value) -> str:
    key = str(value or "").strip()
    return key if key in REPORT_FONTS else DEFAULT_FONT_KEY


def _as_int(value, fallback: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback
