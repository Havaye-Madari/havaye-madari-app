# app/routes/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy.exc import IntegrityError
import pandas as pd
import os
from flask_login import login_required
# Use absolute imports
from app.models import db, Axis, Indicator, Measure, Setting
from app.forms import AxisForm, IndicatorForm, MeasureForm, UploadHierarchyForm, HelpTextForm
import traceback

# Create Blueprint for admin routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# --- Helper Function to Update Indicator's Direct Score Allowance ---
def update_indicator_direct_score(indicator_id):
    """
    Checks the status of measures for a given indicator and updates its
    allow_direct_score flag in the database.
    """
    indicator = Indicator.query.get(indicator_id)
    if not indicator:
        print(f"Warning: Indicator with ID {indicator_id} not found in update_indicator_direct_score.")
        return

    if not indicator.is_active:
        indicator.allow_direct_score = False
    else:
        active_measures_exist = db.session.query(Measure.id)\
                                  .with_session(db.session)\
                                  .filter(Measure.indicator_id == indicator.id, Measure.is_active == True)\
                                  .first() is not None
        indicator.allow_direct_score = not active_measures_exist

    print(f"Indicator '{indicator.name}' (ID: {indicator_id}): allow_direct_score set to {indicator.allow_direct_score}")


# --- Combined Hierarchy Management Route ---
@admin_bp.route('/manage', methods=['GET', 'POST'])
@login_required
def manage_hierarchy():
    """
    Handles the display and management (add, edit, delete) of Axes, Indicators, and Measures.
    Requires admin login.
    """
    axis_form = AxisForm(prefix='axis')
    indicator_form = IndicatorForm(prefix='indicator')
    measure_form = MeasureForm(prefix='measure')
    upload_form = UploadHierarchyForm(prefix='upload')

    # Process Axis Form Submission
    if axis_form.submit_axis.data and axis_form.validate_on_submit():
        axis_id = axis_form.id.data
        axis_name_submitted = axis_form.name.data
        try:
            if axis_id: # Edit
                 axis = Axis.query.get_or_404(axis_id)
                 if axis.name != axis_name_submitted and Axis.query.filter_by(name=axis_name_submitted).first():
                      raise IntegrityError(f"نام محور '{axis_name_submitted}' تکراری است.", params=None, orig=None)
                 axis.name = axis_name_submitted
                 axis.description = axis_form.description.data
                 flash(f'محور "{axis.name}" به‌روزرسانی شد!', 'success')
            else: # Add
                if Axis.query.filter_by(name=axis_name_submitted).first():
                     raise IntegrityError(f"نام محور '{axis_name_submitted}' تکراری است.", params=None, orig=None)
                new_axis = Axis(name=axis_name_submitted, description=axis_form.description.data)
                db.session.add(new_axis)
                flash(f'محور "{new_axis.name}" اضافه شد!', 'success')
            db.session.commit()
        except IntegrityError as ie:
             db.session.rollback()
             error_message = str(ie.orig) if hasattr(ie, 'orig') and ie.orig else str(ie)
             if "UNIQUE constraint failed: axis.name" in error_message or "تکراری است" in error_message:
                 flash(f'خطا: محوری با نام "{axis_name_submitted}" از قبل وجود دارد.', 'danger')
             else:
                 flash(f'خطا در پایگاه داده هنگام ذخیره محور: {error_message}', 'danger')
        except Exception as e:
             db.session.rollback()
             flash(f'خطا در ذخیره محور: {e}', 'danger')
             print(f"Error saving axis: {e}")
             traceback.print_exc()
        return redirect(url_for('admin.manage_hierarchy'))


    # Process Indicator Form Submission
    if indicator_form.submit_indicator.data and indicator_form.validate_on_submit():
         indicator_id = indicator_form.id.data
         indicator_name = indicator_form.name.data
         axis_id_selected = indicator_form.axis_id.data
         is_active_submitted = indicator_form.is_active.data
         try:
             parent_axis_obj = Axis.query.get(axis_id_selected)
             if not parent_axis_obj:
                  flash(f'خطا: محور انتخاب شده یافت نشد.', 'danger')
                  return redirect(url_for('admin.manage_hierarchy'))

             if indicator_id: # Edit
                 indicator = Indicator.query.get_or_404(indicator_id)
                 existing_check = Indicator.query.filter(
                     Indicator.id != indicator_id, Indicator.name == indicator_name,
                     Indicator.axis_id == axis_id_selected).first()
                 if existing_check:
                     raise IntegrityError(f"نام شاخص '{indicator_name}' در این محور تکراری است.", params=None, orig=None)

                 indicator.name = indicator_name
                 indicator.weight = indicator_form.weight.data
                 indicator.description = indicator_form.description.data
                 indicator.axis = parent_axis_obj
                 indicator.is_active = is_active_submitted
                 update_indicator_direct_score(indicator.id)
                 flash(f'شاخص "{indicator.name}" به‌روزرسانی شد!', 'success')
             else: # Add
                existing = Indicator.query.filter_by(name=indicator_name, axis_id=axis_id_selected).first()
                if existing:
                    raise IntegrityError(f"نام شاخص '{indicator_name}' در این محور تکراری است.", params=None, orig=None)

                new_indicator = Indicator(
                    name=indicator_name, weight=indicator_form.weight.data,
                    description=indicator_form.description.data, axis=parent_axis_obj,
                    is_active=is_active_submitted
                )
                new_indicator.allow_direct_score = new_indicator.is_active
                db.session.add(new_indicator)
                flash(f'شاخص "{new_indicator.name}" اضافه شد!', 'success')

             db.session.commit()
         except IntegrityError as ie:
              db.session.rollback()
              flash(f'خطا: شاخصی با نام "{indicator_name}" در این محور از قبل وجود دارد.', 'danger')
         except Exception as e:
             db.session.rollback()
             flash(f'خطا در ذخیره شاخص: {e}', 'danger')
             print(f"Error saving indicator: {e}")
             traceback.print_exc()
         return redirect(url_for('admin.manage_hierarchy'))

    # Process Measure Form Submission
    if measure_form.submit_measure.data and measure_form.validate_on_submit():
        measure_id = measure_form.id.data
        measure_name = measure_form.name.data
        indicator_id_selected = measure_form.indicator_id.data
        is_active_submitted = measure_form.is_active.data
        parent_indicator_obj = None
        try:
            parent_indicator_obj = Indicator.query.get(indicator_id_selected)
            if not parent_indicator_obj:
                 flash(f'خطا: شاخص انتخاب شده یافت نشد.', 'danger')
                 return redirect(url_for('admin.manage_hierarchy'))

            if measure_id: # Edit
                measure = Measure.query.get_or_404(measure_id)
                existing_check = Measure.query.filter(
                    Measure.id != measure_id, Measure.name == measure_name,
                    Measure.indicator_id == indicator_id_selected).first()
                if existing_check:
                     raise IntegrityError(f"نام سنجه '{measure_name}' در این شاخص تکراری است.", params=None, orig=None)

                measure.name = measure_name
                measure.weight = measure_form.weight.data
                measure.description = measure_form.description.data
                measure.indicator = parent_indicator_obj
                measure.is_active = is_active_submitted
                flash(f'سنجه "{measure.name}" به‌روزرسانی شد!', 'success')
            else: # Add
                existing = Measure.query.filter_by(name=measure_name, indicator_id=indicator_id_selected).first()
                if existing:
                    raise IntegrityError(f"نام سنجه '{measure_name}' در این شاخص تکراری است.", params=None, orig=None)

                new_measure = Measure(
                    name=measure_name, weight=measure_form.weight.data,
                    description=measure_form.description.data, indicator=parent_indicator_obj,
                    is_active=is_active_submitted
                )
                db.session.add(new_measure)
                flash(f'سنجه "{new_measure.name}" اضافه شد!', 'success')

            update_indicator_direct_score(parent_indicator_obj.id)
            db.session.commit()
        except IntegrityError as ie:
            db.session.rollback()
            flash(f'خطا: سنجه‌ای با نام "{measure_name}" در این شاخص از قبل وجود دارد.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در ذخیره سنجه: {e}', 'danger')
            print(f"Error saving measure: {e}")
            traceback.print_exc()
        return redirect(url_for('admin.manage_hierarchy'))

    # --- Data Fetching for Display ---
    try:
        axes_with_hierarchy = Axis.query.options(
            joinedload(Axis.indicators).joinedload(Indicator.measures)
        ).order_by(Axis.name).all()
    except Exception as e:
         flash(f"خطا در بارگذاری ساختار فعلی: {e}", "danger")
         axes_with_hierarchy = []


    # Render the template with forms and the hierarchical data
    return render_template(
        'admin/manage_hierarchy.html',
        axis_form=axis_form,
        indicator_form=indicator_form,
        measure_form=measure_form,
        upload_form=upload_form,
        axes_data=axes_with_hierarchy
    )


