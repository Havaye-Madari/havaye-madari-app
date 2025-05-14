# create_admin_script.py
from app import app, db # app و db را از پروژه خودتان import کنید
from app.models import User
# from werkzeug.security import generate_password_hash # دیگر به طور مستقیم نیاز نیست چون از user.set_password() استفاده می‌کنیم

def setup_or_update_admin():
    # --- نام کاربری و رمز عبور ادمین را اینجا مشخص کنید ---
    admin_username = "admin"
    admin_password = "madari@1404"  # اطمینان حاصل کنید که این همان رمزی است که می‌خواهید استفاده کنید
    # ----------------------------------------------------

    with app.app_context(): # نیاز به app context برای کار با دیتابیس
        user = User.query.filter_by(username=admin_username).first()

        if user:
            # اگر کاربر وجود دارد، رمز عبور او را به‌روزرسانی کنید
            try:
                user.set_password(admin_password)
                db.session.commit()
                print(f"Admin user '{admin_username}' password updated successfully by script.")
            except Exception as e:
                db.session.rollback()
                print(f"Error updating admin user '{admin_username}' password: {str(e)}")
        else:
            # اگر کاربر وجود ندارد، آن را ایجاد کنید
            try:
                new_user = User(username=admin_username)
                new_user.set_password(admin_password)
                db.session.add(new_user)
                db.session.commit()
                print(f"Admin user '{admin_username}' created successfully by script.")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating admin user '{admin_username}': {str(e)}")

if __name__ == "__main__":
    # تابع را به نام جدید تغییر دهید
    setup_or_update_admin()
