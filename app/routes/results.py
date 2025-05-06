# app/routes/results.py
from flask import Blueprint, render_template, flash, jsonify, abort, request, redirect, url_for
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case
import pandas as pd
import json
from flask_login import login_required, current_user
# --- UPDATED: Use absolute imports ---
from app.models import db, Axis, Indicator, Measure, Score, Participant, Setting
# --- End UPDATED ---
import traceback

results_bp = Blueprint('results', __name__, url_prefix='/results')

# --- Function to get help text ---
def get_results_help_text():
    """Fetches the help text for results pages from the database."""
    setting = Setting.query.get('participant_results_help')
    return setting.value if setting else None


# --- calculate_scores_internal function ---
def calculate_scores_internal(participant_phone=None):
    """
    Internal function to calculate scores.
    """
    summary_data = {
        'participant': None, 'axes': [], 'overall_score': 0.0,
        'all_indicators_avg': {}, 'total_participants': 0
    }
    calculation_mode = "individual" if participant_phone else "summary"
    print(f"--- Calculating Scores --- Mode: {calculation_mode}, Participant: {participant_phone}")

    try:
        participants_query = Participant.query
        if participant_phone:
            participant = participants_query.get(participant_phone)
            if not participant:
                print(f"Participant not found: {participant_phone}")
                return None
            summary_data['participant'] = participant
            participants_count = 1
        else:
            participants_count = participants_query.count()

        summary_data['total_participants'] = Participant.query.count()

        if participants_count == 0:
            print("No participants found in the database.")
            return summary_data

        active_indicators = Indicator.query.options(joinedload(Indicator.axis))\
                                     .filter(Indicator.is_active == True)\
                                     .order_by(Indicator.axis_id, Indicator.id).all()
        active_measures = Measure.query.options(joinedload(Measure.indicator))\
                                .filter(Measure.is_active == True)\
                                .join(Measure.indicator)\
                                .filter(Indicator.is_active == True)\
                                .all()

        scores_query = db.session.query(Score)
        if participant_phone:
            scores_query = scores_query.filter(Score.participant_phone == participant_phone)
        all_relevant_scores = scores_query.all()

        if participant_phone and not all_relevant_scores:
             print(f"No scores found for participant: {participant_phone}")

        scores_by_participant = {}
        for score in all_relevant_scores:
            phone_key = score.participant_phone
            if phone_key not in scores_by_participant:
                scores_by_participant[phone_key] = {'measures': {}, 'indicators': {}}
            if score.measure_id:
                scores_by_participant[phone_key]['measures'][score.measure_id] = score.value
            elif score.indicator_id:
                scores_by_participant[phone_key]['indicators'][score.indicator_id] = score.value

        indicator_scores_calculated = {}
        all_indicator_scores_list = {}

        all_scores_for_avg = []
        if calculation_mode == "summary" or summary_data['total_participants'] > 0:
             all_scores_for_avg = db.session.query(Score.indicator_id, Score.measure_id, Score.value).all()

        all_scores_lookup = {}
        for score_data in all_scores_for_avg:
             target_type = 'indicator' if score_data.indicator_id else 'measure'
             target_id = score_data.indicator_id if score_data.indicator_id else score_data.measure_id
             if target_id is None: continue
             key = (target_type, target_id)
             if key not in all_scores_lookup:
                  all_scores_lookup[key] = []
             all_scores_lookup[key].append(score_data.value)

        overall_indicator_averages = {}
        for indicator in active_indicators:
             indicator_id = indicator.id
             all_indicator_scores_list[indicator_id] = []
             total_weight_avg = 0.0; weighted_sum_avg = 0.0; scores_found_count = 0

             if indicator.allow_direct_score:
                  direct_scores = all_scores_lookup.get(('indicator', indicator_id), [])
                  if direct_scores:
                       avg_score = sum(direct_scores) / len(direct_scores)
                       overall_indicator_averages[indicator_id] = avg_score
                       all_indicator_scores_list[indicator_id].extend(direct_scores)
                  else: overall_indicator_averages[indicator_id] = 0.0
             else:
                  indicator_measures = [m for m in active_measures if m.indicator_id == indicator_id]
                  for measure in indicator_measures:
                       measure_scores = all_scores_lookup.get(('measure', measure.id), [])
                       if measure_scores:
                            avg_measure_score = sum(measure_scores) / len(measure_scores)
                            weighted_sum_avg += avg_measure_score * measure.weight
                            total_weight_avg += measure.weight
                            scores_found_count += len(measure_scores)
                            all_indicator_scores_list[indicator_id].extend(measure_scores)
                  overall_indicator_averages[indicator_id] = (weighted_sum_avg / total_weight_avg) if total_weight_avg > 0 else 0.0

        summary_data['all_indicators_avg'] = overall_indicator_averages

        for indicator in active_indicators:
            indicator_id = indicator.id
            calculated_score = 0.0

            if calculation_mode == "individual":
                participant_scores = scores_by_participant.get(participant_phone, {'measures': {}, 'indicators': {}})
                if indicator.allow_direct_score:
                    calculated_score = participant_scores['indicators'].get(indicator_id, 0.0)
                else:
                    total_weight = 0.0; weighted_sum = 0.0; has_scores_for_measures = False
                    indicator_measures = [m for m in active_measures if m.indicator_id == indicator_id]
                    for measure in indicator_measures:
                        measure_score = participant_scores['measures'].get(measure.id)
                        if measure_score is not None:
                            weighted_sum += measure_score * measure.weight
                            total_weight += measure.weight
                            has_scores_for_measures = True
                    if has_scores_for_measures and total_weight > 0:
                        calculated_score = weighted_sum / total_weight
                indicator_scores_calculated[indicator_id] = calculated_score
            else: # Summary mode
                indicator_scores_calculated[indicator_id] = overall_indicator_averages.get(indicator_id, 0.0)

        axes_dict = {}
        total_weighted_sum_all = 0.0; total_weight_all = 0.0

        for indicator in active_indicators:
            if not indicator.axis: continue
            axis_id = indicator.axis_id; axis_name = indicator.axis.name

            if axis_id not in axes_dict:
                axes_dict[axis_id] = {'id': axis_id, 'name': axis_name, 'indicators': [], 'total_weighted_score': 0.0, 'total_weight': 0.0}

            indicator_score = indicator_scores_calculated.get(indicator.id, 0.0)
            axes_dict[axis_id]['indicators'].append({'id': indicator.id, 'name': indicator.name, 'score': indicator_score, 'weight': indicator.weight})
            axes_dict[axis_id]['total_weighted_score'] += indicator_score * indicator.weight
            axes_dict[axis_id]['total_weight'] += indicator.weight
            total_weighted_sum_all += indicator_score * indicator.weight
            total_weight_all += indicator.weight

        for axis_data in axes_dict.values():
            axis_data['axis_score'] = (axis_data['total_weighted_score'] / axis_data['total_weight']) if axis_data['total_weight'] > 0 else 0.0
            summary_data['axes'].append(axis_data)

        summary_data['overall_score'] = (total_weighted_sum_all / total_weight_all) if total_weight_all > 0 else 0.0

        summary_data['axes'].sort(key=lambda x: x['name'])
        for axis in summary_data['axes']:
             axis['indicators'].sort(key=lambda x: x['name'])

    except Exception as e:
        print(f"Error calculating scores (Mode: {calculation_mode}, Participant: {participant_phone}): {e}")
        traceback.print_exc()
        flash(f"خطا در محاسبه نتایج: {e}", "danger")

    print(f"--- Score Calculation Complete --- Mode: {calculation_mode}")
    return summary_data


