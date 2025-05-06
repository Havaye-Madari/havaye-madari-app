# app/__init__.py
import os
from flask import Flask, session, flash, redirect, url_for, request # Import session etc.
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user # Import LoginManager, current_user
# Datetime and timedelta are not needed anymore if idle timeout is removed
# from datetime import datetime, timedelta


# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='static')

# Set SECRET_KEY from Environment Variable
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'insecure-default-key-for-dev-only-change-me')
if app.config['SECRET_KEY'] == 'insecure-default-key-for-dev-only-change-me':
    print("⚠️ WARNING: Using default SECRET_KEY. Set a proper SECRET_KEY environment variable for production!")

# --- UPDATED: Configure Database URI ---
# Read database URL from environment variable (used by Render/Heroku)
# Fallback to SQLite for local development if DATABASE_URL is not set
database_url = os.environ.get('DATABASE_URL', 'sqlite:///eval.db')
# Handle the older 'postgres://' prefix sometimes used by platforms like Heroku
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
# --- End Database URI Configuration ---

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Upload Folder
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'participants')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
print(f"ℹ️ Upload folder set to: {app.config['UPLOAD_FOLDER']}")


# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Initialize SQLAlchemy extension
# Use absolute import for models
from app.models import db, User
db.init_app(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login' # Route to redirect to for login
login_manager.login_message = "برای دسترسی به این صفحه، لطفاً وارد شوید."
login_manager.login_message_category = "info" # Bootstrap category for flash message

@login_manager.user_loader
def load_user(user_id):
    """Required user loader function for Flask-Login."""
    return User.query.get(int(user_id))


# Register blueprints AFTER initializing app and extensions
# Use absolute imports for routes as well
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

# Create database tables within the application context
# Note: In a production scenario with migrations (like Flask-Migrate),
# you might remove db.create_all() or guard it.
with app.app_context():
    print("Checking/creating database tables...")
    try:
        db.create_all()
        print("Database tables checked/created.")
    except Exception as e:
        # Catch potential errors during DB connection/creation on startup
        print(f"❌ Error during db.create_all(): {e}")
        print("ℹ️ Note: Ensure the database server is running and accessible.")
        print("ℹ️ Note: In production, manage database creation/migration separately.")


# Global context processor for is_participant_view
@app.context_processor
def inject_view_mode():
    from flask import g
    # Provide a default value if the attribute hasn't been set
    return dict(is_participant_view=getattr(g, 'is_participant_view', False))

# Before request handler to set the is_participant_view flag for templates
@app.before_request
def set_participant_view_flag():
    from flask import request, g
    # Set default at the beginning of each request
    g.is_participant_view = False
    # Check specifically for the participant results endpoint
    if request.endpoint == 'results.participant_summary':
        view_mode = request.args.get('view_mode', 'admin')
        if view_mode == 'participant':
            g.is_participant_view = True


# CLI command to create admin user
import click
from werkzeug.security import generate_password_hash

@app.cli.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin(username, password):
    """Creates the initial admin user."""
    # Ensure command runs within application context to access db
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"Error: User '{username}' already exists.")
            return
        new_user = User(username=username)
        new_user.set_password(password) # Hash the password
        db.session.add(new_user)
        db.session.commit()
        print(f"Admin user '{username}' created successfully.")

