# app/routes/participants.py
import os
import pandas as pd
# --- UPDATED: Import secure_filename, send_from_directory, current_app ---
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, send_from_directory, current_app)
from werkzeug.utils import secure_filename
# --- End UPDATED ---
from io import BytesIO
from flask_login import login_required
# Use absolute imports
from app.models import db, Participant, Measure, Score, Indicator, Axis
# --- UPDATED: Import AttachmentForm ---
from app.forms import ParticipantInfoForm, ScoreForm, UploadForm, AttachmentForm
# --- End UPDATED ---
from sqlalchemy.orm import joinedload, undefer
from wtforms import FloatField
from wtforms.validators import DataRequired, NumberRange
from datetime import datetime
import traceback

# Create Blueprint for participant routes
participants_bp = Blueprint('participants', __name__, url_prefix='/participants')

# --- Function to get active scoreable items ---
# (Function remains the same)
def get_active_scoreable_items():
    """Fetches active Measures and Indicators allowing direct score."""
    scoreable_items = []
    active_indicators = Indicator.query.options(joinedload(Indicator.axis), joinedload(Indicator.measures)).filter(Indicator.is_active == True).order_by(Indicator.axis_id, Indicator.id).all()
    active_measures = Measure.query.options(joinedload(Measure.indicator).joinedload(Indicator.axis)).filter(Measure.is_active == True).join(Measure.indicator).filter(Indicator.is_active == True).order_by(Indicator.axis_id, Measure.indicator_id, Measure.id).all()
    measure_indicator_ids = {m.indicator_id for m in active_measures if m.indicator}
    for measure in active_measures:
        if measure.indicator and measure.indicator.axis: scoreable_items.append(measure)
        else: print(f"Warning: Skipping measure ID {measure.id} due to missing relationship.")
    for indicator in active_indicators:
        if indicator.allow_direct_score:
             if indicator.axis: scoreable_items.append(indicator)
             else: print(f"Warning: Skipping indicator ID {indicator.id} due to missing axis relationship.")
    return scoreable_items

# --- Function to generate unique hierarchical name ---
# (Function remains the same)
def get_hierarchical_name(item):
    """Generates a unique name like 'Axis / Indicator / Measure' or 'Axis / Indicator (مستقیم)'."""
    if isinstance(item, Measure):
        if item.indicator and item.indicator.axis: return f"{item.indicator.axis.name} / {item.indicator.name} / {item.name}"
        else: return f"خطا: سنجه {item.id}"
    elif isinstance(item, Indicator):
        if item.axis: return f"{item.axis.name} / {item.name} (مستقیم)"
        else: return f"خطا: شاخص {item.id}"
    return "آیتم نامشخص"