@results_bp.route('/summary')
@login_required
def summary():
    """Displays the summary results page. Requires admin login."""
    summary_data = calculate_scores_internal()
    help_text = get_results_help_text()

    chart_data = {}
    for axis in summary_data['axes']:
        if axis.get('indicators'):
            chart_data[axis['id']] = {
                'name': axis['name'],
                'labels': [ind['name'] for ind in axis['indicators']],
                'participant_or_avg_scores': [round(ind['score'], 2) for ind in axis['indicators']],
                'overall_indicator_averages': [round(summary_data['all_indicators_avg'].get(ind['id'], 0.0), 2) for ind in axis['indicators']]
            }
        else: print(f"Warning: No indicators found for axis '{axis['name']}' (ID: {axis['id']}) when preparing chart data.")

    return render_template(
        'results/summary.html',
        summary_data=summary_data,
        chart_data_json=json.dumps(chart_data),
        help_text=help_text
    )

@results_bp.route('/participant/<string:phone>')
def participant_summary(phone):
    """
    Displays the results page for a specific participant.
    Requires admin login if not accessed via participant view mode.
    """
    view_mode = request.args.get('view_mode', 'admin')
    is_participant_view = (view_mode == 'participant')

    if not is_participant_view and not current_user.is_authenticated:
        flash("برای دسترسی به این صفحه، لطفاً وارد شوید.", "info")
        return redirect(url_for('auth.login', next=request.url))

    print(f"Accessing participant summary for {phone}. View Mode: {view_mode}, Is Participant View: {is_participant_view}")
    summary_data = calculate_scores_internal(participant_phone=phone)
    help_text = get_results_help_text()

    if summary_data is None:
        flash(f"شرکت‌کننده‌ای با شماره تلفن {phone} یافت نشد.", "warning")
        return redirect(url_for('participant_view.my_results_login') if is_participant_view else url_for('participants.list_participants'))

    if not summary_data.get('participant'):
         flash(f"اطلاعات شرکت‌کننده با شماره {phone} یافت نشد.", "warning")
         return redirect(url_for('participant_view.my_results_login') if is_participant_view else url_for('participants.list_participants'))

    chart_data = {}
    for axis in summary_data['axes']:
        if axis.get('indicators'):
            chart_data[axis['id']] = {
                'name': axis['name'],
                'labels': [ind['name'] for ind in axis['indicators']],
                'participant_or_avg_scores': [round(ind['score'], 2) for ind in axis['indicators']],
                'overall_indicator_averages': [round(summary_data['all_indicators_avg'].get(ind['id'], 0.0), 2) for ind in axis['indicators']]
            }
        else: print(f"Warning: No indicators found for axis '{axis['name']}' (ID: {axis['id']}) when preparing chart data for participant {phone}.")

    return render_template(
        'results/participant_summary.html',
        summary_data=summary_data,
        chart_data_json=json.dumps(chart_data),
        is_participant_view=is_participant_view,
        help_text=help_text
    )