# --- Route for Handling Hierarchy Upload ---
@admin_bp.route('/upload-hierarchy', methods=['POST'])
@login_required
def upload_hierarchy():
    """Handles uploading the hierarchy structure from an Excel file."""
    form = UploadHierarchyForm(prefix='upload')
    print("--- Starting Hierarchy Upload ---")

    if form.validate_on_submit():
        file = form.excel_file.data
        print(f"File '{file.filename}' received and validated.")
        try:
            df = pd.read_excel(file, engine='openpyxl', header=0)
            print(f"Successfully read Excel file. Shape: {df.shape}")

            expected_cols_map = {
                'سطح': 'level', 'نام': 'name', 'نام والد': 'parent_name',
                'وزن': 'weight', 'توضیحات': 'description'
            }
            original_columns = list(df.columns)
            df.columns = [str(col).strip().lower() for col in df.columns]
            df.rename(columns={k.lower(): v for k, v in expected_cols_map.items()}, inplace=True)
            print(f"Original columns: {original_columns}")
            print(f"Normalized/Renamed columns: {list(df.columns)}")


            required_cols_std = ['level', 'name']

            missing_std_cols = [col for col in required_cols_std if col not in df.columns]
            if missing_std_cols:
                 missing_display = [k for k,v in expected_cols_map.items() if v in missing_std_cols]
                 flash(f'خطا: فایل اکسل فاقد ستون‌های الزامی است: {", ".join(missing_display)} (یا نام ستون‌ها در فایل با نمونه مطابقت ندارد). ستون‌های یافت شده: {", ".join(original_columns)}', 'danger')
                 print(f"ERROR: Missing required columns after normalization: {missing_std_cols}. Original missing: {missing_display}")
                 return redirect(url_for('admin.manage_hierarchy'))

            print("Loading existing data into cache...")
            axes_created = {axis.name: axis for axis in Axis.query.all()}
            indicators_created = {}
            for ind in Indicator.query.options(joinedload(Indicator.axis)).all():
                 if ind.axis:
                      indicators_created[(ind.name, ind.axis.name)] = ind
            measures_created = {}
            for m in Measure.query.options(joinedload(Measure.indicator).joinedload(Indicator.axis)).all():
                 if m.indicator and m.indicator.axis:
                      measures_created[(m.name, m.indicator.name, m.indicator.axis.name)] = m

            print(f"Cache loaded: {len(axes_created)} Axes, {len(indicators_created)} Indicators, {len(measures_created)} Measures.")

            row_errors = []
            items_added_count = 0
            indicators_to_update_allow_score = set()

            print("Starting row processing...")
            for index, row in df.iterrows():
                row_num = index + 2
                print(f"\n--- Processing Row {row_num} ---")
                try:
                    level_raw = row.get('level')
                    name_raw = row.get('name')
                    parent_name_raw = row.get('parent_name')
                    weight_raw = row.get('weight')
                    description_raw = row.get('description')

                    level = str(level_raw).strip().lower() if pd.notna(level_raw) else None
                    name = str(name_raw).strip() if pd.notna(name_raw) else None
                    parent_name = str(parent_name_raw).strip() if pd.notna(parent_name_raw) else None
                    parent_name = parent_name if parent_name else None
                    description = str(description_raw).strip() if pd.notna(description_raw) else None
                    description = description if description else None

                    print(f"Row {row_num} Data: Level='{level}', Name='{name}', Parent='{parent_name}', Weight='{weight_raw}', Desc='{description}'")

                    if not level or level not in ['محور', 'axis', 'شاخص', 'indicator', 'سنجه', 'measure']:
                        error_msg = f"ردیف {row_num}: مقدار ستون 'سطح' نامعتبر یا خالی است ('{level_raw}'). مقادیر مجاز: محور, شاخص, سنجه."
                        print(f"ERROR: {error_msg}")
                        row_errors.append(error_msg)
                        continue
                    if not name:
                        error_msg = f"ردیف {row_num}: مقدار ستون 'نام' الزامی و نمی‌تواند خالی باشد."
                        print(f"ERROR: {error_msg}")
                        row_errors.append(error_msg)
                        continue

                    if level in ['محور', 'axis']:
                        if parent_name:
                             error_msg = f"ردیف {row_num} (محور '{name}'): محورها نباید 'نام والد' داشته باشند (مقدار یافت شده: '{parent_name_raw}')."
                             print(f"ERROR: {error_msg}")
                             row_errors.append(error_msg)
                             continue
                        if name not in axes_created:
                            print(f"Row {row_num}: Adding Axis '{name}'")
                            new_axis = Axis(name=name, description=description)
                            db.session.add(new_axis)
                            axes_created[name] = new_axis
                            items_added_count += 1
                        else:
                            print(f"Row {row_num}: Skipping existing Axis '{name}'")
                        continue

                    if level in ['شاخص', 'indicator']:
                        if not parent_name:
                            error_msg = f"ردیف {row_num} (شاخص '{name}'): 'نام والد' (نام محور) الزامی است و نمی‌تواند خالی باشد."
                            print(f"ERROR: {error_msg}")
                            row_errors.append(error_msg)
                            continue
                        if parent_name not in axes_created:
                            error_msg = f"ردیف {row_num} (شاخص '{name}'): محور والد '{parent_name}' یافت نشد."
                            print(f"ERROR: {error_msg}")
                            row_errors.append(error_msg)
                            continue
                        try:
                            if pd.isna(weight_raw): raise ValueError("مقدار وزن نمی‌تواند خالی باشد.")
                            weight = float(weight_raw)
                            if not (0 <= weight <= 1): raise ValueError("مقدار وزن باید بین 0 و 1 باشد.")
                        except (ValueError, TypeError) as e:
                            error_msg = f"ردیف {row_num} (شاخص '{name}'): مقدار 'وزن' نامعتبر است ('{weight_raw}'). خطا: {e}"
                            print(f"ERROR: {error_msg}")
                            row_errors.append(error_msg)
                            continue

                        indicator_key = (name, parent_name)
                        if indicator_key not in indicators_created:
                            print(f"Row {row_num}: Adding Indicator '{name}' under Axis '{parent_name}'")
                            parent_axis_obj = axes_created[parent_name]
                            new_indicator = Indicator(name=name, weight=weight, description=description, axis=parent_axis_obj, is_active=True, allow_direct_score=True)
                            db.session.add(new_indicator)
                            indicators_created[indicator_key] = new_indicator
                            items_added_count += 1
                        else:
                            print(f"Row {row_num}: Skipping existing Indicator '{name}' under Axis '{parent_name}'")
                        continue

                    if level in ['سنجه', 'measure']:
                        if not parent_name:
                            error_msg = f"ردیف {row_num} (سنجه '{name}'): 'نام والد' (نام شاخص) الزامی است و نمی‌تواند خالی باشد."
                            print(f"ERROR: {error_msg}")
                            row_errors.append(error_msg)
                            continue

                        parent_indicator_obj = None
                        parent_axis_name_found = None
                        found_indicator_key = None
                        for key, ind_obj in indicators_created.items():
                            ind_name, ax_name = key
                            if ind_name == parent_name:
                                parent_indicator_obj = ind_obj
                                parent_axis_name_found = ax_name
                                found_indicator_key = key
                                break

                        if not parent_indicator_obj:
                             error_msg = f"ردیف {row_num} (سنجه '{name}'): شاخص والد '{parent_name}' یافت نشد."
                             print(f"ERROR: {error_msg}")
                             row_errors.append(error_msg)
                             continue
                        try:
                            if pd.isna(weight_raw): raise ValueError("مقدار وزن نمی‌تواند خالی باشد.")
                            weight = float(weight_raw)
                            if not (0 <= weight <= 1): raise ValueError("مقدار وزن باید بین 0 و 1 باشد.")
                        except (ValueError, TypeError) as e:
                            error_msg = f"ردیف {row_num} (سنجه '{name}'): مقدار 'وزن' نامعتبر است ('{weight_raw}'). خطا: {e}"
                            print(f"ERROR: {error_msg}")
                            row_errors.append(error_msg)
                            continue

                        measure_key = (name, parent_name, parent_axis_name_found)
                        if measure_key not in measures_created:
                            print(f"Row {row_num}: Adding Measure '{name}' under Indicator '{parent_name}' (Axis: {parent_axis_name_found})")
                            new_measure = Measure(name=name, weight=weight, description=description, indicator=parent_indicator_obj, is_active=True)
                            db.session.add(new_measure)
                            measures_created[measure_key] = new_measure
                            items_added_count += 1
                            indicators_to_update_allow_score.add(parent_indicator_obj.id)
                        else:
                             print(f"Row {row_num}: Skipping existing Measure '{name}' under Indicator '{parent_name}' (Axis: {parent_axis_name_found})")

                except Exception as row_e:
                    error_msg = f"ردیف {row_num}: خطای غیرمنتظره در پردازش - {row_e}"
                    print(f"ERROR: {error_msg}")
                    traceback.print_exc()
                    row_errors.append(error_msg)

            # --- Update allow_direct_score for affected indicators ---
            if indicators_to_update_allow_score:
                 print("\nUpdating allow_direct_score for indicators affected by new measures...")
                 try:
                      db.session.flush()
                      for indicator_id in indicators_to_update_allow_score:
                           update_indicator_direct_score(indicator_id)
                 except Exception as flush_update_e:
                      error_msg = f"خطا در به‌روزرسانی وضعیت امتیاز مستقیم شاخص‌ها پس از افزودن سنجه‌ها: {flush_update_e}"
                      print(f"ERROR: {error_msg}")
                      traceback.print_exc()
                      row_errors.append(error_msg)


            # --- Commit or Rollback Transaction ---
            print("\n--- End of Row Processing ---")
            print(f"Total items added in this run: {items_added_count}")
            print(f"Total errors found: {len(row_errors)}")

            if not row_errors:
                if items_added_count > 0:
                    try:
                        print("Committing changes...")
                        db.session.commit()
                        flash(f'{items_added_count} آیتم جدید با موفقیت از فایل اکسل آپلود و پردازش شد.', 'success')
                    except Exception as commit_e:
                        db.session.rollback()
                        flash(f'خطا در ذخیره نهایی اطلاعات در پایگاه داده: {commit_e}', 'danger')
                        print(f"ERROR: Final commit error after upload: {commit_e}")
                        traceback.print_exc()
                else:
                    print("No new items to add, no commit needed.")
                    flash('هیچ آیتم جدیدی برای افزودن در فایل اکسل یافت نشد (ممکن است تمام آیتم‌ها از قبل وجود داشته باشند).', 'info')
            else:
                print("Errors found, rolling back transaction.")
                db.session.rollback()
                error_list_html = "<ul class='text-start ps-4'>" + "".join([f"<li>{err}</li>" for err in row_errors]) + "</ul>"
                flash(f'خطا در پردازش فایل اکسل. هیچ تغییری ذخیره نشد. خطاها:{error_list_html}', 'danger')

        except ImportError:
             print("ERROR: Pandas/Openpyxl not installed.")
             db.session.rollback()
             flash('خطا: برای پردازش فایل اکسل، لطفاً کتابخانه pandas و openpyxl را نصب کنید (pip install pandas openpyxl).', 'danger')
        except Exception as e:
            print(f"ERROR: Unexpected error during upload/processing: {e}")
            traceback.print_exc()
            db.session.rollback()
            flash(f'خطای غیرمنتظره در آپلود یا پردازش فایل: {e}', 'danger')

    else:
        print("ERROR: Form validation failed.")
        for field, errors in form.errors.items():
            field_obj = getattr(form, field, None)
            label_text = getattr(field_obj, 'label', None)
            label = label_text.text if label_text else field.capitalize()
            for error in errors:
                flash(f"خطا در فیلد '{label}': {error}", 'danger')
                print(f"Form validation error - Field: {label}, Error: {error}")


    return redirect(url_for('admin.manage_hierarchy'))


