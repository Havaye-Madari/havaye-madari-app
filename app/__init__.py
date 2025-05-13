# app/__init__.py
import os
import json # برای کار با JSON در فیلتر
from flask import Flask, session, flash, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, current_user, logout_user
from datetime import datetime, timedelta


# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='static')

# Set SECRET_KEY from Environment Variable
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'insecure-default-key-for-dev-only-change-me')
if app.config['SECRET_KEY'] == 'insecure-default-key-for-dev-only-change-me':
    print("⚠️ WARNING: Using default SECRET_KEY. Set a proper SECRET_KEY environment variable for production!")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///eval.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Upload Folder
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'participants')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
print(f"ℹ️ Upload folder set to: {app.config['UPLOAD_FOLDER']}")

# Initialize CSRF Protection
csrf = CSRFProtect(app)

# Initialize SQLAlchemy extension
from app.models import db, User 
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
    return User.query.get(int(user_id))

# --- NEW: Define and register custom Jinja filter 'fromjson' ---
def from_json_filter(json_string):
    """
    Parses a JSON string and returns the corresponding Python object.
    Returns None if parsing fails.
    """
    if json_string is None:
        return None
    try:
        return json.loads(json_string)
    except (TypeError, json.JSONDecodeError) as e:
        print(f"Error decoding JSON in filter: {e} for string: {json_string}")
        return None # Or an empty dict {} depending on how you want to handle errors

app.jinja_env.filters['fromjson'] = from_json_filter
# --- End NEW ---


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

# Create database tables within the application context
with app.app_context():
    print("Checking/creating database tables...")
    try:
        db.create_all() 
        print("Database tables checked/created.")
    except Exception as e:
        print(f"❌ Error during db.create_all(): {e}")
        print("ℹ️ Note: In production, you might need to manage database creation/migration separately.")


# Global context processor for is_participant_view
@app.context_processor
def inject_view_mode():
    from flask import g
    # Ensure g.is_participant_view exists, default to False
    return dict(is_participant_view=getattr(g, 'is_participant_view', False))

# Before request handler to set the flag
@app.before_request
def set_participant_view_flag():
    from flask import request, g
    # Initialize g.is_participant_view if it doesn't exist for the current request context
    if not hasattr(g, 'is_participant_view'):
         g.is_participant_view = False
    
    # Specifically set it for the participant_summary endpoint
    if request.endpoint == 'results.participant_summary':
        view_mode = request.args.get('view_mode', 'admin')
        g.is_participant_view = (view_mode == 'participant')
    # You might want to reset it or handle it for other endpoints if needed,
    # but for now, this targets the specific case.


# CLI command to create admin user
import click
from werkzeug.security import generate_password_hash

@app.cli.command("create-admin")
@click.argument("username")
@click.password_option()
def create_admin(username, password):
    """Creates the initial admin user."""
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"Error: User '{username}' already exists.")
            return
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        print(f"Admin user '{username}' created successfully.")

