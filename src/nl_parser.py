import re

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

INCOME_HINTS = ("收入", "收到", "进账", "工资", "薪水", "兼职", "家教", "实习", "稿费", "奖学金", "助学金", "生活费", "利息", "分红", "收益")

DATE_PATTERNS = [
    re.compile(r"\d{4}\s*[-/年]\s*\d{1,2}\s*[-/月]\s*\d{1,2}\s*[日号]?"),
    re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]?"),
    re.compile(r"\d{1,2}\s*/\s*\d{1,2}"),
    re.compile(r"(?:今天|昨天|前天|上周|本周|这周|上午|下午|晚上|中午|早上|凌晨)"),
]

QUANTIFIER_SUFFIX = "杯|个|份|斤|公斤|瓶|次|天|月|日|年|号|点|路|楼|人|张|本|件|袋|盒|包|支|只|台|辆|双|套|碗|顿|节|小时|分钟"

UNIT_PATTERN = re.compile(r"(\d+(?:\.\d{1,2})?)\s*(?:元|块钱|块|rmb|RMB|￥|¥|人民币)")
QUANTIFIED_PATTERN = re.compile(r"(\d+(?:\.\d{1,2})?)\s*(?:" + QUANTIFIER_SUFFIX + r")")
NUMBER_PATTERN = re.compile(r"(\d+(?:\.\d{1,2})?)")


def guess_category(text):
    best = None
    best_length = 0
    for category, words in KEYWORDS.items():
        for word in words:
            if word in text and len(word) > best_length:
                best = category
                best_length = len(word)
    return best


def _clean_text(text):
    cleaned = text
    for pattern in DATE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def _extract_amount(text):
    unit_matches = UNIT_PATTERN.findall(text)
    if unit_matches:
        return float(unit_matches[-1]), True

    cleaned = QUANTIFIED_PATTERN.sub(" ", text)
    cleaned = UNIT_PATTERN.sub(" ", cleaned)
    numbers = NUMBER_PATTERN.findall(cleaned)
    if not numbers:
        return None, False
    return float(numbers[-1]), False


def _build_note(text, amount, had_unit):
    note = text
    for pattern in DATE_PATTERNS:
        note = pattern.sub(" ", note)
    if had_unit:
        note = UNIT_PATTERN.sub(" ", note)
    else:
        note = QUANTIFIED_PATTERN.sub(" ", note)
        note = re.sub(r"(?<!\d)" + re.escape(f"{amount:g}") + r"(?!\d)", " ", note)
    note = re.sub(r"[，,。.！!？?、；;：:]", " ", note)
    note = re.sub(r"\s+", " ", note).strip()
    return note[:100] or "快速记账"


def parse_text(text):
    source = (text or "").strip()
    if not source:
        return None

    normalized = _clean_text(source)
    amount, had_unit = _extract_amount(normalized)
    if amount is None or amount <= 0:
        return None

    record_type = "income" if any(hint in normalized for hint in INCOME_HINTS) else "expense"
    category = guess_category(normalized)
    allowed = INCOME_CATEGORIES if record_type == "income" else EXPENSE_CATEGORIES
    if category not in allowed:
        fallback = guess_category(normalized)
        category = fallback if fallback in allowed else "其他"

    note = _build_note(source, amount, had_unit)
    return {"type": record_type, "amount": round(amount, 2), "category": category, "note": note}