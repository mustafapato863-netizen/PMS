"""Regression tests for the clinical_scorecards module.

Covers:
- ER Dr: both LAMA paths (zero and positive), deductions, blank LAMA
- Radiologist: NA exclusion combinations, complaint penalty
- Qlty&Case-Mngt: all four formula paths
- can_recompute thresholds
"""

import pytest

from services.clinical_scorecards import (
    can_recompute,
    compute_clinical_score,
    score_er_dr,
    score_qlty_case_mngt,
    score_radiologist,
)


# ---------------------------------------------------------------------------
# ER Dr
# ---------------------------------------------------------------------------

class TestErDr:
    """ER Dr scoring regression tests."""

    def _full_er_raw(self, **overrides):
        """Base ER Dr raw data with all 6 KPI achievements (0-1 scale)."""
        raw = {
            "Admission Rate %.2": 0.90,
            "Re-visit Rate  %.2": 0.85,
            "Avg Time to Initial Patient Assessment 10%": 0.80,
            "Satisfaction Score.3": 0.92,
            "Documentation%.3": 0.88,
            "LAMA Retention %.2": 0.75,
            "Total LAMA": 5,
            "Valid Complains": 0,
            "Medical Error Rate ": 0,
        }
        raw.update(overrides)
        return raw

    def test_lama_positive_includes_lama_retention(self):
        """When Total LAMA > 0, include LAMA Retention with denominator 0.90."""
        raw = self._full_er_raw(**{"Total LAMA": 5})
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        # 6 KPIs, no penalties
        kpi_keys = [k["kpi_key"] for k in kpis if not k.get("is_penalty")]
        assert "lama_retention" in kpi_keys
        assert len(kpi_keys) == 6

        # Verify weighted sum / 0.90
        weighted = (0.90 * 0.40 + 0.85 * 0.10 + 0.80 * 0.15 +
                    0.92 * 0.15 + 0.88 * 0.10 + 0.75 * 0.10)
        expected = (weighted / 0.90) * 100
        assert abs(score - expected) < 0.1

    def test_lama_zero_excludes_lama_retention(self):
        """When Total LAMA == 0, exclude LAMA Retention with denominator 0.80."""
        raw = self._full_er_raw(**{"Total LAMA": 0})
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis if not k.get("is_penalty")]
        assert "lama_retention" not in kpi_keys
        assert len(kpi_keys) == 5

        # Verify weighted sum / 0.80
        weighted = (0.90 * 0.40 + 0.85 * 0.10 + 0.80 * 0.15 +
                    0.92 * 0.15 + 0.88 * 0.10)
        expected = (weighted / 0.80) * 100
        assert abs(score - expected) < 0.1

    def test_lama_blank_excludes_lama_retention(self):
        """When Total LAMA is blank/absent, exclude LAMA Retention with denominator 0.80."""
        raw = self._full_er_raw()
        del raw["Total LAMA"]
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis if not k.get("is_penalty")]
        assert "lama_retention" not in kpi_keys
        assert len(kpi_keys) == 5

    def test_lama_blank_na(self):
        """When Total LAMA is 'NA', treat as blank and exclude."""
        raw = self._full_er_raw(**{"Total LAMA": "NA"})
        result = score_er_dr(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2] if not k.get("is_penalty")]
        assert "lama_retention" not in kpi_keys

    def test_valid_complaints_deduction(self):
        """Valid Complaints > 0 applies penalty deduction."""
        raw = self._full_er_raw(**{"Valid Complains": 0.05, "Total LAMA": 5})
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        penalties = [k for k in kpis if k.get("is_penalty")]
        assert len(penalties) >= 1
        complaint_penalty = next(p for p in penalties if "complaint" in p["kpi_key"])
        assert complaint_penalty["contribution"] < 0

    def test_medical_error_deduction(self):
        """Medical Error Rate > 0 applies penalty deduction."""
        raw = self._full_er_raw(**{"Medical Error Rate ": 0.03, "Total LAMA": 5})
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        penalties = [k for k in kpis if k.get("is_penalty")]
        error_penalty = next(p for p in penalties if "medical_error" in p["kpi_key"])
        assert error_penalty["contribution"] < 0

    def test_both_deductions(self):
        """Both deductions are applied."""
        raw = self._full_er_raw(**{
            "Valid Complains": 0.05, "Medical Error Rate ": 0.03, "Total LAMA": 5,
        })
        result = score_er_dr(raw)
        assert result is not None
        score, grade, kpis = result
        penalties = [k for k in kpis if k.get("is_penalty")]
        assert len(penalties) == 2

        # Score should be lower than without deductions
        raw_no_ded = self._full_er_raw(**{"Total LAMA": 5})
        result_no_ded = score_er_dr(raw_no_ded)
        assert result_no_ded is not None
        assert score < result_no_ded[0]

    def test_zero_complaints_no_penalty(self):
        """Zero complaints means no penalty."""
        raw = self._full_er_raw(**{"Valid Complains": 0, "Total LAMA": 5})
        result = score_er_dr(raw)
        assert result is not None
        penalties = [k for k in result[2] if k.get("is_penalty")]
        complaint_penalties = [p for p in penalties if "complaint" in p["kpi_key"]]
        assert len(complaint_penalties) == 0

    def test_grade_boundaries(self):
        """Verify grade assignment at boundaries."""
        # High score → grade A
        raw_high = self._full_er_raw(**{
            "Admission Rate %.2": 1.0, "Re-visit Rate  %.2": 1.0,
            "Avg Time to Initial Patient Assessment 10%": 1.0,
            "Satisfaction Score.3": 1.0, "Documentation%.3": 1.0,
            "LAMA Retention %.2": 1.0, "Total LAMA": 5,
        })
        result = score_er_dr(raw_high)
        assert result is not None
        # 1.0 * sum_of_weights / 0.90 → 100/90 → capped at 100
        assert result[0] == 100.0
        assert result[1] == "A"


