# app/routes/participant_view.py
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
# --- UPDATED: Use absolute imports ---
from app.models import Participant
from app.forms import ParticipantLoginForm
# --- End UPDATED ---

# Create Blueprint for participant view routes
participant_view_bp = Blueprint(
    'participant_view',
    __name__,
    url_prefix='/view',
    template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
)

@participant_view_bp.route('/my-results', methods=['GET', 'POST'])
def my_results_login():
    """
    Handles the login page for participants to view their results.
    """
    form = ParticipantLoginForm()
    if form.validate_on_submit():
        phone_number = form.phone.data
        print(f"Attempting login for phone: {phone_number}")

        # Check if participant exists
        participant = Participant.query.get(phone_number)

        if participant:
            print(f"Participant found: {participant.name}. Redirecting to results.")
            # Redirect to the results page with view_mode marker
            return redirect(url_for('results.participant_summary',
                                    phone=phone_number,
                                    view_mode='participant'))
        else:
            print(f"Participant not found for phone: {phone_number}")
            flash('شرکت‌کننده‌ای با این شماره تلفن یافت نشد.', 'warning')
            return render_template('participant_view/participant_login.html', form=form)

    # Render login form for GET or failed POST validation
    return render_template('participant_view/participant_login.html', form=form)

