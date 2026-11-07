import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from src.config import EXPENSE_CATEGORIES, INCOME_CATEGORIES

KEYWORDS = {
    "饮食": ["早饭", "早餐", "午饭", "午餐", "晚饭", "晚餐", "外卖", "奶茶", "咖啡", "食堂", "零食", "聚餐", "宵夜", "水果"],
    "交通": ["地铁", "公交", "打车", "高铁", "火车", "油费", "加油", "共享单车", "停车", "机票"],
    "购物": ["买", "淘宝", "京东", "拼多多", "衣服", "鞋", "日用品", "快递"],
    "居住": ["房租", "水电", "物业", "宿舍", "宽带", "燃气"],
    "学习": ["书", "课程", "打印", "文具", "网课", "资料", "考试"],
    "娱乐": ["电影", "游戏", "健身", "唱歌", "会员", "旅游"],
    "医疗": ["药", "医院", "挂号", "体检", "看病"],
    "工资": ["工资", "薪水", "发薪", "月薪"],
    "生活费": ["生活费", "家里打钱", "爸妈给", "家用"],
    "兼职": ["兼职", "家教", "实习", "稿费", "副业"],
    "奖学金": ["奖学金", "助学金", "补贴"],
    "理财": ["利息", "基金", "理财", "分红", "收益"],
}

INCOME_HINTS = (
    "收入", "收到", "进账", "工资", "薪水", "兼职", "家教", "实习", "稿费",
    "奖学金", "助学金", "生活费", "利息", "分红", "收益",
)

DATE_PATTERNS = [
    re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*[日号]?"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?"),
    re.compile(r"\d{1,2}\s*/\s*\d{1,2}"),
    re.compile(r"(?:今天|昨天|前天|上周|本周|这周|上午|下午|晚上|中午|早上|凌晨)"),
]

QUANTIFIER_SUFFIX = (
    "杯|个|份|斤|公斤|瓶|次|天|月|日|年|号|点|路|楼|人|张|本|件|袋|盒|包|支|只|台|辆|双|套|碗|顿|节|小时|分钟"
)
QUANTIFIED_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:" + QUANTIFIER_SUFFIX + r")"
)

_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_AMOUNT_PATTERN = re.compile(
    r"(?<![\d.])(?P<sign>[+-]?)\s*(?:(?:人民币|RMB|CNY|¥|￥)\s*)?"
    r"(?P<number>" + _NUMBER + r")\s*(?:(?:元|块钱|块|人民币|RMB|CNY))?(?![\d.])",
    re.IGNORECASE,
)
_CURRENCY_PREFIX_PATTERN = re.compile(r"(?:人民币|RMB|CNY|¥|￥)", re.IGNORECASE)
_CURRENCY_SUFFIX_PATTERN = re.compile(r"(?:人民币|RMB|CNY|元|块钱|块)", re.IGNORECASE)
_MONEY_QUANTUM = Decimal("0.01")


def guess_category(text):
    best = None
    best_length = 0
    for category, words in KEYWORDS.items():
        for word in words:
            if word in text and len(word) > best_length:
                best = category
                best_length = len(word)
    return best


def _mask_patterns(text, patterns):
    masked = text
    for pattern in patterns:
        masked = pattern.sub(lambda match: " " * len(match.group()), masked)
    return masked


def _extract_amount(text):
    """Return the final plausible amount and its span in the original text."""
    candidates = []
    for match in _AMOUNT_PATTERN.finditer(text):
        raw_number = match.group("number")
        after = text[match.end():]
        has_currency = bool(
            _CURRENCY_PREFIX_PATTERN.search(match.group())
            or _CURRENCY_SUFFIX_PATTERN.search(match.group())
        )

        # Plain quantities such as "2杯" are not monetary amounts.
        if not has_currency and re.match(r"\s*(?:" + QUANTIFIER_SUFFIX + r")", after):
            continue
        # A leading minus denotes an invalid negative amount, rather than a positive one.
        sign = match.group("sign")
        if sign == "-":
            continue
        try:
            amount = Decimal(raw_number.replace(",", ""))
            amount = amount.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            continue
        if amount <= 0:
            continue
        candidates.append((amount, match.span()))

    return candidates[-1] if candidates else (None, None)


def _build_note(text, amount_span):
    note = _mask_patterns(text, DATE_PATTERNS)
    note = _mask_patterns(note, [QUANTIFIED_PATTERN])
    if amount_span:
        start, end = amount_span
        note = note[:start] + (" " * (end - start)) + note[end:]
    note = re.sub(r"[，,。.！!？?、；;：:]", " ", note)
    note = re.sub(r"\s+", " ", note).strip()
    return note[:100] or "快速记账"


def parse_text(text):
    if not isinstance(text, str):
        return None
    source = text.strip()
    if not source:
        return None

    # Mask dates and quantities without changing offsets, so amount extraction and
    # note cleanup use the same positions in the original phrase.
    normalized = _mask_patterns(source, DATE_PATTERNS)
    normalized = _mask_patterns(normalized, [QUANTIFIED_PATTERN])
    amount, amount_span = _extract_amount(normalized)
    if amount is None:
        return None

    record_type = "income" if any(hint in normalized for hint in INCOME_HINTS) else "expense"
    category = guess_category(normalized)
    allowed = INCOME_CATEGORIES if record_type == "income" else EXPENSE_CATEGORIES
    category = category if category in allowed else "其他"

    note = _build_note(source, amount_span)
    return {
        "type": record_type,
        "amount": float(amount),
        "category": category,
        "note": note,
    }