# ---------------------------------------------------------------------------
# Radiologist
# ---------------------------------------------------------------------------

class TestRadiologist:
    """Radiologist scoring regression tests."""

    def _full_rad_raw(self, **overrides):
        """Base Radiologist raw data with all 6 KPI achievements."""
        raw = {
            "Ach.TAT %": 0.90,
            "Ach.Productivity %": 0.85,
            "Ach.Report Quality %": 0.80,
            "Ach.Imaging Protocol %": 0.95,
            "Ach.Critical Findings %": 0.88,
            "Ach.Patient Waiting Time %": 0.78,
            "Complaints": 0,
        }
        raw.update(overrides)
        return raw

    def test_all_kpis_included(self):
        """All 6 KPIs contribute when none are NA."""
        raw = self._full_rad_raw()
        result = score_radiologist(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis if not k.get("is_penalty")]
        assert len(kpi_keys) == 6
        assert "critical_findings" in kpi_keys
        assert "patient_waiting_time" in kpi_keys

    def test_critical_findings_na(self):
        """Exclude Critical Findings when NA."""
        raw = self._full_rad_raw(**{"Ach.Critical Findings %": "NA"})
        result = score_radiologist(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2] if not k.get("is_penalty")]
        assert "critical_findings" not in kpi_keys
        assert len(kpi_keys) == 5

    def test_patient_waiting_time_na(self):
        """Exclude Patient Waiting Time when NA."""
        raw = self._full_rad_raw(**{"Ach.Patient Waiting Time %": "N/A"})
        result = score_radiologist(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2] if not k.get("is_penalty")]
        assert "patient_waiting_time" not in kpi_keys
        assert len(kpi_keys) == 5

    def test_both_na_excluded(self):
        """Both Critical Findings and Patient Waiting Time NA."""
        raw = self._full_rad_raw(**{
            "Ach.Critical Findings %": "NA",
            "Ach.Patient Waiting Time %": "NA",
        })
        result = score_radiologist(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2] if not k.get("is_penalty")]
        assert "critical_findings" not in kpi_keys
        assert "patient_waiting_time" not in kpi_keys
        assert len(kpi_keys) == 4

        # Denominator should be sum of remaining weights: 0.20 + 0.35 + 0.10 + 0.10 = 0.75
        weighted = (0.90 * 0.20 + 0.85 * 0.35 + 0.80 * 0.10 + 0.95 * 0.10)
        expected = (weighted / 0.75) * 100
        assert abs(result[0] - expected) < 0.1

    def test_complaint_penalty_applied(self):
        """Flat -10pp penalty when complaints > 0."""
        raw = self._full_rad_raw(**{"Complaints": 2})
        result = score_radiologist(raw)
        assert result is not None
        score, grade, kpis = result
        penalties = [k for k in kpis if k.get("is_penalty")]
        assert len(penalties) == 1
        assert penalties[0]["contribution"] == -0.10

        # Score should be 10pp lower
        raw_no_complaint = self._full_rad_raw()
        result_no_complaint = score_radiologist(raw_no_complaint)
        assert result_no_complaint is not None
        assert abs(result_no_complaint[0] - score - 10.0) < 0.1

    def test_zero_complaints_no_penalty(self):
        """Zero complaints means no penalty."""
        raw = self._full_rad_raw(**{"Complaints": 0})
        result = score_radiologist(raw)
        assert result is not None
        penalties = [k for k in result[2] if k.get("is_penalty")]
        assert len(penalties) == 0

    def test_na_plus_complaint(self):
        """NA exclusion plus complaint penalty combined."""
        raw = self._full_rad_raw(**{
            "Ach.Critical Findings %": "NA",
            "Complaints": 1,
        })
        result = score_radiologist(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2] if not k.get("is_penalty")]
        assert "critical_findings" not in kpi_keys
        penalties = [k for k in result[2] if k.get("is_penalty")]
        assert len(penalties) == 1


