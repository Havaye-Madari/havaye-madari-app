# app/routes/results.py
from flask import Blueprint, render_template, flash, jsonify, abort, request, redirect, url_for
from sqlalchemy.orm import joinedload
from sqlalchemy import func, case
import pandas as pd
import json
from flask_login import login_required, current_user
from app.models import db, Axis, Indicator, Measure, Score, Participant, Setting
import traceback

results_bp = Blueprint('results', __name__, url_prefix='/results')

def get_results_help_text():
    """Fetches the help text for results pages from the database."""
    setting = Setting.query.get('participant_results_help')
    return setting.value if setting else None

# --- NEW Helper function to identify participants with all zero scores ---
def get_participants_with_only_zero_scores():
    """
    Returns a set of participant phones for whom all recorded scores are zero,
    OR who have no scores recorded at all.
    These participants will be excluded from overall average calculations.
    """
    participants_to_exclude = set()
    all_participants_with_scores_info = db.session.query(
        Score.participant_phone,
        func.count(Score.id).label('total_scores'),
        func.sum(Score.value).label('sum_scores')
    ).group_by(Score.participant_phone).all()

    participant_phones_with_any_score = {info.participant_phone for info in all_participants_with_scores_info}

    for info in all_participants_with_scores_info:
        if info.sum_scores == 0.0: # All their scores sum to zero (could be multiple zeros)
            participants_to_exclude.add(info.participant_phone)

    # Also find participants who have NO scores at all
    all_participant_phones = {p.phone for p in Participant.query.with_entities(Participant.phone).all()}
    participants_with_no_scores = all_participant_phones - participant_phones_with_any_score
    participants_to_exclude.update(participants_with_no_scores)
    
    print(f"DEBUG: Participants identified to exclude from overall averages: {participants_to_exclude}")
    return participants_to_exclude

