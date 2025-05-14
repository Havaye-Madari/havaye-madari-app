# app/routes/participants.py
import os
import pandas as pd
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, send_from_directory, current_app)
from werkzeug.utils import secure_filename
import traceback
from io import BytesIO
from flask_login import login_required, current_user
from app.models import db, Participant, Measure, Score, Indicator, Axis
# --- UPDATED: Import InputRequired ---
from app.forms import ParticipantInfoForm, ScoreForm, UploadForm, AttachmentForm, BulkAttachmentForm
from sqlalchemy.orm import joinedload
from wtforms import FloatField
# --- InputRequired به جای DataRequired برای فیلدهای عددی که می‌توانند صفر باشند ---
from wtforms.validators import InputRequired, NumberRange # DataRequired حذف و InputRequired اضافه شد
from datetime import datetime


participants_bp = Blueprint('participants', __name__, url_prefix='/participants')

def get_active_scoreable_items():
    """Fetches active Measures and Indicators allowing direct score."""
    scoreable_items = []
    active_indicators = Indicator.query.options(
        joinedload(Indicator.axis),
        joinedload(Indicator.measures)
    ).filter(Indicator.is_active == True).order_by(Indicator.axis_id, Indicator.id).all()

    active_measures = Measure.query.options(
        joinedload(Measure.indicator).joinedload(Indicator.axis)
    ).filter(Measure.is_active == True).join(Measure.indicator).filter(Indicator.is_active == True).order_by(
        Indicator.axis_id, Measure.indicator_id, Measure.id
    ).all()

    for measure in active_measures:
        if measure.indicator and measure.indicator.axis:
            scoreable_items.append(measure)
        else:
            print(f"Warning: Skipping measure ID {measure.id} due to missing indicator/axis relationship.")

    for indicator in active_indicators:
        if indicator.allow_direct_score:
            if indicator.axis:
                scoreable_items.append(indicator)
            else:
                print(f"Warning: Skipping indicator ID {indicator.id} (allows direct score) due to missing axis relationship.")
    return scoreable_items

def get_hierarchical_name(item):
    """Generates a unique name like 'Axis / Indicator / Measure' or 'Axis / Indicator (مستقیم)'."""
    if isinstance(item, Measure):
        if item.indicator and item.indicator.axis:
            return f"{item.indicator.axis.name} / {item.indicator.name} / {item.name}"
        else:
            return f"خطا: سنجه {item.id} فاقد شاخص یا محور معتبر است"
    elif isinstance(item, Indicator):
        if item.axis:
            return f"{item.axis.name} / {item.name} (مستقیم)"
        else:
            return f"خطا: شاخص {item.id} فاقد محور معتبر است"
    return "آیتم نامشخص"