# --- Route to Download the Template File ---
@admin_bp.route('/download-template')
def download_template():
    """Serves the hierarchy template file."""
    try:
        template_dir = os.path.join(current_app.static_folder, 'attachments')
        filename = 'evaluation_hierarchy_template.xlsx'
        print(f"Attempting to send file from: {os.path.join(template_dir, filename)}")
        return send_from_directory(template_dir, filename, as_attachment=True)
    except FileNotFoundError:
        print(f"File not found error: Template not found at {os.path.join(template_dir, filename)}")
        flash("فایل نمونه یافت نشد. لطفاً مطمئن شوید فایل در مسیر app/static/attachments/ قرار دارد.", "danger")
        return redirect(url_for('admin.manage_hierarchy'))
    except Exception as e:
         flash(f"خطا در دانلود فایل نمونه: {e}", "danger")
         print(f"Error downloading template: {e}")
         traceback.print_exc()
         return redirect(url_for('admin.manage_hierarchy'))

# --- Routes to Toggle Active Status ---
@admin_bp.route('/indicator/<int:indicator_id>/toggle-active', methods=['POST'])
@login_required
def toggle_indicator_active(indicator_id):
    """Toggles the active status of an indicator."""
    indicator = Indicator.query.get_or_404(indicator_id)
    try:
        indicator.is_active = not indicator.is_active
        print(f"Toggling indicator '{indicator.name}' to is_active={indicator.is_active}")
        update_indicator_direct_score(indicator.id)
        db.session.commit()
        status = "فعال" if indicator.is_active else "غیرفعال"
        flash(f'وضعیت شاخص "{indicator.name}" به {status} تغییر یافت.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در تغییر وضعیت شاخص: {e}', 'danger')
        print(f"Error toggling indicator active: {e}")
        traceback.print_exc()
    return redirect(url_for('admin.manage_hierarchy'))

