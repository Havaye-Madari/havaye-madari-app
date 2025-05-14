# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, session # Import session
from flask_login import login_user, logout_user, current_user, login_required
# Use absolute imports
from app.models import User
from app.forms import LoginForm

# Create Blueprint for authentication routes
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles the admin login page."""
    if current_user.is_authenticated:
        # Redirect logged-in users to the main index
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user) # Log the user in
            session.permanent = False # Expire session on browser close

            # --- REMOVED: Flash message for successful login ---
            # flash('شما با موفقیت وارد شدید.', 'success')
            # --- End REMOVED ---

            next_page = request.args.get('next')
            # Redirect to the originally requested page or the main index
            return redirect(next_page or url_for('main.index'))
        else:
            flash('نام کاربری یا رمز عبور نامعتبر است.', 'danger')

    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """Logs the current user out."""
    logout_user()
    flash('شما با موفقیت خارج شدید.', 'info') # Keep logout message
    return redirect(url_for('auth.login'))

