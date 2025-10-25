# core/supabase_client.py
# Quản lý kết nối Supabase — ổn định, tự khởi tạo, retry nếu gặp lỗi
import os
import time
import logging
from supabase import create_client, Client

# Cấu hình log gọn gàng
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | SUPABASE | %(message)s",
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client: Client | None = None


def init_supabase(retries: int = 3, delay: int = 2):
    """
    Khởi tạo kết nối Supabase với cơ chế retry tự động.
    Nếu thành công → gán global client.
    """
    global supabase_client

    if not SUPABASE_URL or not SUPABASE_KEY:
        logging.error("⚠️ Không tìm thấy biến môi trường SUPABASE_URL hoặc SUPABASE_KEY.")
        raise RuntimeError("Thiếu cấu hình Supabase.")

    for attempt in range(1, retries + 1):
        try:
            supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test nhanh kết nối
            _ = supabase_client.table("profiles").select("user_id").limit(1).execute()
            logging.info("✅ Supabase khởi tạo thành công.")
            return
        except Exception as e:
            logging.warning(f"⚠️ Lần thử {attempt}/{retries} kết nối Supabase thất bại: {e}")
            time.sleep(delay)

    logging.critical("❌ Không thể kết nối Supabase sau nhiều lần thử.")
    raise RuntimeError("Supabase chưa được khởi tạo.")


def get_client() -> Client:
    """Lấy client Supabase (nếu chưa init thì báo lỗi rõ ràng)."""
    global supabase_client
    if supabase_client is None:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    return supabase_client


def get_table(table_name: str):
    """Trả về table object để thao tác CRUD."""
    return get_client().table(table_name)


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
        logging.error(f"Lỗi khi lấy profile người chơi {user_id}: {e}")
        return None


def ensure_profile(user_id: int):
    """
    Đảm bảo người chơi có trong bảng profiles.
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