@participants_bp.route('/scores', methods=['GET', 'POST'])
@participants_bp.route('/scores/<string:phone>', methods=['GET', 'POST'])
@login_required
def manage_scores(phone=None):
    """Handles adding/editing participant scores. Requires admin login."""
    print(f"Accessing manage_scores with phone: {phone}, Method: {request.method}")
    participant = None
    existing_scores_dict = {}
    form_data_for_validation = request.form if request.method == 'POST' else None
    form_data_for_population = None

    if phone:
        participant = Participant.query.get(phone)
        if not participant:
            flash(f"شرکت‌کننده‌ای با شماره تلفن {phone} یافت نشد.", "warning")
            return redirect(url_for('participants.list_participants'))
        if request.method == 'GET':
            print(f"GET request for existing participant: {participant.name}")
            scores = Score.query.options(
                joinedload(Score.scored_measure).joinedload(Measure.indicator).joinedload(Indicator.axis),
                joinedload(Score.scored_indicator).joinedload(Indicator.axis)
            ).filter_by(participant_phone=phone).all()
            for score in scores:
                item = score.scored_measure if score.measure_id else score.scored_indicator
                if item:
                    field_name = get_hierarchical_name(item)
                    existing_scores_dict[field_name] = score.value
                else:
                    field_name = f"measure_{score.measure_id}" if score.measure_id else f"indicator_{score.indicator_id}"
                    existing_scores_dict[field_name] = score.value
            form_data_for_population = participant

    try:
        scoreable_items = get_active_scoreable_items()
    except Exception as e:
        flash(f"خطا در بارگذاری سنجه‌ها/شاخص‌های فعال: {e}", "danger")
        print(f"Error loading scoreable items: {e}")
        traceback.print_exc()
        scoreable_items = []

    participant_form = ParticipantInfoForm(formdata=form_data_for_validation, obj=form_data_for_population)

    class DynamicScoreForm(ScoreForm):
        pass

    item_name_map = {}
    if scoreable_items:
        for item in scoreable_items:
            field_label = get_hierarchical_name(item)
            field_name = field_label
            item_name_map[field_name] = item
            if "خطا:" not in field_label:
                # --- UPDATED: Use InputRequired instead of DataRequired ---
                setattr(DynamicScoreForm, field_name, FloatField(field_label, validators=[
                    InputRequired(message="امتیاز الزامی است و نمی‌تواند خالی باشد."), # Checks for presence of input
                    NumberRange(min=0, max=5, message="امتیاز باید عددی بین 0 و 5 باشد.")
                ]))
                # --- End UPDATED ---
            else:
                print(f"Skipping form field creation for item due to naming error: {item}")
    else:
        if request.method == 'GET' and not phone:
             flash("هیچ سنجه یا شاخص فعالی برای امتیازدهی یافت نشد. لطفاً ابتدا از بخش مدیریت ساختار، آیتم‌ها را تعریف و فعال کنید.", "warning")

    if request.method == 'POST':
        score_form = DynamicScoreForm(formdata=request.form)
    elif phone and request.method == 'GET':
        score_form = DynamicScoreForm(data=existing_scores_dict)
        print(f"Populating score form with data: {existing_scores_dict}")
    else:
        score_form = DynamicScoreForm()

    if request.method == 'POST':
        print("Processing POST request...")
        participant_form_post = ParticipantInfoForm(request.form)
        score_form_post = score_form

        participant_valid = participant_form_post.validate()
        # score_form_post.process(formdata=request.form) # Ensure data is processed for dynamic form
        score_valid = score_form_post.validate()

        print(f"Participant Form Valid: {participant_valid}, Errors: {participant_form_post.errors}")
        print(f"Score Form Valid: {score_valid}, Errors: {score_form_post.errors}")

        if participant_valid and score_valid:
            submitted_phone = participant_form_post.phone.data
            submitted_name = participant_form_post.name.data

            if not phone:
                existing_participant = Participant.query.get(submitted_phone)
                if existing_participant:
                    flash(f"شرکت‌کننده‌ای با شماره تلفن {submitted_phone} از قبل وجود دارد.", "warning")
                    return render_template('participants/add_scores.html',
                                           participant_form=participant_form_post,
                                           score_form=score_form_post,
                                           editing=False,
                                           scoreable_items=scoreable_items,
                                           item_name_map=item_name_map)
                else:
                    participant = Participant(phone=submitted_phone, name=submitted_name)
                    db.session.add(participant)
            else:
                if not participant or participant.phone != submitted_phone:
                    flash("خطا: تلاش برای ویرایش شرکت‌کننده نامعتبر.", "danger")
                    return redirect(url_for('participants.list_participants'))
                if participant.name != submitted_name:
                    participant.name = submitted_name

            if not participant:
                flash("خطای داخلی: اطلاعات شرکت‌کننده یافت نشد.", "danger")
                return render_template('participants/add_scores.html',
                                       participant_form=participant_form_post,
                                       score_form=score_form_post,
                                       editing=bool(phone),
                                       scoreable_items=scoreable_items,
                                       item_name_map=item_name_map)

            current_participant_phone = participant.phone
            print(f"Processing scores for participant: {current_participant_phone}")

            for field_name, item in item_name_map.items():
                score_value = None
                target_measure_id = None
                target_indicator_id = None

                if isinstance(item, Measure):
                    target_measure_id = item.id
                elif isinstance(item, Indicator):
                    target_indicator_id = item.id
                else:
                    continue

                if hasattr(score_form_post, field_name):
                    # For FloatField, .data will be a float (e.g., 0.0) or None if conversion fails or input is empty
                    field_obj = getattr(score_form_post, field_name)
                    if field_obj.data is not None: # Check if data is not None (0.0 is not None)
                        score_value = field_obj.data
                    else:
                        # This case should ideally be caught by InputRequired if the field was truly empty.
                        # If InputRequired allows empty string that FloatField converts to None,
                        # then we might need to re-evaluate. But typically InputRequired + FloatField is robust.
                        print(f"Warning: Field {field_name} data is None after processing for participant {current_participant_phone}.")
                        # If score_value remains None, we might skip or handle as an error.
                        # For now, if it's None, it means no valid float was entered.
                        # The validators should have caught this.
                        continue # Skip if no valid score was entered and processed.
                else:
                    print(f"Warning: Field {field_name} not found in score_form_post during POST.")
                    continue
                
                existing_score = Score.query.filter_by(
                    participant_phone=current_participant_phone,
                    measure_id=target_measure_id,
                    indicator_id=target_indicator_id
                ).first()

                if existing_score:
                    if existing_score.value != score_value:
                        existing_score.value = score_value
                        existing_score.timestamp = datetime.utcnow()
                        print(f"Updating score for {field_name} to {score_value}")
                    else:
                        print(f"Score for {field_name} unchanged ({score_value})")
                else:
                    new_score = Score(
                        value=score_value,
                        participant_phone=current_participant_phone,
                        measure_id=target_measure_id,
                        indicator_id=target_indicator_id,
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(new_score)
                    print(f"Adding new score for {field_name}: {score_value}")
            try:
                db.session.commit()
                flash('اطلاعات و امتیازات با موفقیت ذخیره شدند!', 'success')
                return redirect(url_for('participants.list_participants'))
            except Exception as e:
                db.session.rollback()
                flash(f'خطا در ذخیره اطلاعات در پایگاه داده: {e}', 'danger')
                print(f"Database commit error: {e}")
                traceback.print_exc()
                return render_template('participants/add_scores.html',
                                       participant_form=participant_form_post,
                                       score_form=score_form_post,
                                       editing=bool(phone),
                                       scoreable_items=scoreable_items,
                                       item_name_map=item_name_map)
        else:
            error_messages = []
            if not participant_valid:
                error_messages.append('خطاهای فرم اطلاعات شرکت‌کننده:')
                for field, errors in participant_form_post.errors.items():
                    label_text = getattr(getattr(participant_form_post, field), 'label', None)
                    label = label_text.text if label_text else field.capitalize()
                    error_messages.append(f"- {label}: {', '.join(errors)}")
            if not score_valid:
                error_messages.append('خطاهای فرم امتیازات:')
                for field_name_error, errors in score_form_post.errors.items():
                    field_obj_error = getattr(score_form_post, field_name_error)
                    label_text_error = getattr(field_obj_error, 'label', None)
                    label_error = label_text_error.text if label_text_error else field_name_error
                    error_messages.append(f"- {label_error}: {', '.join(errors)}")

            flash('\n'.join(error_messages), 'warning')
            return render_template('participants/add_scores.html',
                                   participant_form=participant_form_post,
                                   score_form=score_form_post,
                                   editing=bool(phone),
                                   scoreable_items=scoreable_items,
                                   item_name_map=item_name_map)

    return render_template('participants/add_scores.html',
                           participant_form=participant_form,
                           score_form=score_form,
                           editing=bool(phone),
                           scoreable_items=scoreable_items,
                           item_name_map=item_name_map)


@participants_bp.route('/upload-scores', methods=['GET', 'POST'])
@login_required
def upload_scores():
    """Handles uploading scores from an Excel or CSV file. Requires admin login."""
    form = UploadForm()
    if form.validate_on_submit():
        file = form.excel_file.data
        filename = file.filename
        try:
            print(f"--- Starting Score Upload: {filename} ---")
            dtype_spec = {'شماره تلفن': str}
            if filename.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl', header=0, dtype=dtype_spec)
            elif filename.endswith('.csv'):
                try:
                    df = pd.read_csv(file, encoding='utf-8', header=0, dtype=dtype_spec)
                except UnicodeDecodeError:
                    df = pd.read_csv(file, encoding='windows-1256', header=0, dtype=dtype_spec)
            else:
                flash('فرمت فایل نامعتبر است. فقط .xlsx یا .csv مجاز است.', 'danger')
                return redirect(url_for('participants.upload_scores'))

            print(f"File read successfully. Shape: {df.shape}")
            df.columns = [str(col).strip() for col in df.columns]

            scoreable_items = get_active_scoreable_items()
            item_hierarchical_name_to_target = {
                get_hierarchical_name(item): ('measure' if isinstance(item, Measure) else 'indicator', item.id)
                for item in scoreable_items if "خطا:" not in get_hierarchical_name(item)
            }
            print(f"Scoreable items map (Hierarchical Name -> Target): {item_hierarchical_name_to_target}")

            required_cols = ['شماره تلفن', 'نام']
            missing_required = [col for col in required_cols if col not in df.columns]
            if missing_required:
                flash(f'فایل آپلود شده فاقد ستون‌های الزامی است: {", ".join(missing_required)}.', 'danger')
                return redirect(url_for('participants.upload_scores'))

            score_columns_in_file = {}
            unknown_columns = []
            for col_name in df.columns:
                if col_name in required_cols:
                    continue
                if col_name in item_hierarchical_name_to_target:
                    score_columns_in_file[col_name] = item_hierarchical_name_to_target[col_name]
                else:
                    unknown_columns.append(col_name)

            if not score_columns_in_file:
                 flash('هیچ ستون امتیازی منطبق با نام کامل سنجه‌ها یا شاخص‌های فعال در فایل یافت نشد.', 'warning')
            if unknown_columns:
                flash(f'هشدار: ستون‌های زیر نادیده گرفته شدند: {", ".join(unknown_columns)}', 'warning')
            print(f"Score columns identified in file (using hierarchical names): {score_columns_in_file}")

            processed_count = 0
            error_count = 0
            commit_successful = True
            row_errors = []
            participant_added_in_loop = False

            for index, row in df.iterrows():
                row_num = index + 2
                row_has_error = False
                try:
                    phone_raw = row.get('شماره تلفن')
                    name_raw = row.get('نام')
                    phone = str(phone_raw).strip() if pd.notna(phone_raw) else None
                    name = str(name_raw).strip() if pd.notna(name_raw) else None

                    if not phone or not name:
                        msg = f"ردیف {row_num}: شماره تلفن ('{phone_raw}') یا نام ('{name_raw}') خالی است."
                        print(f"Skipping: {msg}")
                        row_errors.append(msg)
                        error_count += 1; row_has_error = True
                        continue
                    if not phone.startswith('0') or not phone.isdigit():
                        msg = f"ردیف {row_num}: فرمت شماره تلفن '{phone}' نامعتبر است."
                        print(f"Skipping: {msg}")
                        row_errors.append(msg)
                        error_count += 1; row_has_error = True
                        continue

                    participant = Participant.query.get(phone)
                    if not participant:
                        participant = Participant(phone=phone, name=name)
                        db.session.add(participant)
                        participant_added_in_loop = True
                        print(f"Row {row_num}: Adding participant {name} ({phone})")
                    elif participant.name != name:
                        participant.name = name
                        print(f"Row {row_num}: Updating name for {phone} to {name}")

                    for col_name, target_info in score_columns_in_file.items():
                        target_type, target_id = target_info
                        score_raw = row.get(col_name)

                        if pd.isna(score_raw) or str(score_raw).strip() == '':
                            # اگر امتیاز خالی است، آن را صفر در نظر بگیرید یا نادیده بگیرید
                            # در اینجا، برای اینکه با DataRequired سازگار باشد، اگر خالی است، خطای اعتبارسنجی نمی‌دهیم
                            # اما اگر می‌خواهید حتما عددی وارد شود (حتی صفر)، باید این منطق را تغییر دهید
                            # یا اینکه فایل اکسل باید حتما شامل 0 باشد نه سلول خالی
                            # با فرض اینکه سلول خالی به معنی عدم امتیازدهی برای آن آیتم است:
                            # اگر می‌خواهید سلول خالی به معنی صفر باشد، score_value = 0.0
                            # در اینجا فرض می‌کنیم خالی یعنی امتیازی برای آن آیتم ثبت نشده است.
                            # اگر میخواهید خالی به معنی صفر باشد:
                            # score_value = 0.0
                            # else:
                            #     try: score_value = float(score_raw) ...
                            # برای سادگی، فعلا خالی را نادیده می‌گیریم (امتیازی ثبت نمی‌شود)
                            # اگر می‌خواهید خالی، صفر تلقی شود، کد زیر را تغییر دهید:
                            # if pd.isna(score_raw) or str(score_raw).strip() == '':
                            #     score_value = 0.0
                            # else:
                            #     try: ...
                            print(f"Row {row_num}, Col '{col_name}': Score is empty, skipping score entry for this item.")
                            continue # Skip if score is empty

                        try:
                            score_value = float(score_raw) # این شامل 0.0 هم می‌شود
                            if not (0 <= score_value <= 5):
                                msg = f"ردیف {row_num}, ستون '{col_name}': امتیاز {score_value} خارج از محدوده مجاز (0-5) است."
                                print(f"Error: {msg}")
                                row_errors.append(msg)
                                error_count += 1; row_has_error = True
                                continue
                            
                            target_measure_id = target_id if target_type == 'measure' else None
                            target_indicator_id = target_id if target_type == 'indicator' else None
                            existing_score = Score.query.filter_by(participant_phone=phone, measure_id=target_measure_id, indicator_id=target_indicator_id).first()
                            if existing_score:
                                if existing_score.value != score_value:
                                    existing_score.value = score_value
                                    existing_score.timestamp = datetime.utcnow()
                                    print(f"Row {row_num}, Col '{col_name}': Updating score to {score_value}")
                            else:
                                new_score = Score(value=score_value, participant_phone=phone, measure_id=target_measure_id, indicator_id=target_indicator_id, timestamp=datetime.utcnow())
                                db.session.add(new_score)
                                print(f"Row {row_num}, Col '{col_name}': Adding score {score_value}")
                        except (ValueError, TypeError):
                            msg = f"ردیف {row_num}, ستون '{col_name}': فرمت امتیاز '{score_raw}' نامعتبر است (باید عدد باشد)."
                            print(f"Error: {msg}")
                            row_errors.append(msg)
                            error_count += 1; row_has_error = True
                            continue
                    if not row_has_error:
                        processed_count += 1
                except Exception as row_e:
                    msg = f"ردیف {row_num}: خطای غیرمنتظره در پردازش ردیف - {row_e}"
                    print(f"Critical error: {msg}")
                    traceback.print_exc()
                    row_errors.append(msg)
                    error_count += 1; row_has_error = True
                    commit_successful = False; break
            
            print(f"\n--- Upload Finished --- Processed: {processed_count}, Errors: {error_count}")
            if commit_successful:
                 if processed_count > 0 or participant_added_in_loop or error_count > 0: # Commit if any change or error to report
                     try:
                         db.session.commit()
                         if processed_count > 0 or participant_added_in_loop:
                             flash(f'{processed_count} ردیف با موفقیت پردازش و تغییرات ذخیره شد.', 'success')
                         if error_count > 0:
                             error_list_html = "<ul class='text-start ps-4' style='max-height: 200px; overflow-y: auto;'>" + "".join([f"<li>{err}</li>" for err in row_errors]) + "</ul>"
                             flash(f'پردازش فایل با {error_count} خطا/هشدار مواجه شد. جزئیات:{error_list_html}', 'warning')
                     except Exception as commit_error:
                         db.session.rollback()
                         flash(f'خطا در ذخیره نهایی: {commit_error}', 'danger')
                         print(f"Final commit error: {commit_error}")
                         traceback.print_exc()
                 else:
                     flash('تغییری برای ذخیره یافت نشد یا فایل خالی بود.', 'info')
            else:
                 db.session.rollback()
                 error_list_html = "<ul class='text-start ps-4' style='max-height: 200px; overflow-y: auto;'>" + "".join([f"<li>{err}</li>" for err in row_errors]) + "</ul>"
                 flash(f'پردازش فایل با خطای جدی متوقف شد. هیچ تغییری ذخیره نشد. خطاها:{error_list_html}', 'danger')
            return redirect(url_for('participants.list_participants'))
        except ImportError:
            flash('خطا: کتابخانه pandas و openpyxl را نصب کنید.', 'danger')
            return redirect(url_for('participants.upload_scores'))
        except Exception as e:
            db.session.rollback()
            flash(f'خطای غیرمنتظره در پردازش فایل: {e}', 'danger')
            print(f"File processing error: {e}")
            traceback.print_exc()
            return redirect(url_for('participants.upload_scores'))
    return render_template('participants/upload_scores.html', form=form)


@participants_bp.route('/download-score-template')
@login_required
def download_score_template():
    try:
        print("--- Generating Score Template ---")
        scoreable_items = get_active_scoreable_items()
        headers = ['شماره تلفن', 'نام']
        hierarchical_item_names = []
        for item in scoreable_items:
            h_name = get_hierarchical_name(item)
            if "خطا:" not in h_name and h_name not in hierarchical_item_names:
                hierarchical_item_names.append(h_name)
        headers.extend(sorted(hierarchical_item_names))
        print(f"Template Headers: {headers}")
        df = pd.DataFrame(columns=headers)
        sample_data = {h: '' for h in headers}
        sample_data['شماره تلفن'] = '09123456789'
        sample_data['نام'] = 'نام نمونه شرکت کننده'
        for name in hierarchical_item_names:
            sample_data[name] = 0.0 # نمونه امتیاز صفر
        df = pd.concat([df, pd.DataFrame([sample_data])], ignore_index=True)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='امتیازات')
            worksheet = writer.sheets['امتیازات']
            for idx, col in enumerate(df):
                series = df[col]
                max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
                col_letter = chr(65 + idx)
                worksheet.column_dimensions[col_letter].width = max_len
        output.seek(0)
        print("Template generated successfully.")
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='score_upload_template.xlsx')
    except Exception as e:
        print(f"Error generating score template: {e}")
        traceback.print_exc()
        flash("خطا در تولید فایل نمونه اکسل.", "danger")
        return redirect(url_for('participants.list_participants'))


