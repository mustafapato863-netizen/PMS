import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from models.schemas import RootCauseInfo, PerformanceRecord
from repositories.base import TargetsRepository

def safe_float(val, default=0.0) -> float:
    if val is None or (isinstance(val, float) and np.isnan(val)) or pd.isna(val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

class AnalysisService:
    def __init__(self, targets_repo: TargetsRepository):
        self.targets_repo = targets_repo

    def run_root_cause_analysis(
        self, team: str, achievements: Dict[str, float], weights: Dict[str, float], row: Dict[str, Any]
    ) -> Optional[RootCauseInfo]:
        """
        Calculates Weighted Gap = Weight * max(0, 1.0 - Achievement) for each KPI.
        The KPI with the highest weighted gap becomes the Root Cause.
        """
        # Find gaps for all KPIs
        gaps = {}
        weighted_gaps = {}

        for kpi, ach in achievements.items():
            wt = weights.get(kpi, 0.0)
            gap = max(0.0, 1.0 - ach)
            gaps[kpi] = gap
            weighted_gaps[kpi] = gap * wt

        total_weighted_gap = sum(weighted_gaps.values())
        if total_weighted_gap <= 0:
            return None

        # Find KPI with the highest weighted gap
        root_kpi = max(weighted_gaps, key=weighted_gaps.get)
        max_weighted_gap = weighted_gaps[root_kpi]

        if max_weighted_gap <= 0:
            return None

        # Safety import check for np nan
        import math

        impact_pct = float(round((max_weighted_gap / total_weighted_gap) * 100, 2))

        # Retrieve actual and target values for display
        actual_val = 0.0
        target_val = 1.0

        t_record = self.targets_repo.get_by_team(team)
        targets = t_record.targets if t_record else {}

        # Resolve KPI actual name and targets depending on sheet
        if team == "Inbound":
            if root_kpi == "Attend":
                actual_val = safe_float(row.get("A.Attend%"))
                target_val = targets.get("Attend", 0.75)
            elif root_kpi == "Booking":
                actual_val = safe_float(row.get("A.Booking%"))
                target_val = targets.get("Booking", 0.45)
            elif root_kpi == "Quality":
                actual_val = safe_float(row.get("A.QualityScore"))
                target_val = targets.get("Quality", 0.95)
            elif root_kpi == "AHT":
                actual_val = safe_float(row.get("AHT_Minutes"))
                target_val = targets.get("AHT", 150.0) / 60.0  # Convert target to minutes
            elif root_kpi == "Other":
                # Swap UTZ and Abandon
                utz_val = row.get("A.UTZ%")
                if utz_val is not None and not np_isnan(utz_val):
                    actual_val = safe_float(utz_val)
                    target_val = targets.get("UTZ", 0.85)
                else:
                    actual_val = safe_float(row.get("A.AbandonRate%"))
                    target_val = targets.get("Abandon", 0.01)

        elif team == "Outbound":
            if root_kpi == "Attend":
                actual_val = safe_float(row.get("A.Attend%"))
                target_val = targets.get("Attend", 0.75)
            elif root_kpi == "Booking":
                actual_val = safe_float(row.get("A.Booking%"))
                target_val = targets.get("Booking", 0.55)
            elif root_kpi == "Quality":
                actual_val = safe_float(row.get("A.QualityScore"))
                target_val = targets.get("Quality", 0.95)
            elif root_kpi == "Other":
                actual_val = safe_float(row.get("A.Reachability%"))
                target_val = targets.get("Reachability", 0.95)

        elif team == "Inbound UAE":
            if root_kpi == "Attend":
                actual_val = safe_float(row.get("A.Attend%"))
                target_val = targets.get("Attend", 0.75)
            elif root_kpi == "Booking":
                actual_val = safe_float(row.get("A.Booking%"))
                target_val = targets.get("Booking", 0.60)
            elif root_kpi == "Other":
                actual_val = safe_float(row.get("A.AbandonRate%"))
                target_val = targets.get("Abandon", 0.01)

        elif team == "Pre-Approvals IP Offshore":
            if root_kpi == "Rejection":
                actual_val = safe_float(row.get("IPInitialRejection%"))
                target_val = targets.get("Rejection", 0.03)
            elif root_kpi == "InitialError":
                actual_val = safe_float(row.get("Error%"))
                target_val = targets.get("InitialError", 0.03)
            elif root_kpi == "Submission":
                actual_val = safe_float(row.get("NumberApprovalwithin48hrs")) # mapping submission achievement rate
                target_val = targets.get("Submission", 0.90)

        elif team == "Sales":
            clean_row = {str(k).replace(" ", ""): v for k, v in row.items()}
            if root_kpi == "OPCensus":
                if "A.OPCensus" in clean_row and "T.OPCensus" in clean_row:
                    a_val = safe_float(clean_row.get("A.OPCensus"))
                    t_val = safe_float(clean_row.get("T.OPCensus"))
                    actual_val = a_val / t_val if t_val > 0 else 0.0
                else:
                    actual_val = safe_float(clean_row.get("OPCensusAch%"))
                target_val = targets.get("OPCensus", 1.0)
            elif root_kpi == "OPRevenue":
                if "A.OPRevenue" in clean_row and "T.OPRevenue" in clean_row:
                    a_val = safe_float(clean_row.get("A.OPRevenue"))
                    t_val = safe_float(clean_row.get("T.OPRevenue"))
                    actual_val = a_val / t_val if t_val > 0 else 0.0
                else:
                    actual_val = safe_float(clean_row.get("OPRevenueAch%"))
                target_val = targets.get("OPRevenue", 1.0)
            elif root_kpi == "IPCensus":
                if "A.IPCensus" in clean_row and "T.IPCensus" in clean_row:
                    a_val = safe_float(clean_row.get("A.IPCensus"))
                    t_val = safe_float(clean_row.get("T.IPCensus"))
                    actual_val = a_val / t_val if t_val > 0 else 0.0
                else:
                    actual_val = safe_float(clean_row.get("IPCensusAch%"))
                target_val = targets.get("IPCensus", 1.0)
            elif root_kpi == "IPRevenue":
                if "A.IPRevenue" in clean_row and "T.IPRevenue" in clean_row:
                    a_val = safe_float(clean_row.get("A.IPRevenue"))
                    t_val = safe_float(clean_row.get("T.IPRevenue"))
                    actual_val = a_val / t_val if t_val > 0 else 0.0
                else:
                    actual_val = safe_float(clean_row.get("IPRevenueAch%"))
                target_val = targets.get("IPRevenue", 1.0)
            elif root_kpi == "Activity":
                # For Activity, calculate ratio of sum of actuals to sum of targets
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
                actual_val = sum_actual_activity / sum_target_activity if sum_target_activity > 0 else 0.0
                target_val = 1.0
        elif team == "Re-Submission":
            if root_kpi == "quality_errors_rate":
                actual_val = safe_float(row.get("A.QualityErrorsRate"))
                target_val = targets.get("quality_errors_rate", 0.05)
            elif root_kpi == "rejection_rate_after_resubmission":
                actual_val = safe_float(row.get("A.RejectionRateAfterResubmission"))
                target_val = targets.get("rejection_rate_after_resubmission", 0.60)
            elif root_kpi == "tat":
                actual_val = safe_float(row.get("A.TAT"))
                target_val = targets.get("tat", 1.0)

        if math.isnan(actual_val):
            actual_val = 0.0
        if math.isnan(target_val):
            target_val = 0.0

        return RootCauseInfo(
            kpi=root_kpi,
            impact_pct=impact_pct,
            actual=float(round(actual_val, 4)),
            target=float(round(target_val, 4))
        )

    def generate_suggested_action(
        self, score: float, is_new: bool, root_cause: Optional[RootCauseInfo]
    ) -> str:
        """Generates AI recommended action based on performance and root cause gaps."""
        if is_new:
            return "Probation Monitoring"
        if score < 50:
            return "SIP"
        if score < 60:
            return "PI"
        if score >= 90:
            return "Reward & Recognition"

        if not root_cause:
            return "Performance Monitoring"

        kpi_lower = root_cause.kpi.lower()
        if "attend" in kpi_lower:
            return "Attendance Coaching"
        elif "booking" in kpi_lower:
            return "Booking Skills Training"
        elif "quality" in kpi_lower:
            return "Quality Calibration"
        elif "aht" in kpi_lower:
            return "Call Handling Coaching"
        elif "utz" in kpi_lower:
            return "Workflow Optimization"
        elif "abandon" in kpi_lower:
            return "Queue Management Review"
        elif "rejection" in kpi_lower:
            return "Quality Calibration"
        elif "initialerror" in kpi_lower:
            return "Call Handling Coaching"
        elif "submission" in kpi_lower:
            return "Workflow Optimization"
        elif "census" in kpi_lower or "revenue" in kpi_lower:
            return "Sales Target Coaching"
        elif "activity" in kpi_lower:
            return "Activity Optimization"

        return "Performance Monitoring"

def np_isnan(val):
    import math
    try:
        return math.isnan(float(val))
    except Exception:
        return False