# Combined route for adding new and editing existing participant scores
@participants_bp.route('/scores', methods=['GET', 'POST'])
@participants_bp.route('/scores/<string:phone>', methods=['GET', 'POST'])
@login_required
def manage_scores(phone=None):
    """Handles adding/editing participant scores. Requires admin login."""
    # (Code remains the same as previous version)
    print(f"Accessing manage_scores with phone: {phone}, Method: {request.method}")
    participant = None; existing_scores_dict = {}; form_data_for_validation = request.form if request.method == 'POST' else None; form_data_for_population = None
    if phone:
        participant = Participant.query.get(phone)
        if not participant: flash(f"شرکت‌کننده‌ای با شماره تلفن {phone} یافت نشد.", "warning"); return redirect(url_for('participants.list_participants'))
        if request.method == 'GET':
            print(f"GET request for existing participant: {participant.name}")
            scores = Score.query.options(joinedload(Score.scored_measure).joinedload(Measure.indicator).joinedload(Indicator.axis), joinedload(Score.scored_indicator).joinedload(Indicator.axis)).filter_by(participant_phone=phone).all()
            for score in scores:
                 item = score.scored_measure if score.measure_id else score.scored_indicator
                 if item: field_name = get_hierarchical_name(item); existing_scores_dict[field_name] = score.value
                 else: field_name = f"measure_{score.measure_id}" if score.measure_id else f"indicator_{score.indicator_id}"; existing_scores_dict[field_name] = score.value
            form_data_for_population = participant
    try: scoreable_items = get_active_scoreable_items()
    except Exception as e: flash(f"خطا در بارگذاری سنجه‌ها/شاخص‌های فعال: {e}", "danger"); print(f"Error loading scoreable items: {e}"); traceback.print_exc(); scoreable_items = []
    participant_form = ParticipantInfoForm(formdata=form_data_for_validation, obj=form_data_for_population)
    class DynamicScoreForm(ScoreForm): pass
    item_name_map = {}
    if scoreable_items:
        for item in scoreable_items:
            field_label = get_hierarchical_name(item); field_name = field_label; item_name_map[field_name] = item
            if "خطا:" not in field_label: setattr(DynamicScoreForm, field_name, FloatField(field_label, validators=[DataRequired(message="امتیاز الزامی است."), NumberRange(min=0, max=5, message="امتیاز باید بین 0 و 5 باشد.")]))
            else: print(f"Skipping form field creation for item due to naming error: {item}")
    else:
        if request.method == 'GET' and not phone: flash("هیچ سنجه یا شاخص فعالی برای امتیازدهی یافت نشد.", "warning")
    if request.method == 'POST': score_form = DynamicScoreForm(formdata=request.form)
    elif phone and request.method == 'GET': score_form = DynamicScoreForm(data=existing_scores_dict); print(f"Populating score form with data: {existing_scores_dict}")
    else: score_form = DynamicScoreForm()
    if request.method == 'POST':
        print("Processing POST request...")
        participant_form_post = ParticipantInfoForm(request.form); score_form_post = score_form
        participant_valid = participant_form_post.validate(); score_valid = score_form_post.validate()
        print(f"Participant Form Valid: {participant_valid}, Errors: {participant_form_post.errors}"); print(f"Score Form Valid: {score_valid}, Errors: {score_form_post.errors}")
        if participant_valid and score_valid:
            submitted_phone = participant_form_post.phone.data; submitted_name = participant_form_post.name.data
            if not phone:
                existing_participant = Participant.query.get(submitted_phone)
                if existing_participant: flash(f"شرکت‌کننده‌ای با شماره تلفن {submitted_phone} از قبل وجود دارد.", "warning"); return render_template('participants/add_scores.html', participant_form=participant_form_post, score_form=score_form_post, editing=False, scoreable_items=scoreable_items, item_name_map=item_name_map)
                else: participant = Participant(phone=submitted_phone, name=submitted_name); db.session.add(participant)
            else:
                 if not participant or participant.phone != submitted_phone: flash("خطا: تلاش برای ویرایش شرکت‌کننده نامعتبر.", "danger"); return redirect(url_for('participants.list_participants'))
                 if participant.name != submitted_name: participant.name = submitted_name
            if not participant: flash("خطای داخلی: اطلاعات شرکت‌کننده یافت نشد.", "danger"); return render_template('participants/add_scores.html', participant_form=participant_form_post, score_form=score_form_post, editing=bool(phone), scoreable_items=scoreable_items, item_name_map=item_name_map)
            current_participant_phone = participant.phone; print(f"Processing scores for participant: {current_participant_phone}")
            for field_name, item in item_name_map.items():
                score_value = None; target_measure_id = None; target_indicator_id = None
                if isinstance(item, Measure): target_measure_id = item.id
                elif isinstance(item, Indicator): target_indicator_id = item.id
                else: continue
                if hasattr(score_form_post, field_name): score_value = getattr(score_form_post, field_name).data
                else: print(f"Warning: Field {field_name} not found in score_form_post during POST."); continue
                existing_score = Score.query.filter_by(participant_phone=current_participant_phone, measure_id=target_measure_id, indicator_id=target_indicator_id).first()
                if existing_score:
                    if existing_score.value != score_value: existing_score.value = score_value; existing_score.timestamp = datetime.utcnow(); print(f"Updating score for {field_name} to {score_value}")
                    else: print(f"Score for {field_name} unchanged ({score_value})")
                else:
                    new_score = Score(value=score_value, participant_phone=current_participant_phone, measure_id=target_measure_id, indicator_id=target_indicator_id, timestamp=datetime.utcnow())
                    db.session.add(new_score); print(f"Adding new score for {field_name}: {score_value}")
            try: db.session.commit(); flash('اطلاعات و امتیازات با موفقیت ذخیره شدند!', 'success'); return redirect(url_for('participants.list_participants'))
            except Exception as e: db.session.rollback(); flash(f'خطا در ذخیره اطلاعات در پایگاه داده: {e}', 'danger'); print(f"Database commit error: {e}"); traceback.print_exc(); return render_template('participants/add_scores.html', participant_form=participant_form_post, score_form=score_form_post, editing=bool(phone), scoreable_items=scoreable_items, item_name_map=item_name_map)
        else:
             error_messages = [];
             if not participant_valid: error_messages.append('خطاهای فرم اطلاعات شرکت‌کننده:'); [error_messages.append(f"- {getattr(getattr(participant_form_post, field), 'label', None).text if getattr(getattr(participant_form_post, field), 'label', None) else field.capitalize()}: {', '.join(errors)}") for field, errors in participant_form_post.errors.items()]
             if not score_valid: error_messages.append('خطاهای فرم امتیازات:'); [error_messages.append(f"- {getattr(score_form_post, field).label.text if hasattr(getattr(score_form_post, field), 'label') else field}: {', '.join(errors)}") for field, errors in score_form_post.errors.items()]
             flash('\n'.join(error_messages), 'warning')
             return render_template('participants/add_scores.html', participant_form=participant_form_post, score_form=score_form_post, editing=bool(phone), scoreable_items=scoreable_items, item_name_map=item_name_map)
    return render_template('participants/add_scores.html', participant_form=participant_form, score_form=score_form, editing=bool(phone), scoreable_items=scoreable_items, item_name_map=item_name_map)


