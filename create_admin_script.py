# create_admin_script.py
from app import app, db # app و db را از پروژه خودتان import کنید
from app.models import User
from werkzeug.security import generate_password_hash

def setup_admin():
    # --- نام کاربری و رمز عبور ادمین را اینجا مشخص کنید ---
    admin_username = "admin"
    admin_password = "madari@1404"
    # ----------------------------------------------------

    with app.app_context(): # نیاز به app context برای کار با دیتابیس
        if User.query.filter_by(username=admin_username).first():
            print(f"Admin user '{admin_username}' already exists.")
            return

        try:
            new_user = User(username=admin_username)
            new_user.set_password(admin_password)
            db.session.add(new_user)
            db.session.commit()
            print(f"Admin user '{admin_username}' created successfully by script.")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user by script: {str(e)}")

if __name__ == "__main__":
    setup_admin()