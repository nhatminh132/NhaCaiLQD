# core/supabase_client.py
# Quản lý kết nối Supabase: tự khởi tạo, retry khi lỗi, tương thích mọi version supabase-py
import os
import time
import logging
from supabase import create_client, Client

# === Cấu hình logging màu (đẹp trên Render) === #
class LogColors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | SUPABASE | %(message)s",
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client: Client | None = None


# === Hàm tạo client tương thích mọi phiên bản === #
def safe_create_client(url: str, key: str) -> Client:
    """
    Tạo client tương thích với cả phiên bản mới và cũ của supabase-py.
    Một số bản (2.3.3 trở về trước) không chấp nhận argument 'proxy'.
    """
    try:
        return create_client(url, key)
    except TypeError as e:
        if "proxy" in str(e).lower():
            logging.warning(
                f"{LogColors.YELLOW}Phiên bản supabase-py hiện tại không hỗ trợ 'proxy'. "
                "Thử tạo client fallback...%s", LogColors.RESET
            )
            return Client(supabase_url=url, supabase_key=key)
        raise


def init_supabase(retries: int = 3, delay: int = 2):
    """
    Khởi tạo kết nối Supabase với cơ chế retry tự động.
    Nếu thất bại quá 3 lần → báo lỗi dừng bot.
    """
    global supabase_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error(f"{LogColors.RED}Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong biến môi trường!{LogColors.RESET}")
        raise RuntimeError("Thiếu cấu hình Supabase.")

    for attempt in range(1, retries + 1):
        try:
            supabase_client = safe_create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test nhanh kết nối bằng table profiles
            _ = supabase_client.table("profiles").select("user_id").limit(1).execute()
            logging.info(f"{LogColors.GREEN}✅ Supabase khởi tạo thành công!{LogColors.RESET}")
            return
        except Exception as e:
            logging.warning(f"{LogColors.YELLOW}⚠️ Lần thử {attempt}/{retries} kết nối Supabase thất bại: {e}{LogColors.RESET}")
            time.sleep(delay)

    logging.critical(f"{LogColors.RED}❌ Không thể kết nối Supabase sau {retries} lần thử.{LogColors.RESET}")
    raise RuntimeError("Supabase chưa được khởi tạo.")


# === Truy cập client an toàn === #
def get_client() -> Client:
    global supabase_client
    if supabase_client is None:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    return supabase_client


def get_table(table_name: str):
    """Trả về table object để thao tác CRUD."""
    return get_client().table(table_name)


# === Các hàm thao tác dữ liệu cơ bản === #
def fetch_profile(user_id: int):
    """Lấy thông tin hồ sơ người chơi."""
    try:
        data = (
            get_table("profiles")
            .select("*")
            .eq("user_id", user_id)
            .execute()
        ).data
        return data[0] if data else None
    except Exception as e:
        logging.error(f"Lỗi khi lấy profile {user_id}: {e}")
        return None


def ensure_profile(user_id: int):
    """
    Đảm bảo người chơi có hồ sơ trong bảng profiles.
    Nếu chưa có → tạo mới với số dư = 0.
    """
    profile = fetch_profile(user_id)
    if profile:
        return profile

    try:
        get_table("profiles").insert({
            "user_id": user_id,
            "balance": 0,
            "total_bet": 0,
            "total_won": 0,
            "games_played": 0,
        }).execute()
        logging.info(f"Tạo profile mới cho user {user_id}")
    except Exception as e:
        logging.error(f"Lỗi khi tạo profile mới {user_id}: {e}")


def update_balance(user_id: int, delta: int, reason: str = "Cập nhật số dư"):
    """
    Cập nhật số dư người chơi trong bảng profiles.
    """
    profile = fetch_profile(user_id)
    if not profile:
        ensure_profile(user_id)
        profile = {"balance": 0}

    new_balance = profile["balance"] + delta
    if new_balance < 0:
        new_balance = 0  # Không âm

    try:
        get_table("profiles").update({"balance": new_balance}).eq("user_id", user_id).execute()
        logging.info(f"💰 {reason}: {user_id} thay đổi {delta}, số dư mới {new_balance}")
        return new_balance
    except Exception as e:
        logging.error(f"Lỗi update_balance({user_id}): {e}")
        return profile["balance"]