# --- Route for uploading participant scores via Excel/CSV ---
@participants_bp.route('/upload-scores', methods=['GET', 'POST'])
@login_required
def upload_scores():
    """Handles uploading scores from an Excel or CSV file. Requires admin login."""
    # (Code remains the same as previous version)
    form = UploadForm()
    if form.validate_on_submit():
        file = form.excel_file.data
        filename = file.filename
        try:
            print(f"--- Starting Score Upload: {filename} ---")
            dtype_spec = {'شماره تلفن': str}
            if filename.endswith('.xlsx'): df = pd.read_excel(file, engine='openpyxl', header=0, dtype=dtype_spec)
            elif filename.endswith('.csv'):
                try: df = pd.read_csv(file, encoding='utf-8', header=0, dtype=dtype_spec)
                except UnicodeDecodeError: df = pd.read_csv(file, encoding='windows-1256', header=0, dtype=dtype_spec)
            else: flash('فرمت فایل نامعتبر است. فقط .xlsx یا .csv مجاز است.', 'danger'); return redirect(url_for('participants.upload_scores'))
            print(f"File read successfully. Shape: {df.shape}"); df.columns = [str(col).strip() for col in df.columns]
            scoreable_items = get_active_scoreable_items()
            item_hierarchical_name_to_target = { get_hierarchical_name(item): ('measure' if isinstance(item, Measure) else 'indicator', item.id) for item in scoreable_items if "خطا:" not in get_hierarchical_name(item) }
            print(f"Scoreable items map (Hierarchical Name -> Target): {item_hierarchical_name_to_target}")
            required_cols = ['شماره تلفن', 'نام']; missing_required = [col for col in required_cols if col not in df.columns]
            if missing_required: flash(f'فایل آپلود شده فاقد ستون‌های الزامی است: {", ".join(missing_required)}.', 'danger'); return redirect(url_for('participants.upload_scores'))
            score_columns_in_file = {}; unknown_columns = []
            for col_name in df.columns:
                if col_name in required_cols: continue
                if col_name in item_hierarchical_name_to_target: score_columns_in_file[col_name] = item_hierarchical_name_to_target[col_name]
                else: unknown_columns.append(col_name)
            if not score_columns_in_file: flash('هیچ ستون امتیازی منطبق با نام کامل سنجه‌ها یا شاخص‌های فعال در فایل یافت نشد.', 'warning')
            if unknown_columns: flash(f'هشدار: ستون‌های زیر نادیده گرفته شدند: {", ".join(unknown_columns)}', 'warning')
            print(f"Score columns identified in file (using hierarchical names): {score_columns_in_file}")
            processed_count = 0; error_count = 0; commit_successful = True; row_errors = []
            for index, row in df.iterrows():
                row_num = index + 2; row_has_error = False; participant_added_in_loop = False
                try:
                    phone_raw = row.get('شماره تلفن'); name_raw = row.get('نام'); phone = str(phone_raw).strip() if pd.notna(phone_raw) else None; name = str(name_raw).strip() if pd.notna(name_raw) else None
                    if not phone or not name: msg = f"ردیف {row_num}: شماره تلفن ('{phone_raw}') یا نام ('{name_raw}') خالی است."; print(f"Skipping: {msg}"); row_errors.append(msg); error_count += 1; row_has_error = True; continue
                    if not phone.startswith('0') or not phone.isdigit(): msg = f"ردیف {row_num}: فرمت شماره تلفن '{phone}' نامعتبر است."; print(f"Skipping: {msg}"); row_errors.append(msg); error_count += 1; row_has_error = True; continue
                    participant = Participant.query.get(phone)
                    if not participant: participant = Participant(phone=phone, name=name); db.session.add(participant); participant_added_in_loop = True; print(f"Row {row_num}: Adding participant {name} ({phone})")
                    elif participant.name != name: participant.name = name; print(f"Row {row_num}: Updating name for {phone} to {name}")
                    for col_name, target_info in score_columns_in_file.items():
                        target_type, target_id = target_info; score_raw = row.get(col_name)
                        if pd.isna(score_raw) or str(score_raw).strip() == '': continue
                        try:
                            score_value = float(score_raw)
                            if not (0 <= score_value <= 5): msg = f"ردیف {row_num}, ستون '{col_name}': امتیاز {score_value} خارج از محدوده مجاز (0-5) است."; print(f"Error: {msg}"); row_errors.append(msg); error_count += 1; row_has_error = True; continue
                            target_measure_id = target_id if target_type == 'measure' else None; target_indicator_id = target_id if target_type == 'indicator' else None
                            existing_score = Score.query.filter_by(participant_phone=phone, measure_id=target_measure_id, indicator_id=target_indicator_id).first()
                            if existing_score:
                                if existing_score.value != score_value: existing_score.value = score_value; existing_score.timestamp = datetime.utcnow(); print(f"Row {row_num}, Col '{col_name}': Updating score to {score_value}")
                            else: new_score = Score(value=score_value, participant_phone=phone, measure_id=target_measure_id, indicator_id=target_indicator_id, timestamp=datetime.utcnow()); db.session.add(new_score); print(f"Row {row_num}, Col '{col_name}': Adding score {score_value}")
                        except (ValueError, TypeError): msg = f"ردیف {row_num}, ستون '{col_name}': فرمت امتیاز '{score_raw}' نامعتبر است (باید عدد باشد)."; print(f"Error: {msg}"); row_errors.append(msg); error_count += 1; row_has_error = True; continue
                    if not row_has_error: processed_count += 1
                except Exception as row_e: msg = f"ردیف {row_num}: خطای غیرمنتظره در پردازش ردیف - {row_e}"; print(f"Critical error: {msg}"); traceback.print_exc(); row_errors.append(msg); error_count += 1; row_has_error = True; commit_successful = False; break
            print(f"\n--- Upload Finished --- Processed: {processed_count}, Errors: {error_count}")
            if commit_successful and error_count == 0:
                 if processed_count > 0 or participant_added_in_loop:
                     try: db.session.commit(); flash(f'{processed_count} ردیف با موفقیت پردازش و ذخیره شد.', 'success')
                     except Exception as commit_error: db.session.rollback(); flash(f'خطا در ذخیره نهایی: {commit_error}', 'danger'); print(f"Final commit error: {commit_error}")
                 else: flash('تغییری برای ذخیره یافت نشد.', 'info')
            else:
                 db.session.rollback(); error_list_html = "<ul class='text-start ps-4' style='max-height: 200px; overflow-y: auto;'>" + "".join([f"<li>{err}</li>" for err in row_errors]) + "</ul>"; flash(f'پردازش فایل با {error_count} خطا مواجه شد. هیچ تغییری ذخیره نشد. خطاها:{error_list_html}', 'danger')
            return redirect(url_for('participants.list_participants'))
        except ImportError: flash('خطا: کتابخانه pandas و openpyxl را نصب کنید.', 'danger'); return redirect(url_for('participants.upload_scores'))
        except Exception as e: db.session.rollback(); flash(f'خطای غیرمنتظره در پردازش فایل: {e}', 'danger'); print(f"File processing error: {e}"); traceback.print_exc(); return redirect(url_for('participants.upload_scores'))
    return render_template('participants/upload_scores.html', form=form)


