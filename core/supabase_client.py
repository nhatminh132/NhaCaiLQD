import os
from supabase import create_client, Client
from dotenv import load_dotenv
from core.utils import log_info, log_warn

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None

def supabase_init() -> Client:
    global supabase
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log_info("Supabase khởi tạo thành công.")
        return supabase
    except Exception as e:
        log_warn(f"Lỗi kết nối Supabase: {e}")
        return None

def get_table(name: str):
    if not supabase:
        raise RuntimeError("Supabase chưa được khởi tạo.")
    return supabase.table(name)
