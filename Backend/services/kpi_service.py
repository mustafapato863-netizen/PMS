import pandas as pd
import numpy as np
import logging
from typing import Dict, Any, Tuple, Optional, List
from models.schemas import PerformanceRecord, KPIWeight, Target
from repositories.base import KPIWeightsRepository, TargetsRepository
from config.loader import (
    GLOBAL_KPI_ACHIEVEMENT_CAP,
    load_team_config,
    resolve_team_config,
    ConfigurationError,
)
from utils.performance_levels import normalize_performance_level

logger = logging.getLogger(__name__)

def safe_float(val, default=0.0) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

DEFAULT_WEIGHTS = {
    "Inbound": {
        "Attend": 0.70,
        "Booking": 0.10,
        "Quality": 0.05,
        "AHT": 0.05,
        "Other": 0.10  # UTZ or Abandon
    },
    "Outbound": {
        "Attend": 0.70,
        "Booking": 0.10,
        "Quality": 0.10,
        "AHT": 0.00,
        "Other": 0.10  # Reachability
    },
    "Inbound UAE": {
        "Attend": 0.70,
        "Booking": 0.20,
        "Quality": 0.00,
        "AHT": 0.00,
        "Other": 0.10  # Abandon
    },
    "Pre-Approvals IP Offshore": {
        "Rejection": 0.50,
        "InitialError": 0.20,
        "Submission": 0.30
    },
    "Sales": {
        "OPCensus": 0.10,
        "OPRevenue": 0.10,
        "IPCensus": 0.25,
        "IPRevenue": 0.45,
        "Activity": 0.10
    },
    "Coding": {
        "QualityErrors": 0.20,
        "Rejection": 0.50,
        "TAT": 0.30
    },
    "CSR": {
        "Rejection": 0.40,
        "Queries": 0.30,
        "AttendedCR": 0.30
    },
    "Pharmacy": {
        "WaitingTime": 0.20,
        "Leakage": 0.20,
        "TenderCompliance": 0.20,
        "ATV": 0.20,
        "Prescription": 0.20
    },
    "Submission": {
        "initial_rejection_rate": 0.60,
        "submission_within_due_date": 0.40
    },
    "Re-Submission": {
        "quality_errors_rate": 0.20,
        "rejection_rate_after_resubmission": 0.50,
        "tat": 0.30,
    }
}

DEFAULT_TARGETS = {
    "Inbound": {
        "Attend": 0.75,
        "Booking": 0.45,
        "Quality": 0.95,
        "AHT": 150.0,  # 2.5 minutes (150 seconds)
        "Abandon": 0.01, # 1%
        "UTZ": 0.85
    },
    "Outbound": {
        "Attend": 0.55,
        "Booking": 0.46,
        "Quality": 0.95,
        "Reachability": 0.75
    },
    "Inbound UAE": {
        "Attend": 0.75,
        "Booking": 0.60,
        "Abandon": 0.01
    },
    "Pre-Approvals IP Offshore": {
        "Rejection": 0.03,  # 3% target initial rejection rate (lower is better)
        "InitialError": 0.03, # 3% target error rate (lower is better)
        "Submission": 0.90 # 90% within due date
    },
    "Sales": {
        "OPCensus": 1.0,
        "OPRevenue": 1.0,
        "IPCensus": 1.0,
        "IPRevenue": 1.0,
        "Activity": 1.0
    },
    "Coding": {
        "QualityErrors": 0.05,
        "Rejection": 0.04,
        "TAT": 2.5
    },
    "CSR": {
        "Rejection": 0.01,
        "Queries": 0.01,
        "AttendedCR": 0.90
    },
    "Pharmacy": {
        "WaitingTime": 15.0,
        "Leakage": 0.10,
        "TenderCompliance": 0.75,
        "ATV": 600.0,
        "Prescription": 100.0
    },
    "Submission": {
        "initial_rejection_rate": 0.04,
        "submission_within_due_date": 0.90
    },
    "Re-Submission": {
        "quality_errors_rate": 0.05,
        "rejection_rate_after_resubmission": 0.60,
        "tat": 1.00,
    }
}