# --- Route to Download Score Template ---
@participants_bp.route('/download-score-template')
@login_required
def download_score_template():
    """Generates and serves an Excel template for score uploads. Requires admin login."""
    # (Code remains the same as previous version)
    try:
        print("--- Generating Score Template ---")
        scoreable_items = get_active_scoreable_items(); headers = ['شماره تلفن', 'نام']; hierarchical_item_names = []
        for item in scoreable_items: h_name = get_hierarchical_name(item);
        if "خطا:" not in h_name and h_name not in hierarchical_item_names: hierarchical_item_names.append(h_name)
        headers.extend(sorted(hierarchical_item_names)); print(f"Template Headers: {headers}"); df = pd.DataFrame(columns=headers)
        sample_data = {h: '' for h in headers}; sample_data['شماره تلفن'] = '09123456789'; sample_data['نام'] = 'نام نمونه'
        for name in hierarchical_item_names: sample_data[name] = 0.0
        df = pd.concat([df, pd.DataFrame([sample_data])], ignore_index=True); output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='امتیازات'); worksheet = writer.sheets['امتیازات']
            for idx, col in enumerate(df):
                series = df[col]; max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2; col_letter = chr(65 + idx); worksheet.column_dimensions[col_letter].width = max_len
        output.seek(0); print("Template generated successfully.")
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='score_upload_template.xlsx')
    except Exception as e: print(f"Error generating score template: {e}"); traceback.print_exc(); flash("خطا در تولید فایل نمونه اکسل.", "danger"); return redirect(url_for('participants.list_participants'))