def calculate_scores_internal(participant_phone=None):
    """
    Internal function to calculate scores.
    If participant_phone is provided, it also checks if all their scores are zero for display purposes.
    Overall averages exclude participants with all zero scores or no scores.
    """
    summary_data = {
        'participant': None, 'axes': [], 'overall_score': 0.0,
        'all_indicators_avg': {}, 'total_participants': 0,
        'all_scores_zero_for_individual': False, # For individual display
        'num_participants_in_overall_avg': 0 # For transparency in summary
    }
    calculation_mode = "individual" if participant_phone else "summary"
    print(f"--- Calculating Scores --- Mode: {calculation_mode}, Participant: {participant_phone}")

    try:
        total_participants_in_system = Participant.query.count()
        summary_data['total_participants'] = total_participants_in_system

        if participant_phone:
            participant = Participant.query.get(participant_phone)
            if not participant:
                print(f"Participant not found: {participant_phone}")
                return None
            summary_data['participant'] = participant
            
            participant_actual_scores = Score.query.filter_by(participant_phone=participant_phone).all()
            if not participant_actual_scores:
                summary_data['all_scores_zero_for_individual'] = True
            elif all(s.value == 0.0 for s in participant_actual_scores):
                summary_data['all_scores_zero_for_individual'] = True
            # else: all_scores_zero_for_individual remains False

        active_indicators = Indicator.query.options(joinedload(Indicator.axis))\
                                     .filter(Indicator.is_active == True)\
                                     .order_by(Indicator.axis_id, Indicator.id).all()
        active_measures = Measure.query.options(joinedload(Measure.indicator))\
                                .filter(Measure.is_active == True)\
                                .join(Measure.indicator)\
                                .filter(Indicator.is_active == True)\
                                .all()

        # --- Overall Indicator Averages Calculation (excluding all-zero/no-score participants) ---
        excluded_phones_for_avg = get_participants_with_only_zero_scores()
        summary_data['num_participants_in_overall_avg'] = total_participants_in_system - len(excluded_phones_for_avg)

        all_scores_for_overall_avg_query = db.session.query(Score.indicator_id, Score.measure_id, Score.value)\
                                               .filter(Score.participant_phone.notin_(excluded_phones_for_avg))
        all_scores_data_for_overall_avg = all_scores_for_overall_avg_query.all()
        
        all_scores_lookup_for_overall_avg = {}
        for score_data in all_scores_data_for_overall_avg:
            target_type = 'indicator' if score_data.indicator_id else 'measure'
            target_id = score_data.indicator_id if score_data.indicator_id else score_data.measure_id
            if target_id is None: continue
            key = (target_type, target_id)
            if key not in all_scores_lookup_for_overall_avg:
                all_scores_lookup_for_overall_avg[key] = []
            all_scores_lookup_for_overall_avg[key].append(score_data.value)

        overall_indicator_averages = {}
        for indicator in active_indicators:
            indicator_id = indicator.id
            total_weight_for_avg = 0.0
            weighted_sum_for_avg = 0.0
            
            if indicator.allow_direct_score:
                direct_scores_for_avg = all_scores_lookup_for_overall_avg.get(('indicator', indicator_id), [])
                if direct_scores_for_avg:
                    overall_indicator_averages[indicator_id] = sum(direct_scores_for_avg) / len(direct_scores_for_avg)
                else:
                    overall_indicator_averages[indicator_id] = 0.0
            else:
                indicator_measures = [m for m in active_measures if m.indicator_id == indicator_id]
                for measure in indicator_measures:
                    measure_scores_for_avg = all_scores_lookup_for_overall_avg.get(('measure', measure.id), [])
                    if measure_scores_for_avg:
                        avg_measure_score = sum(measure_scores_for_avg) / len(measure_scores_for_avg)
                        weighted_sum_for_avg += avg_measure_score * measure.weight
                        total_weight_for_avg += measure.weight
                overall_indicator_averages[indicator_id] = (weighted_sum_for_avg / total_weight_for_avg) if total_weight_for_avg > 0 else 0.0
        summary_data['all_indicators_avg'] = overall_indicator_averages
        # --- End Overall Indicator Averages Calculation ---

        # --- Context-Specific Score Calculation (Individual or Summary) ---
        indicator_scores_calculated_for_context = {}
        scores_by_participant_map = {} # For individual mode lookup

        if calculation_mode == "individual":
            # Populate scores_by_participant_map for the specific participant
            # participant_actual_scores was fetched earlier
            scores_by_participant_map[participant_phone] = {'measures': {}, 'indicators': {}}
            for s in participant_actual_scores:
                if s.measure_id:
                    scores_by_participant_map[participant_phone]['measures'][s.measure_id] = s.value
                elif s.indicator_id:
                    scores_by_participant_map[participant_phone]['indicators'][s.indicator_id] = s.value
        
        for indicator in active_indicators:
            indicator_id = indicator.id
            calculated_score_ctx = 0.0

            if calculation_mode == "individual":
                # Use the individual participant's scores
                participant_scores_data = scores_by_participant_map.get(participant_phone, {'measures': {}, 'indicators': {}})
                if indicator.allow_direct_score:
                    calculated_score_ctx = participant_scores_data['indicators'].get(indicator_id, 0.0)
                else:
                    total_weight_indiv = 0.0
                    weighted_sum_indiv = 0.0
                    indicator_measures = [m for m in active_measures if m.indicator_id == indicator_id]
                    for measure in indicator_measures:
                        measure_score_indiv = participant_scores_data['measures'].get(measure.id)
                        if measure_score_indiv is not None: # Check for None, 0.0 is a valid score
                            weighted_sum_indiv += measure_score_indiv * measure.weight
                            total_weight_indiv += measure.weight
                    if total_weight_indiv > 0:
                        calculated_score_ctx = weighted_sum_indiv / total_weight_indiv
                indicator_scores_calculated_for_context[indicator_id] = calculated_score_ctx
            else: # Summary mode - use the already calculated overall_indicator_averages
                indicator_scores_calculated_for_context[indicator_id] = overall_indicator_averages.get(indicator_id, 0.0)

        # Aggregate into axes
        axes_dict = {}
        total_weighted_sum_all_context = 0.0
        total_weight_all_context = 0.0

        for indicator in active_indicators:
            if not indicator.axis: continue
            axis_id = indicator.axis_id
            axis_name = indicator.axis.name

            if axis_id not in axes_dict:
                axes_dict[axis_id] = {'id': axis_id, 'name': axis_name, 'indicators': [], 'total_weighted_score': 0.0, 'total_weight': 0.0}

            indicator_score_ctx = indicator_scores_calculated_for_context.get(indicator.id, 0.0)
            axes_dict[axis_id]['indicators'].append({'id': indicator.id, 'name': indicator.name, 'score': indicator_score_ctx, 'weight': indicator.weight})
            axes_dict[axis_id]['total_weighted_score'] += indicator_score_ctx * indicator.weight
            axes_dict[axis_id]['total_weight'] += indicator.weight
            
            total_weighted_sum_all_context += indicator_score_ctx * indicator.weight
            total_weight_all_context += indicator.weight

        for axis_data_val in axes_dict.values():
            axis_data_val['axis_score'] = (axis_data_val['total_weighted_score'] / axis_data_val['total_weight']) if axis_data_val['total_weight'] > 0 else 0.0
            summary_data['axes'].append(axis_data_val)

        summary_data['overall_score'] = (total_weighted_sum_all_context / total_weight_all_context) if total_weight_all_context > 0 else 0.0

        summary_data['axes'].sort(key=lambda x: x['name'])
        for axis_item in summary_data['axes']:
             axis_item['indicators'].sort(key=lambda x: x['name'])

    except Exception as e:
        print(f"Error calculating scores (Mode: {calculation_mode}, Participant: {participant_phone}): {e}")
        traceback.print_exc()
        flash(f"خطا در محاسبه نتایج: {e}", "danger")
        # Ensure participant object is present if in individual mode and an error occurred mid-way
        if participant_phone and 'participant' not in summary_data:
            summary_data['participant'] = Participant.query.get(participant_phone)


    print(f"--- Score Calculation Complete --- Mode: {calculation_mode}, Overall Score: {summary_data['overall_score']}")
    if calculation_mode == "individual":
        print(f"Individual participant ({participant_phone}) all_scores_zero_for_individual: {summary_data['all_scores_zero_for_individual']}")
    print(f"Number of participants included in overall average calculations: {summary_data['num_participants_in_overall_avg']}")
    return summary_data


