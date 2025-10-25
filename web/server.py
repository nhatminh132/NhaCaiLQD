# web/server.py
from flask import Flask, jsonify
import threading, os, logging

# Cấu hình log gọn gàng
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | WEB | %(message)s",
)

app = Flask(__name__)

@app.route('/')
def home():
    """Trang root – kiểm tra bot còn sống không."""
    return jsonify({
        "status": "✅ Bot is alive!",
        "service": "Discord Casino Bot (Render Free)",
    })

@app.route('/health')
def health():
    """Dành cho uptime monitor"""
    return "OK", 200

def run():
    """Khởi chạy Flask server trên Render"""
    port = int(os.environ.get("PORT", 10000))
    logging.info(f"Flask server đang chạy tại port {port}")
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    """Chạy Flask trong thread riêng biệt song song với Discord bot"""
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    logging.info("Flask keep-alive thread started.")
