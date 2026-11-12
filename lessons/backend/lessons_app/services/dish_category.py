CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "면류·튀김류",
        (
            "우동",
            "짬뽕",
            "국수",
            "라면",
            "라멘",
            "파스타",
            "스파게티",
            "돈까스",
            "까스",
            "튀김",
            "탕수육",
            "강정",
            "너겟",
            "피자",
            "그라탕",
            "꿔바로우",
            "파르팔레",
        ),
    ),
    (
        "육류 주찬",
        (
            "불고기",
            "제육",
            "갈비",
            "삼겹",
            "수육",
            "닭",
            "돈육",
            "소고기",
            "쇠고기",
            "찜",
            "스테이크",
            "목살",
            "족발",
            "치킨",
            "한돈",
            "한우",
            "돼지",
            "바베큐",
            "짜글이",
        ),
    ),
    ("한식 일반", ("덮밥", "비빔밥", "볶음밥", "구이", "조림", "볶음", "전", "짜장", "필라프", "커리", "라이스")),
]
DEFAULT_CATEGORY = "나물·채소 위주"
ALL_CATEGORIES = tuple(name for name, _ in CATEGORY_RULES) + (DEFAULT_CATEGORY,)


def suggest_category(main_dish: str) -> str:
    for category, keywords in CATEGORY_RULES:
        if any(keyword in main_dish for keyword in keywords):
            return category
    return DEFAULT_CATEGORY
