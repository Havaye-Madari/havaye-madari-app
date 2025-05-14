# app/models.py
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Initialize SQLAlchemy extension
db = SQLAlchemy()

# --- User Model for Admin Login ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# --- Axis Model ---
class Axis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    indicators = db.relationship('Indicator', backref='axis', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Axis {self.name}>'

# --- Indicator Model ---
class Indicator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    axis_id = db.Column(db.Integer, db.ForeignKey('axis.id'), nullable=False)
    measures = db.relationship('Measure', backref='indicator', lazy=True, cascade="all, delete-orphan")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    allow_direct_score = db.Column(db.Boolean, default=False, nullable=False)
    direct_scores = db.relationship('Score', backref='scored_indicator', lazy='dynamic',
                                    primaryjoin="and_(Indicator.id==Score.indicator_id, Score.measure_id==None)",
                                    cascade="all, delete-orphan")

    def __repr__(self):
        status = "Active" if self.is_active else "Inactive"
        direct = "| Direct Score" if self.allow_direct_score else ""
        return f'<Indicator {self.name} ({status}{direct})>'

    def update_direct_score_allowance(self):
        if not self.is_active:
             self.allow_direct_score = False
             return
        active_measures_exist = db.session.query(Measure.id)\
                                  .filter(Measure.indicator_id == self.id, Measure.is_active == True)\
                                  .first() is not None
        self.allow_direct_score = not active_measures_exist
        # print(f"Indicator '{self.name}': allow_direct_score set to {self.allow_direct_score}") # Debug log


# --- Measure Model ---
class Measure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey('indicator.id'), nullable=False)
    scores = db.relationship('Score', backref='scored_measure', lazy='dynamic',
                             primaryjoin="and_(Measure.id==Score.measure_id, Score.indicator_id==None)",
                             cascade="all, delete-orphan")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        status = "Active" if self.is_active else "Inactive"
        return f'<Measure {self.name} ({status})>'

# --- Participant Model ---
class Participant(db.Model):
    phone = db.Column(db.String(15), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    scores = db.relationship('Score', backref='participant', lazy='dynamic', cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # --- NEW: Field to store the attachment filename ---
    attachment_filename = db.Column(db.String(255), nullable=True) # Store only the filename

    def __repr__(self):
        return f'<Participant {self.name} ({self.phone})>'

# --- Score Model ---
class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Float, nullable=False)
    participant_phone = db.Column(db.String(15), db.ForeignKey('participant.phone'), nullable=False)
    measure_id = db.Column(db.Integer, db.ForeignKey('measure.id'), nullable=True)
    indicator_id = db.Column(db.Integer, db.ForeignKey('indicator.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        CheckConstraint(
            '(measure_id IS NOT NULL AND indicator_id IS NULL) OR (measure_id IS NULL AND indicator_id IS NOT NULL)',
            name='score_target_check'
        ),
    )

    def __repr__(self):
        target_type = "Measure" if self.measure_id else "Indicator"
        target_id = self.measure_id if self.measure_id else self.indicator_id
        return f'<Score {self.value} for {target_type} {target_id} by Participant {self.participant_phone}>'


# --- Setting Model ---
class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Setting {self.key}>'