class KPIService:
    def __init__(
        self,
        weights_repo: KPIWeightsRepository,
        targets_repo: TargetsRepository,
        *,
        initialize_defaults: bool | None = None,
    ):
        self.weights_repo = weights_repo
        self.targets_repo = targets_repo
        # Retained as a keyword-only compatibility argument for deterministic
        # calculation callers. Default initialization is owned by repositories,
        # not by the calculation service itself.
        self.initialize_defaults = initialize_defaults

    def calculate_performance(self, team: str, row: Dict[str, Any], performance_level: str = "Employee") -> Tuple[float, str, Dict[str, float], Dict[str, float]]:
        """
        Calculate performance score and grade.
        Returns:
          - score (float): 0-100 range
          - grade (str)
          - achievements (dict): map of KPI name to achievement rate (0-1)
          - weights (dict): KPI weights used for this calculation
        """
        performance_level = normalize_performance_level(performance_level)
        if performance_level != "Employee":
            score, grade, kpi_values_list = self.calculate_performance_multi_team(team, row, performance_level)
            return (
                score,
                grade,
                {value['kpi_key']: value['achievement_ratio'] for value in kpi_values_list},
                {value['kpi_key']: value['weight_applied'] for value in kpi_values_list},
            )

        # Load weights and targets (fallback to defaults if repo fails)
        w_record = self.weights_repo.get_by_team(team)
        weights = w_record.weights if w_record else DEFAULT_WEIGHTS.get(team, {})

        target_rec = self.targets_repo.get_by_team(team)
        targets = target_rec.targets if target_rec else DEFAULT_TARGETS.get(team, {})

        achievements = {}
        final_weights = {}

        # Import helper functions
        from utils.helpers import convert_aht_to_minutes, convert_percentage

        if team not in ["Inbound", "Outbound", "Inbound UAE", "Pre-Approvals IP Offshore", "Sales"]:
            try:
                score, grade, kpi_values_list = self.calculate_performance_multi_team(team, row, performance_level)
                achievements = {kv['kpi_key']: kv['achievement_ratio'] for kv in kpi_values_list}
                final_weights = {kv['kpi_key']: kv['weight_applied'] for kv in kpi_values_list}
                
                # Write back for backward compatibility
                row["PerformanceScore%"] = score
                row["PerformanceScor%"] = score
                row["PerformanceScore"] = score
                row["Performance_Score"] = score
                
                return score, grade, achievements, final_weights
            except Exception as e:
                logger.error(f"Error calculating performance for multi-team {team}: {e}")

        if team == "Inbound":
            # 1. Raw Inbound Volumes
            total_handled = safe_float(row.get("TotalHandledCalls"))
            
            dubai_booking = safe_float(row.get("Dubai_Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking"))
            ajman_booking = safe_float(row.get("Ajman_Booking"))
            clinics_booking = safe_float(row.get("Clinics_Booking"))
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend"))
            ajman_attend = safe_float(row.get("Ajman_Attend"))
            clinics_attend = safe_float(row.get("Clinics_Attend") or row.get("clinics.Attend") or row.get("clinics_Attend") or row.get("Clinics.Attend"))
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            inbound_calls = safe_float(row.get("InboundCalls") or row.get("InboundCalls "))
            abandoned_calls = safe_float(row.get("AbandonedCalls"))

            # 2. Actual Rate Calculations
            actual_booking_cr = total_bookings / total_handled if total_handled > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_abandon_rate = abandoned_calls / inbound_calls if inbound_calls > 0 else 0.0
            
            # Fetch actual quality
            actual_quality = convert_percentage(row.get("A.QualityScore", 0.0))
            # Fetch actual UTZ
            actual_utz = convert_percentage(row.get("A.UTZ%", 0.0))

            # Fetch target values
            t_booking = targets.get("Booking", 0.45)
            t_attend = targets.get("Attend", 0.75)
            t_aht = targets.get("AHT", 150.0)
            t_quality = targets.get("Quality", 0.95)
            t_utz = targets.get("UTZ", 0.85)
            t_abandon = targets.get("Abandon", 0.01)

            # Get Actual AHT in seconds
            aht_val = row.get("AHT_Minutes")
            if aht_val is None or pd.isna(aht_val):
                raw_aht = row.get("AHT") or row.get("A.AHT") or row.get("A.AHT.1")
                aht_minutes = convert_aht_to_minutes(raw_aht)
            else:
                aht_minutes = safe_float(aht_val)
            actual_aht_seconds = aht_minutes * 60.0

            # 3. Achievement Calculations (Capped at 1.0)
            attend_ach = actual_attend_cr / t_attend if t_attend > 0 else 0.0
            booking_ach = actual_booking_cr / t_booking if t_booking > 0 else 0.0
            quality_ach = actual_quality / t_quality if t_quality > 0 else 0.0
            aht_ach = t_aht / actual_aht_seconds if actual_aht_seconds > 0 else 0.0
            utz_ach = actual_utz / t_utz if t_utz > 0 else 0.0
            
            # Abandon achievement is Target / Actual (inverse metric)
            if actual_abandon_rate <= t_abandon:
                abandon_ach = 1.0
            else:
                abandon_ach = t_abandon / actual_abandon_rate if actual_abandon_rate > 0 else 1.0

            # 4. Swappable UTZ / Abandon metric logic
            utz_raw = row.get("A.UTZ%")
            if utz_raw is None or (isinstance(utz_raw, float) and np.isnan(utz_raw)) or pd.isna(utz_raw):
                other_ach = abandon_ach
            else:
                other_ach = utz_ach

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Quality": quality_ach,
                "AHT": aht_ach,
                "Other": other_ach
            }
            
            date_val = row.get("Date")
            is_june_2026 = False
            if date_val:
                if hasattr(date_val, "month") and hasattr(date_val, "year"):
                    is_june_2026 = (date_val.month == 6 and date_val.year == 2026)
                elif isinstance(date_val, str):
                    is_june_2026 = ('2026-06' in date_val or '/06/2026' in date_val or 'June 2026' in date_val)

            w_booking = weights.get("Booking", 0.10)
            w_attend = weights.get("Attend", 0.70)
            w_aht = weights.get("AHT", 0.05)
            w_quality = 0.0 if is_june_2026 else weights.get("Quality", 0.05)
            w_other = 0.15 if is_june_2026 else weights.get("Other", 0.10)

            final_weights = {
                "Booking": w_booking,
                "Attend": w_attend,
                "AHT": w_aht,
                "Quality": w_quality,
                "Other": w_other
            }

            # Inject computed values back to row for backward compatibility
            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.AbandonRate%"] = actual_abandon_rate
            row["A.UTZ%"] = actual_utz
            row["A.QualityScore"] = actual_quality
            row["AHT_Minutes"] = aht_minutes
            row["Booking%Ach%"] = booking_ach
            row["Attend%Ach%"] = attend_ach
            row["QualityTargetAch%"] = quality_ach
            row["AHTAch%"] = aht_ach
            row["UTZ%Ach%"] = utz_ach
            row["AbandonRate%Ach%"] = abandon_ach

        elif team == "Outbound":
            # 1. Raw Outbound Volumes
            reached = safe_float(row.get("Reached"))
            num_leads = safe_float(row.get("NumOfLeads") or row.get("NumOfLeads "))
            
            dubai_booking = safe_float(row.get("Dubai_Booking") or row.get("Dubai _Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking") or row.get("Sharjah_Booking "))
            ajman_booking = safe_float(row.get("Ajman_Booking") or row.get("Ajman_Booking "))
            clinics_booking = safe_float(row.get("Clinics_Booking") or row.get("Clinics _Booking") or row.get("clinics_Booking") or row.get("clinics.Booking") or 0.0)
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend") or row.get("Dubai _Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend") or row.get("Sharjah_Attend "))
            ajman_attend = safe_float(row.get("Ajman_Attend") or row.get("Ajman_Attend "))
            clinics_attend = safe_float(row.get("Clinics_Attend") or row.get("Clinics_Attend ") or row.get("clinics_Attend") or row.get("clinics.Attend") or 0.0)
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            actual_booking_cr = total_bookings / reached if reached > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_reachability = reached / num_leads if num_leads > 0 else 0.0
            actual_quality = convert_percentage(row.get("A.QualityScore", 0.0))

            t_booking = targets.get("Booking", 0.55)
            t_attend = targets.get("Attend", 0.75)
            t_quality = targets.get("Quality", 0.95)
            t_reachability = targets.get("Reachability", 0.95)

            booking_ach = actual_booking_cr / t_booking if t_booking > 0 else 0.0
            attend_ach = actual_attend_cr / t_attend if t_attend > 0 else 0.0
            quality_ach = actual_quality / t_quality if t_quality > 0 else 0.0
            reachability_ach = actual_reachability / t_reachability if t_reachability > 0 else 0.0

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Quality": quality_ach,
                "Other": reachability_ach
            }
            date_val = row.get("Date")
            is_june_26 = False
            if date_val:
                if hasattr(date_val, "month") and hasattr(date_val, "year"):
                    is_june_26 = (date_val.month == 6 and date_val.year == 2026)
                elif isinstance(date_val, str):
                    is_june_26 = ('2026-06' in date_val or '/06/2026' in date_val or 'June 2026' in date_val or 'June' in date_val)

            w_quality = 0.00 if is_june_26 else weights.get("Quality", 0.10)
            w_other = 0.20 if is_june_26 else weights.get("Other", 0.10)

            final_weights = {
                "Attend": weights.get("Attend", 0.70),
                "Booking": weights.get("Booking", 0.10),
                "Quality": w_quality,
                "Other": w_other
            }

            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.Reachability%"] = actual_reachability
            row["A.QualityScore"] = actual_quality
            row["BookingC.RAch%"] = booking_ach
            row["AttendC.RAch%"] = attend_ach
            row["QualityAch%"] = quality_ach
            row["Reachability%Ach%"] = reachability_ach

        elif team == "Inbound UAE":
            # 1. Raw UAE Inbound Volumes
            total_handled = safe_float(row.get("TotalHandledCalls"))
            inbound_calls = safe_float(row.get("InboundCalls") or row.get("InboundCalls "))
            abandoned_calls = safe_float(row.get("AbandonedCalls"))
            
            dubai_booking = safe_float(row.get("Dubai_Booking") or row.get("Dubai _Booking"))
            sharjah_booking = safe_float(row.get("Sharjah_Booking") or row.get("Sharjah_Booking "))
            ajman_booking = safe_float(row.get("Ajman_Booking") or row.get("Ajman_Booking "))
            clinics_booking = safe_float(row.get("Clinics_Booking") or row.get("Clinics _Booking"))
            total_bookings = dubai_booking + sharjah_booking + ajman_booking + clinics_booking

            dubai_attend = safe_float(row.get("Dubai_Attend") or row.get("Dubai _Attend"))
            sharjah_attend = safe_float(row.get("Sharjah_Attend") or safe_float(row.get("Sharjah_Attend ")))
            ajman_attend = safe_float(row.get("Ajman_Attend") or safe_float(row.get("Ajman_Attend ")))
            clinics_attend = safe_float(row.get("Clinics_Attend") or safe_float(row.get("Clinics_Attend ")))
            total_attends = dubai_attend + sharjah_attend + ajman_attend + clinics_attend

            actual_booking_cr = total_bookings / total_handled if total_handled > 0 else 0.0
            actual_attend_cr = total_attends / total_bookings if total_bookings > 0 else 0.0
            actual_abandon_rate = abandoned_calls / inbound_calls if inbound_calls > 0 else 0.0

            t_booking = targets.get("Booking", 0.60)
            t_attend = targets.get("Attend", 0.75)
            t_abandon = targets.get("Abandon", 0.01)

            booking_ach = actual_booking_cr / t_booking if t_booking > 0 else 0.0
            attend_ach = actual_attend_cr / t_attend if t_attend > 0 else 0.0
            
            if actual_abandon_rate <= t_abandon:
                abandon_ach = 1.0
            else:
                abandon_ach = t_abandon / actual_abandon_rate if actual_abandon_rate > 0 else 1.0

            achievements = {
                "Attend": attend_ach,
                "Booking": booking_ach,
                "Other": abandon_ach
            }
            final_weights = {
                "Attend": weights.get("Attend", 0.70),
                "Booking": weights.get("Booking", 0.20),
                "Other": weights.get("Other", 0.10)
            }

            row["A.Booking%"] = actual_booking_cr
            row["A.Attend%"] = actual_attend_cr
            row["A.AbandonRate%"] = actual_abandon_rate
            row["BookingC.RAch%"] = booking_ach
            row["AttendC.RAch%"] = attend_ach
            row["AbandonRateAch%"] = abandon_ach

        elif team == "Pre-Approvals IP Offshore":
            actual_rejection = convert_percentage(row.get("IPInitialRejection%", 0.0))
            actual_error = convert_percentage(row.get("Error%", 0.0))
            actual_submission = convert_percentage(row.get("NumberApprovalwithin48hrs") or row.get("NumberApprovalwithin48hrs ") or 0.0)

            t_rej = targets.get("Rejection", 0.03)
            t_err = targets.get("InitialError", 0.03)
            t_sub = targets.get("Submission", 0.90)

            claims = safe_float(row.get("SubmittedClaims"))
            
            # Rejection achievement is inverse
            if actual_rejection <= t_rej:
                rejection_ach = 1.0
            else:
                rejection_ach = t_rej / actual_rejection if actual_rejection > 0 else 1.0
            
            # Error achievement is inverse, 0 if no claims
            if claims == 0:
                initial_error_ach = 0.0
            else:
                if actual_error <= t_err:
                    initial_error_ach = 1.0
                else:
                    initial_error_ach = t_err / actual_error if actual_error > 0 else 1.0
            
            # Submission achievement follows the global 100% cap.
            submission_ach = min(actual_submission / t_sub, 1.0) if t_sub > 0 else 0.0

            # Dynamic weights logic
            if claims == 0:
                w_rej = 0.60
                w_err = 0.00
                w_sub = 0.40
            else:
                w_rej = 0.50
                w_err = 0.20
                w_sub = 0.30

            achievements = {
                "Rejection": rejection_ach,
                "InitialError": initial_error_ach,
                "Submission": submission_ach
            }
            final_weights = {
                "Rejection": w_rej,
                "InitialError": w_err,
                "Submission": w_sub
            }

            row["IPInitialRejection%"] = actual_rejection
            row["Error%"] = actual_error
            row["NumberApprovalwithin48hrs"] = actual_submission
            row["RejectionRate"] = rejection_ach
            row["InitialError%"] = initial_error_ach
            row["%ofSubmissionWithinDuedate"] = submission_ach

        elif team == "Sales":
            # Extract KPI weights and targets
            w_op_census = weights.get("OPCensus", 0.10)
            w_op_rev = weights.get("OPRevenue", 0.10)
            w_ip_census = weights.get("IPCensus", 0.25)
            w_ip_rev = weights.get("IPRevenue", 0.45)
            w_activity = weights.get("Activity", 0.10)

            # Extract achievements from raw data (safely handle already parsed/cleaned columns)
            # Remove spaces in keys just in case we are dealing with uncleaned raw row keys
            clean_row = {str(k).replace(" ", ""): v for k, v in row.items()}
            
            # Dynamic achievement calculation: actual / target
            if "A.OPCensus" in clean_row and "T.OPCensus" in clean_row:
                a_op_census = safe_float(clean_row.get("A.OPCensus"))
                t_op_census = safe_float(clean_row.get("T.OPCensus"))
                op_census_ach = a_op_census / t_op_census if t_op_census > 0 else 0.0
            else:
                op_census_ach = convert_percentage(clean_row.get("OPCensusAch%"))

            if "A.OPRevenue" in clean_row and "T.OPRevenue" in clean_row:
                a_op_rev = safe_float(clean_row.get("A.OPRevenue"))
                t_op_rev = safe_float(clean_row.get("T.OPRevenue"))
                op_revenue_ach = a_op_rev / t_op_rev if t_op_rev > 0 else 0.0
            else:
                op_revenue_ach = convert_percentage(clean_row.get("OPRevenueAch%"))

            if "A.IPCensus" in clean_row and "T.IPCensus" in clean_row:
                a_ip_census = safe_float(clean_row.get("A.IPCensus"))
                t_ip_census = safe_float(clean_row.get("T.IPCensus"))
                ip_census_ach = a_ip_census / t_ip_census if t_ip_census > 0 else 0.0
            else:
                ip_census_ach = convert_percentage(clean_row.get("IPCensusAch%"))

            if "A.IPRevenue" in clean_row and "T.IPRevenue" in clean_row:
                a_ip_rev = safe_float(clean_row.get("A.IPRevenue"))
                t_ip_rev = safe_float(clean_row.get("T.IPRevenue"))
                ip_revenue_ach = a_ip_rev / t_ip_rev if t_ip_rev > 0 else 0.0
            else:
                ip_revenue_ach = convert_percentage(clean_row.get("IPRevenueAch%"))

            # Calculate activity ratio/score (mirroring sales.py logic)
            activity_keywords = ['ClinicActivity', 'CorporateActivity', 'CBDTour', 'Visits']
            all_act_cols = [c for c in clean_row.keys() if any(k in c for k in activity_keywords) and 'Ach%' not in c]
            
            if any(c.startswith('T.') for c in all_act_cols) or any(c.startswith('A.') for c in all_act_cols):
                t_act_cols = [c for c in all_act_cols if c.startswith('T.')]
                a_act_cols = [c for c in all_act_cols if c.startswith('A.')]
            else:
                t_act_cols = [c for c in all_act_cols if not c.endswith('.1') and not c.endswith('.2')]
                a_act_cols = [c for c in all_act_cols if c.endswith('.1') or c.endswith('.2')]
                if len(t_act_cols) != len(a_act_cols):
                    half = len(all_act_cols) // 2
                    t_act_cols = all_act_cols[:half]
                    a_act_cols = all_act_cols[half:]

            sum_actual_activity = sum(safe_float(clean_row.get(c)) for c in a_act_cols)
            sum_target_activity = sum(safe_float(clean_row.get(c)) for c in t_act_cols)
            
            activity_ratio = sum_actual_activity / sum_target_activity if sum_target_activity > 0 else 0.0
            activity_ach = activity_ratio

            achievements = {
                "OPCensus": safe_float(op_census_ach),
                "OPRevenue": safe_float(op_revenue_ach),
                "IPCensus": safe_float(ip_census_ach),
                "IPRevenue": safe_float(ip_revenue_ach),
                "Activity": safe_float(activity_ach)
            }
            final_weights = {
                "OPCensus": w_op_census,
                "OPRevenue": w_op_rev,
                "IPCensus": w_ip_census,
                "IPRevenue": w_ip_rev,
                "Activity": w_activity
            }

            # Map back to standardized keys on the original row
            row["OPCensusAch%"] = op_census_ach
            row["OPRevenueAch%"] = op_revenue_ach
            row["IPCensusAch%"] = ip_census_ach
            row["IPRevenueAch%"] = ip_revenue_ach
            row["ActivityAch%"] = activity_ach

        # Excel can expose unavailable formulas as NaN. A zero-weight period
        # exception must not let NaN * 0 poison the complete score.
        achievements = {
            key: max(safe_float(value), 0.0)
            for key, value in achievements.items()
        }
        final_weights = {
            key: max(safe_float(value), 0.0)
            for key, value in final_weights.items()
        }

        # Calculate score (normalized to 0-100)
        raw_score = 0.0
        for kpi, ach in achievements.items():
            wt = final_weights.get(kpi, 0.0)
            # Sales uses capped KPI contributions: an over-target source
            # volume must not compensate for a different KPI below target.
            raw_score += (min(ach, 1.0) if team == "Sales" else ach) * wt

        score = float(round(min(raw_score, 1.0) * 100.0, 2))
        grade = self.assign_grade(score)

        # Write score back to row
        if team == "Inbound":
            row["PerformanceScore%"] = score
        elif team in ["Outbound", "Pre-Approvals IP Offshore"]:
            row["PerformanceScor%"] = score
        elif team == "Inbound UAE":
            row["PerformanceScore%"] = score
        elif team == "Sales":
            row["PerformanceScore%"] = score
            row["PerformanceScore"] = score
            row["Performance_Score"] = score

        return score, grade, achievements, final_weights

    @staticmethod
    def assign_grade(score: float) -> str:
        """Assign performance grade based on unified thresholds.
        
        Thresholds:
        - A: score >= 95
        - B: score >= 85
        - C: score >= 75
        - D: score >= 65
        - E: score < 65
        
        These thresholds are unified with Frontend (constants/grades.ts)
        to ensure consistent grading across the system.
        """
        if score >= 95.0:
            return "A"
        elif score >= 90.0:
            return "B"
        elif score >= 80.0:
            return "C"
        elif score >= 70.0:
            return "D"
        else:
            return "E"

    def calculate_performance_multi_team(
        self,
        team_id: str,
        row: Dict[str, Any],
        performance_level: str = "Employee",
        position_name: str | None = None,
    ) -> Tuple[float, str, List[Dict[str, Any]]]:
        """
        Calculate performance score and grade for multi-team support (Pharmacy, Coding, CSR).
        
        Args:
            team_id: Team identifier (e.g., "Pharmacy", "Coding", "CSR")
            row: Data row from Excel with actual/target values
            performance_level: Employee, Managerial, or Corporate configuration scope
            position_name: Optional position/workstream within the performance level
            
        Returns:
            Tuple of (score, grade, kpi_values_list)
            
            where kpi_values_list contains dicts with:
                - kpi_key: KPI identifier
                - actual_value: Parsed actual value
                - target_value: Parsed target value
                - achievement_ratio: Calculated achievement (as decimal 0-N)
                - weight_applied: Weight for this KPI
                - contribution: achievement × weight
        """
        try:
            config = resolve_team_config(
                load_team_config(team_id),
                performance_level,
                position_name,
            )
        except ConfigurationError as e:
            logger.error(f"Failed to load config for team {team_id}: {e}")
            raise
        
        # Extract team metadata
        team_name = config.get('team')
        grade_thresholds = config.get('grade_thresholds', {})
        kpis = config.get('kpis', [])
        missing_actual_exception = config.get('missing_actual_exception')

        missing_columns = sorted({
            str(column)
            for kpi in kpis
            for column in (kpi.get('actual_col'), kpi.get('target_col'))
            if column and self._find_row_key(row, str(column)) is None
        })
        if missing_columns:
            raise ConfigurationError(
                f"Missing {config['performance_level']} KPI columns for {team_name}: {', '.join(missing_columns)}"
            )
        
        logger.info(f"Calculating performance for {team_name} with {len(kpis)} KPIs")
        
        kpi_values_list = []
        achievements = {}
        exception_triggered = False
        exception_primary_achievement = None
        
        # Calculate achievement for each KPI
        for kpi_def in kpis:
            kpi_key = kpi_def.get('key')
            actual_col = kpi_def.get('actual_col')
            target_col = kpi_def.get('target_col')
            direction = kpi_def.get('direction')  # 'higher_better' or 'lower_better'
            weight = float(kpi_def.get('weight', 0.0))
            actual_key = self._find_row_key(row, str(actual_col)) if actual_col else None
            raw_actual_value = row.get(actual_key) if actual_key is not None else None
            actual_is_missing = self._is_missing_raw_value(raw_actual_value)
            if missing_actual_exception == 'initial_rejection_only' and actual_is_missing:
                exception_triggered = True
            # Parse actual and target from row
            actual_value = self._resolve_row_value(row, actual_col)
            target_value = self._resolve_row_value(row, target_col)
            achievement_col = kpi_def.get('achievement_col')
            precomputed_achievement = None
            if achievement_col:
                achievement_raw = self._resolve_row_value(row, achievement_col)
                normalized_achievement_col = self._normalize_key(achievement_col)
                has_achievement_col = any(self._normalize_key(key) == normalized_achievement_col for key in row.keys())
                if has_achievement_col:
                    precomputed_achievement = achievement_raw if achievement_raw > 2.0 else achievement_raw * 100.0
            
            # Calculate achievement
            is_inverse = direction == 'lower_better'
            if precomputed_achievement is not None:
                achievement = max(precomputed_achievement, 0.0)
            elif target_value == 0.0:
                # Try to search for precalculated achievement in row
                found_ach_val = None
                possible_keys = [
                    f"{kpi_key}Ach%", f"{kpi_key}Ach", f"Noof{kpi_key}Ach%",
                    f"{kpi_key}_Achievement", f"{kpi_key}RateAch%"
                ]
                for possible_key in possible_keys:
                    for r_key in row.keys():
                        if r_key.replace(" ", "").replace("_", "").lower() == possible_key.replace(" ", "").replace("_", "").lower():
                            found_ach_val = self._parse_kpi_value(row, r_key)
                            break
                    if found_ach_val is not None:
                        break
                
                if found_ach_val is not None:
                    # Scale decimal achievement (e.g. 1.04) to percentage scale (104.4)
                    achievement = found_ach_val if found_ach_val > 2.0 else found_ach_val * 100.0
                else:
                    achievement = 0.0
            else:
                achievement = self._calculate_achievement(
                    actual_value,
                    target_value,
                    is_inverse=is_inverse,
                    cap_at_100=False
                )
            
            # Convert to decimal (0-1 scale) for storage.  Achievement is a
            # product-wide capped metric; legacy per-team ``uncapped`` flags
            # are normalized by the configuration loader and cannot bypass it.
            achievement_ratio = achievement / 100.0
            cap_achievement = True
            effective_ratio = min(achievement_ratio, GLOBAL_KPI_ACHIEVEMENT_CAP)

            # Persist the effective achievement so every consumer (cards,
            # analysis, exports, and scorecards) uses the same 0-100 rule.
            contribution = effective_ratio * weight
            stored_achievement_ratio = effective_ratio
            
            kpi_value = {
                'kpi_key': kpi_key,
                'label': kpi_def.get('label', kpi_key),
                'unit': kpi_def.get('unit', '%'),
                'color': kpi_def.get('color', '#3B82F6'),
                'direction': direction,
                'actual_value': float(actual_value),
                'target_value': float(target_value),
                'achievement_ratio': float(round(stored_achievement_ratio, 4)),
                'weight_applied': float(weight),
                'contribution': float(round(contribution, 4))
            }
            kpi_values_list.append(kpi_value)
            achievements[kpi_key] = effective_ratio
            if kpi_key == 'initial_rejection_rate':
                exception_primary_achievement = effective_ratio
            
            logger.debug(
                f"{team_name}/{kpi_key}: actual={actual_value}, target={target_value}, "
                f"achievement={achievement:.2f}%, effective={effective_ratio * 100.0:.2f}%, "
                f"weight={weight}, contribution={contribution:.4f}"
            )
        
        # Calculate final performance score
        if exception_triggered and missing_actual_exception == 'initial_rejection_only':
            score_decimal = exception_primary_achievement or 0.0
        else:
            score_decimal = self._calculate_weighted_score(
                achievements,
                {kpi_def.get('key'): float(kpi_def.get('weight', 0.0)) for kpi_def in kpis},
                cap_final_at_100=True
            )
        
        # Convert to 0-100 scale
        score = score_decimal * 100.0
        
        # Assign grade using team-specific thresholds
        grade = self._assign_grade_with_thresholds(score, grade_thresholds)
        
        logger.info(f"{team_name} final score: {score:.2f}, grade: {grade}")
        
        return score, grade, kpi_values_list

    def _parse_kpi_value(self, row: Dict[str, Any], col_name: str) -> float:
        """
        Parse and normalize KPI value from row.
        
        Handles:
        - Percentage strings: "95%", "0.95"
        - Numeric values: 95, 0.95, etc.
        - NaN/None values: returns 0.0
        
        Args:
            row: Data row dict
            col_name: Column name to extract
            
        Returns:
            Normalized float value
        """
        value = row.get(col_name)
        
        if value is None or pd.isna(value):
            return 0.0
        
        # Handle string percentages
        if isinstance(value, str):
            value = value.rstrip('%').replace(',', '').strip()
            try:
                numeric = float(value)
            except (ValueError, AttributeError):
                logger.warning(f"Could not parse value from column {col_name}: {value}")
                return 0.0
        else:
            try:
                numeric = float(value)
            except (ValueError, TypeError):
                logger.warning(f"Could not parse value from column {col_name}: {value}")
                return 0.0
        
        # Normalize fractional values to raw scale (don't multiply by 100)
        # The formulas (actual/target) will naturally produce the right ratio
        return numeric

    @staticmethod
    def _normalize_key(key: str) -> str:
        return ''.join(ch.lower() for ch in str(key) if ch.isalnum())

    @staticmethod
    def _is_missing_raw_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip().casefold() in {"", "-", "—", "n/a", "na", "none", "nan"}
        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False

    def _resolve_row_value(self, row: Dict[str, Any], col_name: str) -> float:
        matching_key = self._find_row_key(row, col_name)
        if matching_key is not None:
            return self._parse_kpi_value(row, matching_key)
        return self._parse_kpi_value(row, col_name)

    def _find_row_key(self, row: Dict[str, Any], col_name: str) -> str | None:
        if col_name in row:
            return col_name

        prefix = None
        if isinstance(col_name, str) and len(col_name) >= 2 and col_name[1] == '.':
            prefix = col_name[0].lower()

        candidates = [col_name]
        for suffix in ('Rate', 'Hours', 'Target'):
            if suffix in col_name:
                candidates.append(col_name.replace(suffix, ''))
        if 'CPTConversion' in col_name:
            candidates.append(col_name.replace('CPTConversion', 'AttendedCR'))
        if 'AttendedCR' in col_name:
            candidates.append(col_name.replace('AttendedCR', 'CPTConversion'))

        norm_candidates = {self._normalize_key(c) for c in candidates}
        preferred_keys = []
        fallback_keys = []
        for key in row.keys():
            key_prefix = key[0].lower() if isinstance(key, str) and len(key) >= 2 and key[1] == '.' else None
            if prefix and key_prefix == prefix:
                preferred_keys.append(key)
            else:
                fallback_keys.append(key)

        for key in preferred_keys + fallback_keys:
            norm_key = self._normalize_key(key)
            if norm_key in norm_candidates:
                return key
            for candidate in norm_candidates:
                if not candidate:
                    continue
                stripped_key = norm_key[1:] if len(norm_key) > 1 else norm_key
                stripped_candidate = candidate[1:] if len(candidate) > 1 else candidate
                if candidate in norm_key or norm_key in candidate or stripped_candidate in stripped_key or stripped_key in stripped_candidate:
                    return key
        return None

    def _calculate_achievement(
        self,
        actual: float,
        target: float,
        is_inverse: bool = False,
        cap_at_100: bool = False,
        zero_actual_value: float = 100.0
    ) -> float:
        """
        Calculate KPI achievement ratio (0-100 scale).
        
        Args:
            actual: Actual performance value
            target: Target performance value
            is_inverse: If True, calculate as target/actual (lower is better)
            cap_at_100: If True, cap result at 100
            zero_actual_value: Value to return when actual=0 for inverse KPIs
            
        Returns:
            Achievement ratio on 0-100 scale, capped at 100% by the product rule.
        """
        actual = safe_float(actual)
        target = safe_float(target)
        
        if is_inverse:
            # Lower is better: target/actual
            if actual == 0:
                # No division by zero - assume perfect performance
                achievement = zero_actual_value
            else:
                achievement = (target / actual) * 100.0
        else:
            # Higher is better: actual/target
            if target == 0:
                # Cannot measure achievement if target is zero
                achievement = 0.0 if actual == 0 else 0.0
            else:
                achievement = (actual / target) * 100.0
        
        # The product rule caps every KPI achievement at 100%; retain the
        # argument for backwards compatibility with callers.
        achievement = min(max(achievement, 0.0), 100.0)
        
        return achievement

    def _calculate_weighted_score(
        self,
        achievements: Dict[str, float],
        weights: Dict[str, float],
        cap_final_at_100: bool = False
    ) -> float:
        """
        Calculate weighted performance score.
        
        Args:
            achievements: Dict of KPI -> achievement ratio (0-N decimal scale)
            weights: Dict of KPI -> weight (sum should equal 1.0)
            cap_final_at_100: If True, cap final score at 1.0 (100%)
            
        Returns:
            Weighted score as decimal (0-1 scale)
        """
        score = 0.0
        for kpi, achievement in achievements.items():
            weight = weights.get(kpi, 0.0)
            score += min(max(float(achievement), 0.0), GLOBAL_KPI_ACHIEVEMENT_CAP) * max(float(weight), 0.0)
        
        if cap_final_at_100:
            score = min(max(score, 0.0), GLOBAL_KPI_ACHIEVEMENT_CAP)
        
        return score

    def _assign_grade_with_thresholds(
        self,
        score: float,
        thresholds: Dict[str, int]
    ) -> str:
        """
        Assign grade based on team-specific thresholds.
        
        Args:
            score: Performance score (0-100 scale)
            thresholds: Grade thresholds dict with keys: A, B, C, D
                       Expected format: {"A": 95, "B": 85, "C": 75, "D": 65}
            
        Returns:
            Grade letter: A, B, C, D, or E
        """
        threshold_a = float(thresholds.get('A', 95))
        threshold_b = float(thresholds.get('B', 90))
        threshold_c = float(thresholds.get('C', 80))
        threshold_d = float(thresholds.get('D', 70))
        
        if score >= threshold_a:
            return 'A'
        elif score >= threshold_b:
            return 'B'
        elif score >= threshold_c:
            return 'C'
        elif score >= threshold_d:
            return 'D'
        else:
            return 'E'
