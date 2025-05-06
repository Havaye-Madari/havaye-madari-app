# app/__init__.py
import os
from flask import Flask, session, flash, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user
# --- UPDATED: Import User model directly here for initial user creation ---
from app.models import db, User
# --- End UPDATED ---
from werkzeug.security import generate_password_hash # Needed for initial user creation

# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='static')

# Set SECRET_KEY from Environment Variable
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'insecure-default-key-for-dev-only-change-me')
if app.config['SECRET_KEY'] == 'insecure-default-key-for-dev-only-change-me':
    print("⚠️ WARNING: Using default SECRET_KEY. Set a proper SECRET_KEY environment variable for production!")

# Configure Database URI
database_url = os.environ.get('DATABASE_URL', 'sqlite:///eval.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Upload Folder
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'participants')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
print(f"ℹ️ Upload folder set to: {app.config['UPLOAD_FOLDER']}")


# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Initialize SQLAlchemy extension
# db object is already imported from app.models
db.init_app(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "برای دسترسی به این صفحه، لطفاً وارد شوید."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    """Required user loader function for Flask-Login."""
    # User model is already imported
    return User.query.get(int(user_id))


# Register blueprints AFTER initializing app and extensions
from app.routes.admin import admin_bp
from app.routes.participants import participants_bp
from app.routes.main import main_bp
from app.routes.results import results_bp
from app.routes.participant_view import participant_view_bp
from app.routes.auth import auth_bp

app.register_blueprint(admin_bp)
app.register_blueprint(participants_bp)
app.register_blueprint(main_bp)
app.register_blueprint(results_bp)
app.register_blueprint(participant_view_bp)
app.register_blueprint(auth_bp)

# Create database tables and initial admin user within the application context
with app.app_context():
    print("Checking/creating database tables...")
    try:
        db.create_all()
        print("Database tables checked/created.")

        # --- NEW: Create initial admin user if no users exist ---
        try:
            if not User.query.first(): # Check if any user exists
                print("ℹ️ No users found. Creating default admin user...")
                # *** IMPORTANT: Set a STRONG password here or via Environment Variable ***
                # Option 1: Use an Environment Variable (Recommended)
                default_admin_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'change_this_default_password')
                if default_admin_password == 'change_this_default_password':
                     print("⚠️ WARNING: Using a default password for initial admin user because DEFAULT_ADMIN_PASSWORD env var is not set. Please set it or change the password immediately after first login!")
                # Option 2: Hardcode a STRONG password (Less Recommended)
                # default_admin_password = 'YourVeryStrongPasswordHere123!'

                admin_user = User(username='admin')
                admin_user.set_password(default_admin_password) # Hashes the password
                db.session.add(admin_user)
                db.session.commit()
                print(f"✅ Default admin user 'admin' created.")
            else:
                print("ℹ️ Users already exist. Skipping default admin creation.")
        except Exception as e_user:
            print(f"❌ Error during initial admin user creation check: {e_user}")
            db.session.rollback() # Rollback in case of error during check/creation
        # --- End initial admin user creation ---

    except Exception as e_db:
        # Catch potential errors during DB connection/creation on startup
        print(f"❌ Error during db.create_all(): {e_db}")
        print("ℹ️ Note: Ensure the database server is running and accessible.")


# Global context processor for is_participant_view
@app.context_processor
def inject_view_mode():
    from flask import g
    return dict(is_participant_view=getattr(g, 'is_participant_view', False))

# Before request handler to set the is_participant_view flag for templates
@app.before_request
def set_participant_view_flag():
    from flask import request, g
    g.is_participant_view = False
    if request.endpoint == 'results.participant_summary':
        view_mode = request.args.get('view_mode', 'admin')
        if view_mode == 'participant':
            g.is_participant_view = True


# --- REMOVED: CLI command to create admin user (no longer needed/usable on free Render) ---
# import click
# @app.cli.command("create-admin")
# ... (command code removed) ...
# --- End REMOVED ---

