from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "records.json"
WEB_DIR = BASE_DIR / "web"

EXPENSE_CATEGORIES = ["饮食", "交通", "购物", "居住", "学习", "娱乐", "医疗", "其他"]
INCOME_CATEGORIES = ["工资", "生活费", "兼职", "奖学金", "理财", "其他"]

RECORD_TYPES = {"expense": "支出", "income": "收入"}

DATE_FORMAT = "%Y-%m-%d"
CURRENCY = "¥"

MAX_NOTE_LENGTH = 100