import os
import time
from supabase import create_client, Client
import colorlog

# Logger setup
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

_supabase: Client | None = None


def init_supabase(retries: int = 3, delay: int = 2):
    """
    Khởi tạo kết nối Supabase (phiên bản supabase-py >= 2.0, không dùng proxy).
    """
    global _supabase
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        logger.error("❌ Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong biến môi trường.")
        raise ValueError("Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong biến môi trường.")

    for attempt in range(1, retries + 1):
        try:
            logger.info(f"🔗 Đang kết nối Supabase (lần {attempt}/{retries}) ...")
            _supabase = create_client(url, key)

            # Test truy cập bảng (tùy chọn, để chắc chắn kết nối hoạt động)
            _supabase.table("users").select("id").limit(1).execute()

            logger.info("✅ Kết nối Supabase thành công.")
            return
        except Exception as e:
            logger.warning(f"⚠️ Lần thử {attempt}/{retries} thất bại: {e}")
            time.sleep(delay)

    logger.error("❌ Không thể kết nối Supabase sau nhiều lần thử.")
    raise RuntimeError("Supabase chưa được khởi tạo.")


def get_supabase() -> Client:
    """
    Trả về đối tượng Supabase client đã khởi tạo.
    """
    if _supabase is None:
        raise RuntimeError("Supabase chưa được khởi tạo. Hãy gọi init_supabase() trước.")
    return _supabase


def test_connection():
    """
    Hàm kiểm tra nhanh xem Supabase có hoạt động hay không.
    """
    sb = get_supabase()
    try:
        res = sb.table("users").select("email").limit(1).execute()
        logger.info(f"✅ Kiểm tra Supabase thành công ({len(res.data)} bản ghi được trả về).")
    except Exception as e:
        logger.error(f"❌ Lỗi khi kiểm tra Supabase: {e}")