# ---------------------------------------------------------------------------
# Qlty&Case-Mngt
# ---------------------------------------------------------------------------

class TestQltyCaseMngt:
    """Qlty&Case-Mngt scoring regression tests."""

    def test_path1_case_management_row(self):
        """Path 1: blank AF, numeric AG, unavailable AE → Audit 30% + Revenue 70%."""
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.80,
            "Revenue Impact": 0.90,
            # Case Management Rate and Rejection Rate are absent
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis]
        assert set(kpi_keys) == {"audit", "revenue_impact"}

        expected = (0.80 * 0.30 + 0.90 * 0.70) * 100
        assert abs(score - expected) < 0.1

    def test_path2_quality_af_zero(self):
        """Path 2: AF = 0 → Audit 40% + Rejection 60%."""
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.85,
            "Rejection Rate": 0.75,
            "Case Management Rate": 0.0,
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis]
        assert set(kpi_keys) == {"audit", "rejection"}

        expected = (0.85 * 0.40 + 0.75 * 0.60) * 100
        assert abs(score - expected) < 0.1

    def test_path3_af_nonzero_ad_zero(self):
        """Path 3: AF nonzero, AD = 0 → Rejection 60% + Case Management 40%."""
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.0,
            "Rejection Rate": 0.80,
            "Case Management Rate": 0.65,
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis]
        assert set(kpi_keys) == {"rejection", "case_management"}

        expected = (0.80 * 0.60 + 0.65 * 0.40) * 100
        assert abs(score - expected) < 0.1

    def test_path3_af_nonzero_ad_blank(self):
        """Path 3 also applies when AD is blank/absent."""
        raw = {
            "Rejection Rate": 0.80,
            "Case Management Rate": 0.65,
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        kpi_keys = [k["kpi_key"] for k in result[2]]
        assert set(kpi_keys) == {"rejection", "case_management"}

    def test_path4_full_formula(self):
        """Path 4: Audit 30% + Rejection 50% + Case Management 20%."""
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.85,
            "Rejection Rate": 0.75,
            "Case Management Rate": 0.90,
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        score, grade, kpis = result
        kpi_keys = [k["kpi_key"] for k in kpis]
        assert set(kpi_keys) == {"audit", "rejection", "case_management"}

        expected = (0.85 * 0.30 + 0.75 * 0.50 + 0.90 * 0.20) * 100
        assert abs(score - expected) < 0.1

    def test_missing_kpi_contributes_zero(self):
        """Missing text in a KPI used by the selected formula contributes zero."""
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.85,
            "Case Management Rate": 0.90,
            # Rejection Rate missing but formula uses it
        }
        result = score_qlty_case_mngt(raw)
        assert result is not None
        score, grade, kpis = result
        # Path 4 applies (Audit present, CM nonzero)
        expected = (0.85 * 0.30 + 0.0 * 0.50 + 0.90 * 0.20) * 100
        assert abs(score - expected) < 0.1

    def test_insufficient_data_returns_none(self):
        """No relevant columns → returns None."""
        raw = {"SomethingElse": 42}
        result = score_qlty_case_mngt(raw)
        assert result is None