@participants_bp.route('/list')
@login_required
def list_participants():
     page = request.args.get('page', 1, type=int)
     try:
          participants_pagination = Participant.query.order_by(Participant.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
     except Exception as e:
         flash(f"خطا در بارگذاری لیست شرکت‌کنندگان: {e}", "danger")
         print(f"Error loading participants list: {e}")
         traceback.print_exc()
         participants_pagination = None
     return render_template('participants/list.html', participants_pagination=participants_pagination)

@participants_bp.route('/<string:phone>/delete', methods=['POST'])
@login_required
def delete_participant(phone):
    participant = Participant.query.get_or_404(phone)
    participant_name = participant.name
    try:
        if participant.attachment_filename:
            try:
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"Deleted attachment file: {filepath}")
            except Exception as file_e:
                print(f"Error deleting attachment file {participant.attachment_filename}: {file_e}")
                flash(f'هشدار: خطا در حذف فایل پیوست برای {participant_name}.', 'warning')
        db.session.delete(participant)
        db.session.commit()
        flash(f'شرکت‌کننده "{participant_name}" و تمام اطلاعات او حذف شدند.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف "{participant_name}": {e}', 'danger')
        print(f"Error deleting {phone}: {e}")
        traceback.print_exc()
    return redirect(url_for('participants.list_participants'))

