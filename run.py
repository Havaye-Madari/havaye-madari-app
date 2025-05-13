import sys
import os

# اضافه کردن مسیر اصلی پروژه به PYTHONPATH
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # تلاش برای وارد کردن app
    from app import app
    print("✅ فایل app با موفقیت وارد شد.")

    if __name__ == '__main__':
        # --- UPDATED: Removed debug=True for production ---
        # The WSGI server (like Gunicorn or the one in PythonAnywhere)
        # will handle running the app in production, not this app.run() call.
        # This block might not even be executed when deployed via WSGI.
        # Keeping the port specification can be useful for local testing without debug.
        print("🚀 سرور Flask (برای تست محلی بدون دیباگ) روی پورت 5000")
        # Note: When deploying, the command in Procfile or WSGI config takes precedence.
        app.run(host='0.0.0.0', port=5000) # Listen on all interfaces, remove debug

except Exception as e:
    print(f"❌ خطا در اجرای برنامه: {e}")
    import traceback
    traceback.print_exc()
