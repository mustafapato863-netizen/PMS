from typing import List, Dict, Any, Optional
from models.schemas import PerformanceRecord
from utils.helpers import convert_aht_to_minutes

MONTH_ORDER = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
}

class TrendService:
    @staticmethod
    def get_trend_label(change: float, is_lower_better: bool = False) -> str:
        """Assign trend status based on change threshold."""
        # For AHT (lower is better), we invert the change
        val = -change if is_lower_better else change
        
        if val > 0.02:
            return "Improving"
        elif val < -0.10:
            return "Critical Decline"
        elif val < -0.02:
            return "Declining"
        else:
            return "Stable"

    def calculate_trends(self, history: List[PerformanceRecord], curr_idx: int) -> Dict[str, Dict[str, str]]:
        """
        Calculate MoM, QoQ, and YTD trends for a given performance record.
        Returns:
          - trend_status (dict): { kpi: { "mom": label, "qoq": label, "ytd": label } }
        """
        curr = history[curr_idx]
        
        def safe_float(val, default=0.0) -> float:
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        # Helper to extract KPI values
        def get_kpi_value(record: PerformanceRecord, kpi: str) -> float:
            if kpi == "score":
                return record.evaluation.score
            elif kpi == "attendance":
                return record.actual.attend_rate
            elif kpi == "booking":
                return record.actual.booking_rate
            elif kpi == "quality":
                # Find quality achievement rate
                return record.achievement.quality_ach if record.achievement.quality_ach > 0 else safe_float(record.raw_data.get("A.QualityScore"))
            elif kpi == "aht":
                # Use AHT in minutes
                return convert_aht_to_minutes(record.calls.aht_raw)
            return 0.0

        kpis = ["score", "attendance", "booking", "quality", "aht"]
        trend_status = {}

        for kpi in kpis:
            curr_val = get_kpi_value(curr, kpi)
            is_aht = (kpi == "aht")

            # 1. Month-over-Month (MoM)
            mom_label = "Stable"
            if curr_idx >= 1:
                prev = history[curr_idx - 1]
                prev_val = get_kpi_value(prev, kpi)
                if is_aht:
                    change = (curr_val - prev_val) / prev_val if prev_val > 0 else 0.0
                else:
                    # Score and Rates: absolute difference
                    # For rates, convert to 0-100 scale to check change (since score is 0-100 and rates are 0-1)
                    mult = 100.0 if kpi != "score" else 1.0
                    change = (curr_val - prev_val) * mult
                    change = change / 100.0  # normalize back
                mom_label = self.get_trend_label(change, is_lower_better=is_aht)

            # 2. Quarter-over-Quarter (QoQ)
            qoq_label = "Stable"
            if curr_idx >= 3:
                prev_q = history[curr_idx - 3]
                prev_q_val = get_kpi_value(prev_q, kpi)
                if is_aht:
                    change = (curr_val - prev_q_val) / prev_q_val if prev_q_val > 0 else 0.0
                else:
                    mult = 100.0 if kpi != "score" else 1.0
                    change = (curr_val - prev_q_val) * mult
                    change = change / 100.0
                qoq_label = self.get_trend_label(change, is_lower_better=is_aht)

            # 3. Year to Date (YTD)
            ytd_label = "Stable"
            if curr_idx >= 1:
                preceding_vals = [get_kpi_value(h, kpi) for h in history[:curr_idx]]
                avg_ytd = sum(preceding_vals) / len(preceding_vals)
                if is_aht:
                    change = (curr_val - avg_ytd) / avg_ytd if avg_ytd > 0 else 0.0
                else:
                    mult = 100.0 if kpi != "score" else 1.0
                    change = (curr_val - avg_ytd) * mult
                    change = change / 100.0
                ytd_label = self.get_trend_label(change, is_lower_better=is_aht)

            trend_status[kpi] = {
                "mom": mom_label,
                "qoq": qoq_label,
                "ytd": ytd_label
            }

        return trend_status