@participants_bp.route('/delete-all', methods=['POST'])
@login_required
def delete_all_participants():
    try:
        participants_with_attachments = Participant.query.filter(Participant.attachment_filename.isnot(None)).all()
        deleted_files_count = 0
        for participant in participants_with_attachments:
            if participant.attachment_filename:
                try:
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                        deleted_files_count += 1
                except Exception as file_e:
                    print(f"Error deleting attachment file {participant.attachment_filename} during delete-all: {file_e}")
        print(f"Deleted {deleted_files_count} attachment files during delete-all.")
        num_scores_deleted = db.session.query(Score).delete()
        num_participants_deleted = db.session.query(Participant).delete()
        db.session.commit()
        flash(f'تمام {num_participants_deleted} شرکت‌کننده، {num_scores_deleted} امتیاز و {deleted_files_count} فایل پیوست حذف شدند.', 'success')
        print(f"DELETED ALL PARTICIPANTS ({num_participants_deleted}), SCORES ({num_scores_deleted}), and ATTACHMENTS ({deleted_files_count})")
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف تمام شرکت‌کنندگان: {e}', 'danger')
        print(f"Error deleting all: {e}")
        traceback.print_exc()
    return redirect(url_for('participants.list_participants'))


def get_participant_scores(phone):
    try:
        scores = Score.query.filter_by(participant_phone=phone).options(joinedload(Score.scored_measure).joinedload(Measure.indicator).joinedload(Indicator.axis), joinedload(Score.scored_indicator).joinedload(Indicator.axis)).all()
        score_dict = {}
        for score in scores:
             item = score.scored_measure if score.measure_id else score.scored_indicator
             if item:
                 field_name = get_hierarchical_name(item)
                 score_dict[field_name] = score.value
             else:
                 field_name = f"measure_{score.measure_id}" if score.measure_id else f"indicator_{score.indicator_id}"
                 score_dict[field_name] = score.value
        return score_dict
    except Exception as e:
        print(f"Error fetching scores for participant {phone}: {e}")
        traceback.print_exc()
        return {}


