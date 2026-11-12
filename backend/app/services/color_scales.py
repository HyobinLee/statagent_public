from __future__ import annotations

from typing import Any

MIN_CLASSES = 3
MAX_CLASSES = 7

SCALE_TYPE_LABELS = {
    "sequential": "순차형 단색 계열",
    "diverging": "순차형 반대색 계열",
}
SCALE_TYPE_HINTS = {
    "sequential": "값이 클수록 색이 진해집니다. 많고 적음을 볼 때 씁니다.",
    "diverging": "가운데 회색을 기준으로 양쪽이 반대 색입니다. 기준보다 높은 쪽과 낮은 쪽을 나눠 볼 때 씁니다.",
}

_SEQUENTIAL: dict[str, dict[int, list[str]]] = {
    "blue": {
        3: ["#66bdf1", "#1a87cf", "#2c53ab"],
        4: ["#66bdf1", "#2c99da", "#1a76c3", "#2c53ab"],
        5: ["#66bdf1", "#39a2e0", "#1a87cf", "#1f6dbd", "#2c53ab"],
        6: ["#66bdf1", "#3fa4e0", "#1f8ccf", "#1774be", "#245cac", "#2a469b"],
        7: ["#66bdf1", "#45a8e3", "#2994d5", "#1780c6", "#1b6cb8", "#2559a9", "#2a469b"],
    },
    "green": {
        3: ["#80b6a2", "#217e5a", "#00422b"],
        4: ["#80b6a2", "#459072", "#006a47", "#00422b"],
        5: ["#80b6a2", "#54997e", "#217e5a", "#006040", "#00422b"],
        6: ["#80b6a2", "#5a9c82", "#328362", "#006946", "#004e33", "#003521"],
        7: ["#80b6a2", "#60a087", "#408b6d", "#187753", "#006040", "#004a30", "#003521"],
    },
    "orange": {
        3: ["#dba193", "#b85d3e", "#772900"],
        4: ["#dba193", "#c4735b", "#ad481e", "#772900"],
        5: ["#dba193", "#ca7e69", "#b85d3e", "#a73d03", "#772900"],
        6: ["#dba193", "#ca826e", "#b9654a", "#a84822", "#8a3100", "#601f00"],
        7: ["#dba193", "#cd8774", "#bf6f56", "#b15637", "#a33f10", "#832e00", "#601f00"],
    },
    "violet": {
        3: ["#a7aeed", "#7071c9", "#4837a4"],
        4: ["#a7aeed", "#8185d5", "#615ebd", "#4837a4"],
        5: ["#a7aeed", "#8a8fdb", "#7071c9", "#5a54b7", "#4837a4"],
        6: ["#a7aeed", "#8d92dc", "#7577ca", "#5f5db8", "#4d43a6", "#3e2a93"],
        7: ["#a7aeed", "#9197de", "#7d80d0", "#6a6ac1", "#5954b2", "#4a3fa3", "#3e2a93"],
    },
    "red": {
        3: ["#e59ea4", "#c6585b", "#a51101"],
        4: ["#e59ea4", "#d16f73", "#bc4242", "#a51101"],
        5: ["#e59ea4", "#d67b7f", "#c6585b", "#b63736", "#a51101"],
        6: ["#e59ea4", "#d67f83", "#c66063", "#b64343", "#a62521", "#870b00"],
        7: ["#e59ea4", "#d98489", "#cc6a6e", "#bf5153", "#b13938", "#a3201a", "#870b00"],
    },
}

_DIVERGING: dict[str, dict[int, list[str]]] = {
    "blue_red": {
        3: ["#2c53ab", "#f0efec", "#a51101"],
        4: ["#2c53ab", "#66bdf1", "#e59ea4", "#a51101"],
        5: ["#2c53ab", "#66bdf1", "#f0efec", "#e59ea4", "#a51101"],
        6: ["#2a469b", "#1780c6", "#66bdf1", "#e59ea4", "#bf5153", "#870b00"],
        7: ["#2a469b", "#1780c6", "#66bdf1", "#f0efec", "#e59ea4", "#bf5153", "#870b00"],
    },
    "aqua_orange": {
        3: ["#00422b", "#f0efec", "#772900"],
        4: ["#00422b", "#80b6a2", "#dba193", "#772900"],
        5: ["#00422b", "#80b6a2", "#f0efec", "#dba193", "#772900"],
        6: ["#003521", "#187753", "#80b6a2", "#dba193", "#b15637", "#601f00"],
        7: ["#003521", "#187753", "#80b6a2", "#f0efec", "#dba193", "#b15637", "#601f00"],
    },
    "violet_green": {
        3: ["#4837a4", "#f0efec", "#004200"],
        4: ["#4837a4", "#a7aeed", "#87b48d", "#004200"],
        5: ["#4837a4", "#a7aeed", "#f0efec", "#87b48d", "#004200"],
        6: ["#3e2a93", "#6a6ac1", "#a7aeed", "#87b48d", "#2c742d", "#003400"],
        7: ["#3e2a93", "#6a6ac1", "#a7aeed", "#f0efec", "#87b48d", "#2c742d", "#003400"],
    },
}

_NAMES = {
    "blue": "파랑",
    "green": "초록",
    "orange": "주황",
    "violet": "보라",
    "red": "빨강",
    "blue_red": "파랑 – 빨강",
    "aqua_orange": "청록 – 주황",
    "violet_green": "보라 – 초록",
}

DEFAULT_SCALE = "blue"


def _steps(scale_id: str) -> dict[int, list[str]]:
    return _SEQUENTIAL.get(scale_id) or _DIVERGING[scale_id]


def scale_type(scale_id: str) -> str:
    return "sequential" if scale_id in _SEQUENTIAL else "diverging"


def known_scale(scale_id: str | None) -> str:
    if scale_id in _SEQUENTIAL or scale_id in _DIVERGING:
        return scale_id
    return DEFAULT_SCALE


def colors_for(scale_id: str, n_classes: int) -> list[str]:
    scale_id = known_scale(scale_id)
    n_classes = min(max(n_classes, MIN_CLASSES), MAX_CLASSES)
    return list(_steps(scale_id)[n_classes])


def scale_info(scale_id: str, n_classes: int = 5) -> dict[str, Any]:
    scale_id = known_scale(scale_id)
    kind = scale_type(scale_id)
    return {
        "scale_id": scale_id,
        "name": _NAMES[scale_id],
        "type": kind,
        "type_label": SCALE_TYPE_LABELS[kind],
        "type_hint": SCALE_TYPE_HINTS[kind],
        "colors": colors_for(scale_id, n_classes),
    }


def list_scales(n_classes: int = 5) -> list[dict[str, Any]]:
    return [scale_info(scale_id, n_classes) for scale_id in list(_SEQUENTIAL) + list(_DIVERGING)]
