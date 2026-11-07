import re

from src.config import EXPENSE_CATEGORIES, INCOME_CATEGORIES

KEYWORDS = {
    "饮食": ["饭", "早餐", "午饭", "晚饭", "外卖", "奶茶", "咖啡", "食堂", "零食", "聚餐"],
    "交通": ["地铁", "公交", "打车", "高铁", "火车", "油费", "共享单车"],
    "购物": ["买", "淘宝", "京东", "衣服", "鞋", "日用品"],
    "居住": ["房租", "水电", "物业", "宿舍"],
    "学习": ["书", "课程", "打印", "文具", "网课"],
    "娱乐": ["电影", "游戏", "健身", "唱歌"],
    "医疗": ["药", "医院", "挂号"],
    "工资": ["工资", "薪水", "发薪"],
    "生活费": ["生活费", "家里打钱", "爸妈"],
    "兼职": ["兼职", "家教", "实习", "稿费"],
    "奖学金": ["奖学金", "助学金"],
    "理财": ["利息", "基金", "理财", "分红"],
}

AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d{1,2})?)\s*(?:元|块|rmb|￥|¥)?", re.IGNORECASE)
INCOME_HINTS = ("收入", "收到", "工资", "兼職", "兼职", "奖学金", "生活费", "进账")


def guess_category(text):
    for category, words in KEYWORDS.items():
        if any(word in text for word in words):
            return category
    return None


def parse_text(text):
    source = (text or "").strip()
    if not source:
        return None

    match = AMOUNT_PATTERN.search(source)
    if not match:
        return None
    amount = float(match.group(1))
    if amount <= 0:
        return None

    record_type = "income" if any(hint in source for hint in INCOME_HINTS) else "expense"
    category = guess_category(source)
    if category is None:
        category = "其他"
    allowed = INCOME_CATEGORIES if record_type == "income" else EXPENSE_CATEGORIES
    if category not in allowed:
        record_type = "expense"
        if category not in EXPENSE_CATEGORIES:
            category = "其他"

    note = AMOUNT_PATTERN.sub("", source).strip()
    note = re.sub(r"元|块|收入|支出", "", note).strip() or "快速记账"
    return {"type": record_type, "amount": amount, "category": category, "note": note[:100]}