# ---------------------------------------------------------------------------
# can_recompute thresholds
# ---------------------------------------------------------------------------

class TestCanRecompute:
    """Test minimum data requirements for recomputation."""

    def test_er_dr_needs_3_columns(self):
        raw = {"Admission Rate %.2": 0.9, "Re-visit Rate  %.2": 0.85}
        assert can_recompute("ER Dr", raw) is False
        raw["Satisfaction Score.3"] = 0.90
        assert can_recompute("ER Dr", raw) is True

    def test_radiologist_needs_3_columns(self):
        raw = {"Ach.TAT %": 0.9, "Ach.Productivity %": 0.85}
        assert can_recompute("Radiologist", raw) is False
        raw["Ach.Report Quality %"] = 0.80
        assert can_recompute("Radiologist", raw) is True

    def test_qlty_needs_2_columns(self):
        raw = {"Audit Compliance Rate % (IP, OP, Re-Submission)": 0.9}
        assert can_recompute("Qlty&Case-Mngt", raw) is False
        raw["Rejection Rate"] = 0.80
        assert can_recompute("Qlty&Case-Mngt", raw) is True

    def test_unsupported_team(self):
        assert can_recompute("Inbound", {"some": "data"}) is False

    def test_non_dict_raw(self):
        assert can_recompute("ER Dr", None) is False
        assert can_recompute("ER Dr", "string") is False


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

class TestComputeClinicalScore:
    """Test compute_clinical_score dispatching."""

    def test_er_dr_dispatch(self):
        raw = {
            "Admission Rate %.2": 0.90, "Re-visit Rate  %.2": 0.85,
            "Avg Time to Initial Patient Assessment 10%": 0.80,
            "Satisfaction Score.3": 0.92, "Documentation%.3": 0.88,
            "Total LAMA": 0,
        }
        result = compute_clinical_score("ER Dr", raw)
        assert result is not None

    def test_radiologist_dispatch(self):
        raw = {
            "Ach.TAT %": 0.90, "Ach.Productivity %": 0.85,
            "Ach.Report Quality %": 0.80, "Ach.Imaging Protocol %": 0.95,
            "Ach.Critical Findings %": 0.88, "Ach.Patient Waiting Time %": 0.78,
        }
        result = compute_clinical_score("Radiologist", raw)
        assert result is not None

    def test_qlty_dispatch(self):
        raw = {
            "Audit Compliance Rate % (IP, OP, Re-Submission)": 0.85,
            "Rejection Rate": 0.75,
        }
        result = compute_clinical_score("Qlty&Case-Mngt", raw)
        assert result is not None

    def test_unknown_team_returns_none(self):
        assert compute_clinical_score("Inbound", {}) is None
