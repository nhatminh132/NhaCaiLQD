import datetime
import pytz
import colorlog

# Logger màu
logger = colorlog.getLogger("CasinoBot")
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)-8s%(reset)s | %(message)s",
    log_colors={"INFO": "green", "WARNING": "yellow", "ERROR": "red"}
))
logger.addHandler(handler)
logger.setLevel("INFO")

def log_info(msg): logger.info(msg)
def log_warn(msg): logger.warning(msg)
def log_error(msg): logger.error(msg)

# Lấy giờ VN
def now_vn() -> datetime.datetime:
    return datetime.datetime.now(pytz.timezone("Asia/Ho_Chi_Minh"))

# Định dạng tiền tệ
def fmt_money(amount: int) -> str:
    return f"{amount:,} 🪙"

# Emoji mặc định
TICK = "<a:tick:1430933260581605376>"
CROSS = "<a:cross:1430933257167442010>"