@results_bp.route('/summary')
@login_required
def summary():
    """Displays the summary results page. Requires admin login."""
    summary_data = calculate_scores_internal()
    help_text = get_results_help_text()

    chart_data = {}
    if summary_data and summary_data.get('axes'):
        for axis in summary_data['axes']:
            if axis.get('indicators'):
                chart_data[axis['id']] = {
                    'name': axis['name'],
                    'labels': [ind['name'] for ind in axis['indicators']],
                    'participant_or_avg_scores': [round(ind['score'], 2) for ind in axis['indicators']],
                    'overall_indicator_averages': [round(summary_data['all_indicators_avg'].get(ind['id'], 0.0), 2) for ind in axis['indicators']]
                }
            else:
                print(f"Warning: No indicators found for axis '{axis['name']}' (ID: {axis['id']}) when preparing chart data for overall summary.")
    else:
        print("Warning: No axes data found in summary_data for overall summary page.")
        # flash("داده‌ای برای نمایش خلاصه نتایج یافت نشد.", "warning") # Potentially

    return render_template(
        'results/summary.html',
        summary_data=summary_data, # Includes num_participants_in_overall_avg
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

    if summary_data is None: # Participant not found
        flash(f"شرکت‌کننده‌ای با شماره تلفن {phone} یافت نشد.", "warning")
        return redirect(url_for('participant_view.my_results_login') if is_participant_view else url_for('participants.list_participants'))

    if not summary_data.get('participant'): # Should be redundant if summary_data is not None
         flash(f"اطلاعات شرکت‌کننده با شماره {phone} به طور کامل بارگذاری نشد.", "warning")
         return redirect(url_for('participant_view.my_results_login') if is_participant_view else url_for('participants.list_participants'))

    chart_data = {}
    # Only prepare chart data if not all_scores_zero_for_individual
    if not summary_data.get('all_scores_zero_for_individual', False):
        if summary_data.get('axes'):
            for axis in summary_data['axes']:
                if axis.get('indicators'):
                    chart_data[axis['id']] = {
                        'name': axis['name'],
                        'labels': [ind['name'] for ind in axis['indicators']],
                        'participant_or_avg_scores': [round(ind['score'], 2) for ind in axis['indicators']],
                        'overall_indicator_averages': [round(summary_data['all_indicators_avg'].get(ind['id'], 0.0), 2) for ind in axis['indicators']]
                    }
                else:
                    print(f"Warning: No indicators found for axis '{axis['name']}' (ID: {axis['id']}) for participant {phone}.")
        else:
            print(f"Warning: No axes data found in summary_data for participant {phone}.")

    return render_template(
        'results/participant_summary.html',
        summary_data=summary_data, # Includes all_scores_zero_for_individual and num_participants_in_overall_avg
        chart_data_json=json.dumps(chart_data),
        is_participant_view=is_participant_view,
        help_text=help_text
    )