# --- Route to view list of participants ---
@participants_bp.route('/list')
@login_required
def list_participants():
     """Displays a paginated list of participants. Requires admin login."""
     page = request.args.get('page', 1, type=int)
     try:
          participants_pagination = Participant.query.order_by(Participant.created_at.desc()).paginate(page=page, per_page=15, error_out=False)
     except Exception as e:
         flash(f"خطا در بارگذاری لیست شرکت‌کنندگان: {e}", "danger"); print(f"Error loading participants list: {e}"); traceback.print_exc(); participants_pagination = None
     return render_template('participants/list.html', participants_pagination=participants_pagination)

# --- Route to Delete Participant ---
@participants_bp.route('/<string:phone>/delete', methods=['POST'])
@login_required
def delete_participant(phone):
    """Deletes a participant and their associated scores. Requires admin login."""
    # (Code remains the same as previous version)
    participant = Participant.query.get_or_404(phone)
    participant_name = participant.name
    try:
        # --- NEW: Delete associated attachment file before deleting participant ---
        if participant.attachment_filename:
            try:
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"Deleted attachment file: {filepath}")
            except Exception as file_e:
                print(f"Error deleting attachment file {participant.attachment_filename}: {file_e}")
                # Optionally flash a warning, but proceed with participant deletion
                flash(f'هشدار: خطا در حذف فایل پیوست برای {participant_name}.', 'warning')
        # --- End NEW ---
        db.session.delete(participant)
        db.session.commit()
        flash(f'شرکت‌کننده "{participant_name}" و تمام اطلاعات او حذف شدند.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'خطا در حذف "{participant_name}": {e}', 'danger'); print(f"Error deleting {phone}: {e}"); traceback.print_exc()
    return redirect(url_for('participants.list_participants'))

# --- Route to Delete ALL Participants ---
@participants_bp.route('/delete-all', methods=['POST'])
@login_required
def delete_all_participants():
    """Deletes ALL participants and their scores/attachments. Requires admin login."""
    try:
        # --- NEW: Delete all attachment files first ---
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
                    # Log error but continue
        print(f"Deleted {deleted_files_count} attachment files during delete-all.")
        # --- End NEW ---

        num_scores_deleted = db.session.query(Score).delete()
        num_participants_deleted = db.session.query(Participant).delete()
        db.session.commit()
        flash(f'تمام {num_participants_deleted} شرکت‌کننده، {num_scores_deleted} امتیاز و {deleted_files_count} فایل پیوست حذف شدند.', 'success')
        print(f"DELETED ALL PARTICIPANTS ({num_participants_deleted}), SCORES ({num_scores_deleted}), and ATTACHMENTS ({deleted_files_count})")
    except Exception as e:
        db.session.rollback(); flash(f'خطا در حذف تمام شرکت‌کنندگان: {e}', 'danger'); print(f"Error deleting all: {e}"); traceback.print_exc()
    return redirect(url_for('participants.list_participants'))


# --- Helper function ---
# (Function remains the same)
def get_participant_scores(phone):
    """Fetches scores for a specific participant, grouped by hierarchical name."""
    try:
        scores = Score.query.filter_by(participant_phone=phone).options(joinedload(Score.scored_measure).joinedload(Measure.indicator).joinedload(Indicator.axis), joinedload(Score.scored_indicator).joinedload(Indicator.axis)).all()
        score_dict = {}
        for score in scores:
             item = score.scored_measure if score.measure_id else score.scored_indicator
             if item: field_name = get_hierarchical_name(item); score_dict[field_name] = score.value
             else: field_name = f"measure_{score.measure_id}" if score.measure_id else f"indicator_{score.indicator_id}"; score_dict[field_name] = score.value
        return score_dict
    except Exception as e: print(f"Error fetching scores for participant {phone}: {e}"); traceback.print_exc(); return {}


# --- NEW: Routes for Attachment Management ---

@participants_bp.route('/manage-attachment/<string:phone>', methods=['GET', 'POST'])
@login_required
def manage_attachment(phone):
    """Displays the attachment management page and handles uploads."""
    participant = Participant.query.get_or_404(phone)
    form = AttachmentForm()

    if form.validate_on_submit():
        file = form.attachment.data
        try:
            # Secure the filename
            filename = secure_filename(file.filename)
            if not filename: # Handle empty filename after securing
                 flash('نام فایل نامعتبر است.', 'danger')
                 return redirect(url_for('participants.manage_attachment', phone=phone))

            # Add phone number prefix for uniqueness (optional but good practice)
            filename = f"{phone}_{filename}"
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

            # Delete old file if it exists and is different
            if participant.attachment_filename and participant.attachment_filename != filename:
                old_filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], participant.attachment_filename)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                        print(f"Deleted old attachment: {old_filepath}")
                    except Exception as e:
                        print(f"Error deleting old attachment {old_filepath}: {e}")
                        flash('خطا در حذف فایل پیوست قبلی.', 'warning')

            # Save the new file
            file.save(save_path)
            print(f"Saved new attachment: {save_path}")

            # Update participant record
            participant.attachment_filename = filename
            db.session.commit()
            flash('فایل پیوست با موفقیت آپلود شد.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'خطا در آپلود فایل: {e}', 'danger')
            print(f"Error uploading file for {phone}: {e}")
            traceback.print_exc()

        return redirect(url_for('participants.manage_attachment', phone=phone))

    # GET request: Render the management page
    return render_template('participants/manage_attachment.html', participant=participant, form=form)


@participants_bp.route('/delete-attachment/<string:phone>', methods=['POST'])
@login_required
def delete_attachment(phone):
    """Deletes the attachment for a participant."""
    participant = Participant.query.get_or_404(phone)
    filename = participant.attachment_filename

    if not filename:
        flash('این شرکت‌کننده فایل پیوستی ندارد.', 'info')
        return redirect(url_for('participants.manage_attachment', phone=phone))

    try:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted attachment file: {filepath}")
        else:
            print(f"Attachment file not found on disk, but removing DB record: {filepath}")

        # Remove filename from database record
        participant.attachment_filename = None
        db.session.commit()
        flash('فایل پیوست با موفقیت حذف شد.', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف فایل پیوست: {e}', 'danger')
        print(f"Error deleting attachment for {phone}: {e}")
        traceback.print_exc()

    return redirect(url_for('participants.manage_attachment', phone=phone))


# --- Route to serve uploaded files ---
# Note: No @login_required here, access control might be needed if files are sensitive
# For now, anyone with the filename can access it.
@participants_bp.route('/view-attachment/<filename>')
def view_attachment(filename):
    """Serves the uploaded attachment file."""
    # Basic security: Use secure_filename again to prevent directory traversal attempts
    # Although the filename stored in DB should already be secured.
    filename = secure_filename(filename)
    print(f"Attempting to serve file: {filename} from {current_app.config['UPLOAD_FOLDER']}")
    try:
        # send_from_directory is safer for serving files
        return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=False) # Set as_attachment=True to force download
    except FileNotFoundError:
        flash('فایل مورد نظر یافت نشد.', 'danger')
        # Redirect somewhere sensible, maybe participant list or login
        if current_user.is_authenticated:
             return redirect(url_for('participants.list_participants'))
        else:
             # If not logged in, maybe redirect to participant login?
             # This depends on how you want to handle broken links for non-logged-in users.
             return redirect(url_for('participant_view.my_results_login')) # Or main.index/auth.login
    except Exception as e:
        flash(f'خطا در نمایش فایل: {e}', 'danger')
        print(f"Error serving file {filename}: {e}")
        if current_user.is_authenticated:
             return redirect(url_for('participants.list_participants'))
        else:
             return redirect(url_for('participant_view.my_results_login'))

# --- End NEW Attachment Routes ---