@participants_bp.route('/manage-attachment/<string:phone>', methods=['GET', 'POST'])
@login_required
def manage_attachment(phone):
    participant = Participant.query.get_or_404(phone)
    form = AttachmentForm()
    if form.validate_on_submit():
        file = form.attachment.data
        try:
            original_filename = secure_filename(file.filename)
            if not original_filename:
                 flash('نام فایل پیوست نامعتبر است.', 'danger')
                 return redirect(url_for('participants.manage_attachment', phone=phone))
            _ , file_extension = os.path.splitext(original_filename)
            file_extension = file_extension.lower().lstrip('.')
            new_server_filename = f"{participant.phone}.{file_extension}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], new_server_filename)
            if participant.attachment_filename and participant.attachment_filename != new_server_filename:
                old_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                        print(f"Deleted old attachment: {old_filepath} for participant {phone}")
                    except Exception as e:
                        print(f"Error deleting old attachment {old_filepath} for {phone}: {e}")
                        flash('خطا در حذف فایل پیوست قبلی.', 'warning')
            file.save(save_path)
            print(f"Saved new attachment as: {save_path} for participant {phone}")
            participant.attachment_filename = new_server_filename
            db.session.commit()
            flash('فایل پیوست با موفقیت آپلود و ذخیره شد.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در آپلود فایل پیوست: {e}', 'danger')
            print(f"Error uploading file for {phone}: {e}")
            traceback.print_exc()
        return redirect(url_for('participants.manage_attachment', phone=phone))
    return render_template('participants/manage_attachment.html', participant=participant, form=form)


