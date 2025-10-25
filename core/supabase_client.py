import os
import time
import requests
import colorlog

logger = colorlog.getLogger("SUPABASE")
handler = colorlog.StreamHandler()
formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s | SUPABASE | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red'
    }
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel("INFO")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_headers = None
_initialized = False


def init_supabase(retries: int = 3, delay: int = 2):
    global _headers, _initialized

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("❌ Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong biến môi trường.")
        raise ValueError("Thiếu SUPABASE_URL hoặc SUPABASE_KEY.")

    base = f"{SUPABASE_URL}/rest/v1"
    _headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🔗 Đang kiểm tra kết nối Supabase (lần {attempt}/{retries}) ...")
            resp = requests.get(f"{base}/users?select=id&limit=1", headers=_headers, timeout=10)
            if resp.status_code == 200:
                logger.info("✅ Kết nối Supabase REST API thành công.")
                _initialized = True
                return
            else:
                logger.warning(f"⚠️ Lỗi HTTP {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"⚠️ Lần thử {attempt}/{retries} thất bại: {e}")
        time.sleep(delay)

    logger.error("❌ Không thể kết nối Supabase sau nhiều lần thử.")
    raise RuntimeError("Supabase chưa được khởi tạo.")


def query(table: str, filters: str = "", limit: int = 100):
    """Thực hiện GET query tới Supabase REST."""
    if not _initialized:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&limit={limit}{filters}"
    r = requests.get(url, headers=_headers, timeout=15)
    if r.status_code == 200:
        return r.json()
    raise RuntimeError(f"Lỗi Supabase query: {r.status_code} - {r.text}")


def insert(table: str, data: dict):
    """Thêm bản ghi mới."""
    if not _initialized:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = requests.post(url, headers=_headers, json=data, timeout=15)
    if r.status_code in [200, 201]:
        return r.json()
    raise RuntimeError(f"Lỗi insert: {r.status_code} - {r.text}")


def update(table: str, match: str, data: dict):
    """Cập nhật bản ghi (match là filter, ví dụ: 'email=eq.user@example.com')."""
    if not _initialized:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    url = f"{SUPABASE_URL}/rest/v1/{table}?{match}"
    r = requests.patch(url, headers=_headers, json=data, timeout=15)
    if r.status_code in [200, 204]:
        return True
    raise RuntimeError(f"Lỗi update: {r.status_code} - {r.text}")


def delete(table: str, match: str):
    """Xóa bản ghi."""
    if not _initialized:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    url = f"{SUPABASE_URL}/rest/v1/{table}?{match}"
    r = requests.delete(url, headers=_headers, timeout=15)
    if r.status_code in [200, 204]:
        return True
    raise RuntimeError(f"Lỗi delete: {r.status_code} - {r.text}")