@admin_bp.route('/measure/<int:measure_id>/toggle-active', methods=['POST'])
@login_required
def toggle_measure_active(measure_id):
    """Toggles the active status of a measure and updates its parent indicator."""
    measure = Measure.query.options(joinedload(Measure.indicator)).get(measure_id)
    if not measure:
        flash('سنجه یافت نشد.', 'danger')
        return redirect(url_for('admin.manage_hierarchy'))

    parent_indicator_id = measure.indicator_id
    try:
        measure.is_active = not measure.is_active
        print(f"Toggling measure '{measure.name}' to is_active={measure.is_active}")
        update_indicator_direct_score(parent_indicator_id)
        db.session.commit()
        status = "فعال" if measure.is_active else "غیرفعال"
        flash(f'وضعیت سنجه "{measure.name}" به {status} تغییر یافت.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در تغییر وضعیت سنجه: {e}', 'danger')
        print(f"Error toggling measure active: {e}")
        traceback.print_exc()

    return redirect(url_for('admin.manage_hierarchy'))


# --- Deletion Routes ---
@admin_bp.route('/axis/<int:axis_id>/delete', methods=['POST'])
@login_required
def delete_axis(axis_id):
    """Deletes an axis and all its descendants."""
    axis = Axis.query.get_or_404(axis_id)
    try:
        db.session.delete(axis)
        db.session.commit()
        flash(f'محور "{axis.name}" و تمام زیرمجموعه‌های آن حذف شدند.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف محور: {e}', 'danger')
    return redirect(url_for('admin.manage_hierarchy'))