@participants_bp.route('/delete-attachment/<string:phone>', methods=['POST'])
@login_required
def delete_attachment(phone):
    participant = Participant.query.get_or_404(phone)
    filename_to_delete = participant.attachment_filename
    if not filename_to_delete:
        flash('این شرکت‌کننده در حال حاضر فایل پیوستی ندارد.', 'info')
        return redirect(url_for('participants.manage_attachment', phone=phone))
    try:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename_to_delete)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted attachment file from disk: {filepath}")
        else:
            print(f"Attachment file not found on disk ({filepath}), but removing DB record for participant {phone}.")
            flash('فایل پیوست در مسیر ذخیره‌سازی یافت نشد، اما رکورد آن از پایگاه داده حذف گردید.', 'warning')
        participant.attachment_filename = None
        db.session.commit()
        flash('فایل پیوست با موفقیت حذف شد.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف فایل پیوست: {e}', 'danger')
        print(f"Error deleting attachment for {phone}: {e}")
        traceback.print_exc()
    return redirect(url_for('participants.manage_attachment', phone=phone))


@participants_bp.route('/view-attachment/<filename>')
def view_attachment(filename):
    filename = secure_filename(filename)
    print(f"Attempting to serve file: {filename} from {current_app.config['UPLOAD_FOLDER']}")
    try:
        return send_from_directory(
            current_app.config['UPLOAD_FOLDER'],
            filename,
            as_attachment=False
        )
    except FileNotFoundError:
        flash('فایل پیوست مورد نظر یافت نشد.', 'danger')
        if current_user.is_authenticated and not current_user.is_anonymous:
             return redirect(url_for('participants.list_participants'))
        else:
             return redirect(url_for('participant_view.my_results_login'))
    except Exception as e:
        flash(f'خطا در نمایش فایل پیوست: {e}', 'danger')
        print(f"Error serving file {filename}: {e}")
        if current_user.is_authenticated and not current_user.is_anonymous:
             return redirect(url_for('participants.list_participants'))
        else:
             return redirect(url_for('participant_view.my_results_login'))


