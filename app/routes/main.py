import os
from flask import Blueprint, render_template
from flask_login import login_required
# --- No relative imports like ..models or ..forms needed here usually ---

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    # Render the index page from the 'main' subdirectory within the main 'templates' folder
    return render_template('main/index.html')