@admin_bp.route('/indicator/<int:indicator_id>/delete', methods=['POST'])
@login_required
def delete_indicator(indicator_id):
    """Deletes an indicator and all its measures."""
    indicator = Indicator.query.get_or_404(indicator_id)
    try:
        db.session.delete(indicator)
        db.session.commit()
        flash(f'شاخص "{indicator.name}" و تمام سنجه‌های مرتبط با آن حذف شدند.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف شاخص: {e}', 'danger')
    return redirect(url_for('admin.manage_hierarchy'))


@admin_bp.route('/measure/<int:measure_id>/delete', methods=['POST'])
@login_required
def delete_measure(measure_id):
    """Deletes a measure and updates the parent indicator."""
    measure = Measure.query.get_or_404(measure_id)
    parent_indicator_id = measure.indicator_id
    try:
        db.session.delete(measure)
        print(f"Deleting measure '{measure.name}' (ID: {measure_id})")
        update_indicator_direct_score(parent_indicator_id)
        db.session.commit()
        flash(f'سنجه "{measure.name}" و امتیازات مرتبط با آن حذف شدند.', 'success')
    except IntegrityError as ie:
         db.session.rollback()
         error_str = str(ie.orig).lower()
         if "foreign key constraint" in error_str or "foreign key violation" in error_str:
              flash(f'خطا: سنجه "{measure.name}" قابل حذف نیست زیرا امتیازاتی برای آن ثبت شده است.', 'danger')
         else:
              flash(f'خطا در پایگاه داده هنگام حذف سنجه: {ie.orig}', 'danger')
    except Exception as e:
        db.session.rollback()
        flash(f'خطا در حذف سنجه: {e}', 'danger')
    return redirect(url_for('admin.manage_hierarchy'))