@participants_bp.route('/bulk-upload-attachments', methods=['GET', 'POST'])
@login_required
def bulk_upload_attachments():
    form = BulkAttachmentForm()
    if request.method == 'POST':
        files = request.files.getlist(form.attachments.name)
        if not files or all(f.filename == '' for f in files):
            flash('هیچ فایلی برای آپلود انتخاب نشده است.', 'warning')
            return redirect(url_for('participants.bulk_upload_attachments'))

        successful_uploads = 0
        failed_uploads = 0
        skipped_files_info = []
        updated_participants_info = []
        allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png', 'gif'}

        for file_storage in files:
            if file_storage and file_storage.filename:
                original_filename = file_storage.filename
                try:
                    filename_no_ext, file_extension_with_dot = os.path.splitext(original_filename)
                    file_extension = file_extension_with_dot.lower().lstrip('.')
                    if file_extension not in allowed_extensions:
                        skipped_files_info.append(f"فایل '{original_filename}': پسوند نامعتبر ('{file_extension}').")
                        failed_uploads += 1
                        continue
                    participant_phone = filename_no_ext.strip()
                    participant = Participant.query.get(participant_phone)
                    if participant:
                        new_server_filename = f"{participant_phone}.{file_extension}"
                        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], new_server_filename)
                        if participant.attachment_filename and participant.attachment_filename != new_server_filename:
                            old_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                            if os.path.exists(old_filepath):
                                try:
                                    os.remove(old_filepath)
                                except Exception as e_del:
                                    print(f"Bulk: Error deleting old attachment {participant.attachment_filename} for {participant_phone}: {e_del}")
                        file_storage.save(save_path)
                        participant.attachment_filename = new_server_filename
                        updated_participants_info.append(f"شرکت‌کننده '{participant.name}' ({participant_phone}) با فایل '{new_server_filename}'.")
                        successful_uploads += 1
                    else:
                        skipped_files_info.append(f"فایل '{original_filename}': شرکت‌کننده‌ای با شماره '{participant_phone}' یافت نشد.")
                        failed_uploads += 1
                except Exception as e:
                    skipped_files_info.append(f"فایل '{original_filename}': خطا در پردازش - {str(e)[:100]}.")
                    print(f"Error processing file {original_filename} in bulk upload: {e}")
                    traceback.print_exc()
                    failed_uploads += 1
        try:
            if successful_uploads > 0:
                db.session.commit()
                flash(f"{successful_uploads} فایل پیوست با موفقیت آپلود و تخصیص داده شد.", "success")
                if updated_participants_info:
                     flash("جزئیات موفقیت آمیز:\n" + "\n".join(updated_participants_info), "info")
            elif failed_uploads == 0 and not skipped_files_info :
                 pass
            else:
                 db.session.rollback()

            if failed_uploads > 0 and skipped_files_info:
                flash(f"{failed_uploads} فایل با خطا مواجه شد یا نادیده گرفته شد.", "warning")
                flash("جزئیات خطاها/فایل‌های نادیده گرفته شده:\n" + "\n".join(skipped_files_info), "info")
        except Exception as e_commit:
            db.session.rollback()
            flash(f"خطای پایگاه داده هنگام ذخیره نهایی پیوست‌ها: {e_commit}", "danger")
            print(f"Database commit error after bulk attachment upload: {e_commit}")
            traceback.print_exc()
        return redirect(url_for('participants.list_participants'))
    return render_template('participants/bulk_upload_attachments.html', form=form)
