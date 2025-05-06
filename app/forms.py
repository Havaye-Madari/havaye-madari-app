# app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, FloatField, SelectField, SubmitField, HiddenField, BooleanField, PasswordField
from wtforms.validators import DataRequired, NumberRange, Optional, Regexp
# --- UPDATED: Import FileField and FileAllowed ---
from flask_wtf.file import FileField, FileAllowed, FileRequired
# --- End UPDATED ---
from app.models import db, Axis, Indicator # Import necessary models for choices

# --- Helper Functions to Populate Select Fields ---
def get_axes_choices():
    """Fetches all axes for use in SelectFields."""
    choices = [(0, '--- انتخاب محور ---')]
    try:
        choices.extend([(axis.id, axis.name) for axis in Axis.query.order_by(Axis.name).all()])
    except Exception as e:
        print(f"Error fetching axes: {e}")
        pass
    return choices

def get_indicators_choices():
    """Fetches all indicators for use in SelectFields, including axis name."""
    choices = [(0, '--- انتخاب شاخص ---')]
    try:
        indicators = db.session.query(Indicator, Axis.name.label('axis_name')) \
                        .join(Axis, Axis.id == Indicator.axis_id) \
                        .order_by(Axis.name, Indicator.name).all()
        choices.extend([(ind.Indicator.id, f"{ind.axis_name} / {ind.Indicator.name}") for ind in indicators])
    except Exception as e:
        print(f"Error fetching indicators: {e}")
        pass
    return choices


# --- Forms for Managing Hierarchy Manually ---
class AxisForm(FlaskForm):
    id = HiddenField('Axis ID')
    name = StringField('نام محور', validators=[DataRequired(message="نام محور الزامی است.")])
    description = TextAreaField('توضیحات (اختیاری)')
    submit_axis = SubmitField('ذخیره محور')

class IndicatorForm(FlaskForm):
    id = HiddenField('Indicator ID')
    axis_id = SelectField('محور مرتبط', coerce=int, validators=[DataRequired(message="انتخاب محور الزامی است.")])
    name = StringField('نام شاخص', validators=[DataRequired(message="نام شاخص الزامی است.")])
    weight = FloatField('وزن (0 تا 1)', validators=[DataRequired(message="وزن الزامی است."), NumberRange(min=0, max=1, message="وزن باید بین 0 و 1 باشد.")])
    description = TextAreaField('توضیحات (اختیاری)')
    is_active = BooleanField('فعال', default=True)
    submit_indicator = SubmitField('ذخیره شاخص')

    def __init__(self, *args, **kwargs):
        super(IndicatorForm, self).__init__(*args, **kwargs)
        self.axis_id.choices = get_axes_choices()

class MeasureForm(FlaskForm):
    id = HiddenField('Measure ID')
    indicator_id = SelectField('شاخص مرتبط', coerce=int, validators=[DataRequired(message="انتخاب شاخص الزامی است.")])
    name = StringField('نام سنجه', validators=[DataRequired(message="نام سنجه الزامی است.")])
    weight = FloatField('وزن (0 تا 1)', validators=[DataRequired(message="وزن الزامی است."), NumberRange(min=0, max=1, message="وزن باید بین 0 و 1 باشد.")])
    description = TextAreaField('توضیحات (اختیاری)')
    is_active = BooleanField('فعال', default=True)
    submit_measure = SubmitField('ذخیره سنجه')

    def __init__(self, *args, **kwargs):
        super(MeasureForm, self).__init__(*args, **kwargs)
        self.indicator_id.choices = get_indicators_choices()


# --- Forms for Participant Scores ---
class ScoreForm(FlaskForm):
    submit = SubmitField('ذخیره امتیازها')

class UploadForm(FlaskForm):
    excel_file = FileField('فایل اکسل یا CSV شرکت‌کنندگان', validators=[
        DataRequired(message="انتخاب فایل الزامی است."),
        FileAllowed(['xlsx', 'csv'], 'فقط فایل‌های Excel (.xlsx) و CSV (.csv) مجاز هستند!')
    ])
    submit = SubmitField('آپلود و پردازش فایل')

class ParticipantInfoForm(FlaskForm):
    phone = StringField('شماره تلفن', validators=[DataRequired(message="شماره تلفن الزامی است.")])
    name = StringField('نام و نام خانوادگی', validators=[DataRequired(message="نام الزامی است.")])

# --- Form for Uploading Hierarchy ---
class UploadHierarchyForm(FlaskForm):
    excel_file = FileField('فایل اکسل ساختار ارزیابی', validators=[
        DataRequired(message="انتخاب فایل الزامی است."),
        FileAllowed(['xlsx'], 'فقط فایل‌های Excel (.xlsx) مجاز هستند!')
    ])
    submit_upload = SubmitField('آپلود و پردازش ساختار')


# --- Form for Participant Login ---
class ParticipantLoginForm(FlaskForm):
    phone = StringField('شماره تلفن همراه', validators=[
        DataRequired(message="وارد کردن شماره تلفن الزامی است."),
        Regexp(r'^09\d{9}$', message="فرمت شماره تلفن نامعتبر است (مثال: 09123456789).")
    ])
    submit = SubmitField('مشاهده نتایج')

# --- Form for Editing Help Text ---
class HelpTextForm(FlaskForm):
    help_text = TextAreaField('متن راهنمای صفحه نتایج',
                              render_kw={'rows': 15, 'style': 'font-family: Vazirmatn, sans-serif;'})
    submit = SubmitField('ذخیره متن راهنما')


# --- Admin Login Form ---
class LoginForm(FlaskForm):
    username = StringField('نام کاربری', validators=[DataRequired(message="نام کاربری الزامی است.")])
    password = PasswordField('رمز عبور', validators=[DataRequired(message="رمز عبور الزامی است.")])
    submit = SubmitField('ورود به پنل مدیریت')

# --- NEW: Form for Uploading Participant Attachment ---
class AttachmentForm(FlaskForm):
    """Form for uploading an attachment for a participant."""
    # Use FileRequired to ensure a file is selected
    attachment = FileField('انتخاب فایل پیوست (PDF یا تصویر)', validators=[
        FileRequired(message="انتخاب فایل الزامی است."),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'pdf'], 'فقط فایل‌های تصویری (jpg, png, gif) یا PDF مجاز هستند!')
    ])
    submit = SubmitField('آپلود پیوست')
# --- End NEW ---