# --- Routes for getting data for editing (AJAX) ---
@admin_bp.route('/axis/<int:axis_id>/data', methods=['GET'])
@login_required
def get_axis_data(axis_id):
    """Returns axis data as JSON for editing form."""
    axis = Axis.query.get_or_404(axis_id)
    return {'id': axis.id, 'name': axis.name, 'description': axis.description or ''}


@admin_bp.route('/indicator/<int:indicator_id>/data', methods=['GET'])
@login_required
def get_indicator_data(indicator_id):
    """Returns indicator data as JSON for editing form."""
    indicator = Indicator.query.get_or_404(indicator_id)
    return {
        'id': indicator.id,
        'name': indicator.name,
        'weight': indicator.weight,
        'description': indicator.description or '',
        'axis_id': indicator.axis_id,
        'is_active': indicator.is_active
    }

@admin_bp.route('/measure/<int:measure_id>/data', methods=['GET'])
@login_required
def get_measure_data(measure_id):
    """Returns measure data as JSON for editing form."""
    measure = Measure.query.get_or_404(measure_id)
    return {
        'id': measure.id,
        'name': measure.name,
        'weight': measure.weight,
        'description': measure.description or '',
        'indicator_id': measure.indicator_id,
        'is_active': measure.is_active
    }

# --- Route for Managing Help Text ---
@admin_bp.route('/manage-help', methods=['GET', 'POST'])
@login_required
def manage_help():
    """Manages the help text displayed on results pages."""
    form = HelpTextForm()
    setting_key = 'participant_results_help'
    default_help_text = "اینجا می‌توانید راهنمای مربوط به نحوه تفسیر نتایج و نمودارها را قرار دهید."

    if form.validate_on_submit():
        try:
            setting = Setting.query.get(setting_key)
            if setting:
                setting.value = form.help_text.data
                print(f"Updating setting '{setting_key}'")
            else:
                setting = Setting(key=setting_key, value=form.help_text.data)
                db.session.add(setting)
                print(f"Creating setting '{setting_key}'")
            db.session.commit()
            flash('متن راهنما با موفقیت ذخیره شد.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'خطا در ذخیره متن راهنما: {e}', 'danger')
            print(f"Error saving help text: {e}")
            traceback.print_exc()
        return redirect(url_for('admin.manage_help'))

    if request.method == 'GET':
        setting = Setting.query.get(setting_key)
        current_text = setting.value if setting else default_help_text
        form.help_text.data = current_text

    return render_template('admin/manage_help.html', form=form)

# Ensure there is no trailing code or syntax errors below this line

