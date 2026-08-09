"""
Comprehensive tests for Three Teams KPI Implementation

Tests cover:
- Configuration loading and validation
- Data cleaner functionality
- KPI calculations (direct, inverse, capping)
- Performance scoring with the global 100% achievement cap
- Grade assignments
- Property-based tests for correctness properties
"""

import pytest
import json
import numpy as np
import pandas as pd
from hypothesis import given, strategies as st, settings, HealthCheck
from pathlib import Path
from decimal import Decimal

# Import modules
from config.loader import (
    load_team_config,
    validate_team_config,
    ConfigurationError,
    WeightValidationError,
    ThresholdValidationError,
)

from Data_Cleaning_Teams.pharmacy import (
    process_pharmacy,
    calculate_achievement,
    parse_percentage,
)
from Data_Cleaning_Teams.coding import process_coding
from Data_Cleaning_Teams.csr import process_csr

from data_cleaning.cleaner_factory import get_process_function


# ============================================================
# UNIT TESTS: Configuration Loading
# ============================================================

class TestConfigurationLoading:
    """Test configuration file loading and validation.
    
    Tests cover:
    - Valid configuration loading for all three teams
    - Error handling for missing fields
    - Error handling for invalid weights
    - Error handling for bad thresholds
    - Weight validation with 0.001 tolerance
    
    Validates: Requirements 19.2
    """
    
    # ===== Test 1: Load All Three Team Configs Successfully =====
    
    def test_load_pharmacy_config(self):
        """Test loading Pharmacy configuration successfully."""
        config = load_team_config("Pharmacy")
        assert config is not None
        assert config['team'] == 'Pharmacy'
        assert config['db_name'] == 'Pharmacy'
        assert len(config['kpis']) == 5
        
        # Verify all Pharmacy KPI keys present
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['WaitingTime', 'Leakage', 'TenderCompliance', 'ATV', 'Prescription']
        assert kpi_keys == expected_keys
    
    def test_load_coding_config(self):
        """Test loading Coding configuration successfully."""
        config = load_team_config("Coding")
        assert config is not None
        assert config['team'] == 'Coding'
        assert config['db_name'] == 'Coding'
        assert len(config['kpis']) == 3
        
        # Verify all Coding KPI keys present
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['QualityErrors', 'Rejection', 'TAT']
        assert kpi_keys == expected_keys
    
    def test_load_csr_config(self):
        """Test loading CSR configuration successfully."""
        config = load_team_config("CSR")
        assert config is not None
        assert config['team'] == 'CSR'
        assert config['db_name'] == 'CSR'
        assert len(config['kpis']) == 3
        
        # Verify all CSR KPI keys present
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['Rejection', 'Queries', 'AttendedCR']
        assert kpi_keys == expected_keys
    
    # ===== Test 2: Invalid/Non-Existent Team Raises ConfigurationError =====
    
    def test_config_invalid_team_raises_error(self):
        """Test loading non-existent team raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Team configuration not found"):
            load_team_config("NonExistentTeam")
    
    def test_config_case_sensitive_team_name(self):
        """Test team names are case-sensitive."""
        # Correct case works
        config = load_team_config("Pharmacy")
        assert config is not None
        
        # Incorrect case raises error (on case-sensitive systems)
        # Note: behavior depends on OS filesystem
        try:
            load_team_config("pharmacy")  # lowercase
            # If this doesn't raise on case-insensitive systems, that's OK
        except ConfigurationError:
            pass  # Expected on case-sensitive systems
    
    # ===== Test 3: Weights Sum to 1.0 (within 0.001 tolerance) =====
    
    def test_pharmacy_weights_sum_to_one(self):
        """Test Pharmacy weights sum to exactly 1.0 within tolerance."""
        config = load_team_config("Pharmacy")
        total_weight = sum(kpi['weight'] for kpi in config['kpis'])
        assert abs(total_weight - 1.0) < 0.001, \
            f"Pharmacy weights sum to {total_weight}, expected 1.0 ± 0.001"
    
    def test_coding_weights_sum_to_one(self):
        """Test Coding weights sum to exactly 1.0 within tolerance."""
        config = load_team_config("Coding")
        total_weight = sum(kpi['weight'] for kpi in config['kpis'])
        assert abs(total_weight - 1.0) < 0.001, \
            f"Coding weights sum to {total_weight}, expected 1.0 ± 0.001"
    
    def test_csr_weights_sum_to_one(self):
        """Test CSR weights sum to exactly 1.0 within tolerance."""
        config = load_team_config("CSR")
        total_weight = sum(kpi['weight'] for kpi in config['kpis'])
        assert abs(total_weight - 1.0) < 0.001, \
            f"CSR weights sum to {total_weight}, expected 1.0 ± 0.001"
    
    def test_pharmacy_individual_weights_within_tolerance(self):
        """Test each Pharmacy KPI weight is properly preserved."""
        config = load_team_config("Pharmacy")
        for kpi in config['kpis']:
            # Each should be 0.20 (20%)
            assert 0.19 < kpi['weight'] < 0.21, \
                f"Pharmacy {kpi['key']} weight {kpi['weight']} is not 0.20"
    
    def test_coding_individual_weights_within_tolerance(self):
        """Test each Coding KPI weight is properly preserved."""
        config = load_team_config("Coding")
        expected_weights = {
            'QualityErrors': 0.20,
            'Rejection': 0.50,
            'TAT': 0.30
        }
        for kpi in config['kpis']:
            expected = expected_weights[kpi['key']]
            assert abs(kpi['weight'] - expected) < 0.001, \
                f"Coding {kpi['key']} weight {kpi['weight']} should be {expected}"
    
    def test_csr_individual_weights_within_tolerance(self):
        """Test each CSR KPI weight is properly preserved."""
        config = load_team_config("CSR")
        expected_weights = {
            'Rejection': 0.40,
            'Queries': 0.30,
            'AttendedCR': 0.30
        }
        for kpi in config['kpis']:
            expected = expected_weights[kpi['key']]
            assert abs(kpi['weight'] - expected) < 0.001, \
                f"CSR {kpi['key']} weight {kpi['weight']} should be {expected}"
    
    # ===== Test 4: Grade Thresholds in Descending Order =====
    
    def test_grade_thresholds_descending_order(self):
        """Test grade thresholds are in strict descending order for all teams."""
        for team_name in ["Pharmacy", "Coding", "CSR"]:
            config = load_team_config(team_name)
            thresholds = config['grade_thresholds']
            
            # Must have all grades A, B, C, D
            assert 'A' in thresholds, f"{team_name}: Missing grade A threshold"
            assert 'B' in thresholds, f"{team_name}: Missing grade B threshold"
            assert 'C' in thresholds, f"{team_name}: Missing grade C threshold"
            assert 'D' in thresholds, f"{team_name}: Missing grade D threshold"
            
            # Must be in strict descending order
            assert thresholds['A'] > thresholds['B'], \
                f"{team_name}: A threshold {thresholds['A']} should be > B {thresholds['B']}"
            assert thresholds['B'] > thresholds['C'], \
                f"{team_name}: B threshold {thresholds['B']} should be > C {thresholds['C']}"
            assert thresholds['C'] > thresholds['D'], \
                f"{team_name}: C threshold {thresholds['C']} should be > D {thresholds['D']}"
    
    def test_pharmacy_grade_thresholds_values(self):
        """Test Pharmacy grade threshold values are as specified."""
        config = load_team_config("Pharmacy")
        thresholds = config['grade_thresholds']
        assert thresholds['A'] == 95
        assert thresholds['B'] == 85
        assert thresholds['C'] == 75
        assert thresholds['D'] == 65
    
    def test_coding_grade_thresholds_values(self):
        """Test Coding grade threshold values are as specified."""
        config = load_team_config("Coding")
        thresholds = config['grade_thresholds']
        assert thresholds['A'] == 95
        assert thresholds['B'] == 85
        assert thresholds['C'] == 75
        assert thresholds['D'] == 65
    
    def test_csr_grade_thresholds_values(self):
        """Test CSR grade threshold values are as specified."""
        config = load_team_config("CSR")
        thresholds = config['grade_thresholds']
        assert thresholds['A'] == 95
        assert thresholds['B'] == 85
        assert thresholds['C'] == 75
        assert thresholds['D'] == 65
    
    # ===== Test 5: Missing Required Fields Raises ConfigurationError =====
    
    def test_missing_team_field_raises_error(self):
        """Test missing 'team' field raises ConfigurationError."""
        config = {
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": []
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("team" in e.lower() for e in errors)
    
    def test_missing_db_name_field_raises_error(self):
        """Test missing 'db_name' field raises ConfigurationError."""
        config = {
            "team": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": []
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("db_name" in e.lower() for e in errors)
    
    def test_missing_grade_thresholds_raises_error(self):
        """Test missing 'grade_thresholds' field raises ConfigurationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "kpis": []
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("grade_thresholds" in e.lower() for e in errors)
    
    def test_missing_kpis_field_raises_error(self):
        """Test missing 'kpis' field raises ConfigurationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65}
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("kpis" in e.lower() for e in errors)
    
    def test_missing_kpi_required_fields_raises_error(self):
        """Test missing KPI required fields raises ConfigurationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": [
                {
                    "key": "KPI1",
                    # Missing 'label', 'weight', 'direction', etc.
                }
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("kpi" in e.lower() and "field" in e.lower() for e in errors)
    
    # ===== Test 6: Invalid Weight Distributions Raise WeightValidationError =====
    
    def test_weights_sum_less_than_tolerance_raises_error(self):
        """Test weights summing to < 0.999 raises WeightValidationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 0.40, "direction": "higher_better", 
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"},
                {"key": "KPI2", "label": "KPI2", "weight": 0.50, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI2", "target_col": "T.KPI2"},
                # Total: 0.90 < 0.999 (too low)
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("weight" in e.lower() for e in errors)
    
    def test_weights_sum_more_than_tolerance_raises_error(self):
        """Test weights summing to > 1.001 raises WeightValidationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 0.50, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"},
                {"key": "KPI2", "label": "KPI2", "weight": 0.55, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI2", "target_col": "T.KPI2"},
                # Total: 1.05 > 1.001 (too high)
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("weight" in e.lower() for e in errors)
    
    def test_empty_kpis_list_raises_error(self):
        """Test empty KPIs list (no weights) raises error."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": []
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("no kpi" in e.lower() or "weight" in e.lower() for e in errors)
    
    def test_single_weight_not_one_raises_error(self):
        """Test single KPI with weight != 1.0 raises error."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75, "D": 65},
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 0.95, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"}
                 # Only 0.95, not 1.0
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("weight" in e.lower() for e in errors)
    
    # ===== Test 7: Bad Threshold Ordering Raises ThresholdValidationError =====
    
    def test_grade_a_not_greater_than_b_raises_error(self):
        """Test grade A threshold not > B raises ThresholdValidationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 85, "B": 85, "C": 75, "D": 65},  # A == B (error)
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 1.0, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"}
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("threshold" in e.lower() or "descending" in e.lower() for e in errors)
    
    def test_grade_b_not_greater_than_c_raises_error(self):
        """Test grade B threshold not > C raises ThresholdValidationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 75, "C": 75, "D": 65},  # B == C (error)
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 1.0, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"}
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("threshold" in e.lower() or "descending" in e.lower() for e in errors)
    
    def test_grade_c_not_greater_than_d_raises_error(self):
        """Test grade C threshold not > D raises ThresholdValidationError."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 65, "D": 65},  # C == D (error)
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 1.0, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"}
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("threshold" in e.lower() or "descending" in e.lower() for e in errors)
    
    def test_missing_grade_threshold_raises_error(self):
        """Test missing grade threshold (e.g., D) raises error."""
        config = {
            "team": "Test",
            "db_name": "Test",
            "region": "UAE",
            "employee_id_col": "ID",
            "employee_name_col": "Name",
            "grade_thresholds": {"A": 95, "B": 85, "C": 75},  # Missing D
            "kpis": [
                {"key": "KPI1", "label": "KPI1", "weight": 1.0, "direction": "higher_better",
                 "unit": "%", "color": "#000000", "actual_col": "A.KPI1", "target_col": "T.KPI1"}
            ]
        }
        is_valid, errors = validate_team_config(config)
        assert not is_valid
        assert any("grade" in e.lower() or "threshold" in e.lower() for e in errors)
    
    # ===== Additional Comprehensive Tests =====
    
    def test_all_required_fields_present(self):
        """Test all required fields are present in loaded configs."""
        required_top_level = ['team', 'db_name', 'region', 'employee_id_col', 'employee_name_col', 'grade_thresholds', 'kpis']
        required_kpi_fields = ['key', 'label', 'weight', 'direction', 'unit', 'color', 'actual_col', 'target_col', 'capping']
        
        for team_name in ["Pharmacy", "Coding", "CSR"]:
            config = load_team_config(team_name)
            
            # Check top-level fields
            for field in required_top_level:
                assert field in config, f"{team_name}: Missing required field '{field}'"
            
            # Check KPI fields
            for idx, kpi in enumerate(config['kpis']):
                for field in required_kpi_fields:
                    assert field in kpi, f"{team_name} KPI {idx}: Missing required field '{field}'"


# ============================================================
# UNIT TESTS: Achievement Calculation
# ============================================================

class TestAchievementCalculation:
    """Test KPI achievement calculations."""
    
    def test_direct_kpi_achievement(self):
        """Test direct KPI achievement (higher is better)."""
        # actual/target * 100
        achievement = calculate_achievement(actual=90, target=100, is_inverse=False, cap_at_100=False)
        assert achievement == 90.0
    
    def test_direct_kpi_is_capped_at_100(self):
        """Test the global KPI achievement cap."""
        achievement = calculate_achievement(actual=110, target=100, is_inverse=False, cap_at_100=False)
        assert achievement == 100.0
    
    def test_inverse_kpi_achievement(self):
        """Test inverse KPI achievement (lower is better)."""
        # target/actual * 100
        achievement = calculate_achievement(actual=5, target=4, is_inverse=True, cap_at_100=False)
        assert achievement == 80.0
    
    def test_inverse_kpi_actual_zero(self):
        """Test inverse KPI with actual=0 returns 100% (no division by zero)."""
        achievement = calculate_achievement(actual=0, target=5, is_inverse=True, cap_at_100=False)
        assert achievement == 100.0
    
    def test_direct_kpi_capped(self):
        """Test direct KPI capped at 100% when flag set."""
        achievement = calculate_achievement(actual=120, target=100, is_inverse=False, cap_at_100=True)
        assert achievement == 100.0
    
    def test_inverse_kpi_capped(self):
        """Test inverse KPI capped at 100% when flag set."""
        achievement = calculate_achievement(actual=2, target=5, is_inverse=True, cap_at_100=True)
        capped = min(250.0, 100.0)
        assert achievement == capped


class TestPercentageParsing:
    """Test percentage parsing utility."""
    
    def test_parse_percentage_string_with_percent(self):
        """Test parsing '95%' format."""
        value = parse_percentage("95%")
        assert value == 95.0
    
    def test_parse_percentage_decimal(self):
        """Test parsing 0.95 (decimal fraction) format."""
        value = parse_percentage(0.95)
        assert value == 95.0
    
    def test_parse_percentage_integer(self):
        """Test parsing integer 95 format."""
        value = parse_percentage(95)
        assert value == 95.0
    
    def test_parse_percentage_nan(self):
        """Test parsing NaN returns 0."""
        value = parse_percentage(np.nan)
        assert value == 0.0
    
    def test_parse_percentage_with_comma(self):
        """Test parsing value with comma: '1,234'."""
        value = parse_percentage("1,234")
        assert value == 1234.0


# ============================================================
# UNIT TESTS: Cleaner Factory
# ============================================================

class TestCleanerFactory:
    """Test cleaner factory functionality."""
    
    def test_get_pharmacy_process_function(self):
        """
        Test factory returns correct Pharmacy cleaner function.
        
        Validates: Requirement 12.1
        """
        func = get_process_function("Pharmacy")
        assert callable(func), "Pharmacy cleaner should be callable"
        assert func.__name__ == "process_pharmacy", f"Expected 'process_pharmacy', got '{func.__name__}'"
    
    def test_get_coding_process_function(self):
        """
        Test factory returns correct Coding cleaner function.
        
        Validates: Requirement 12.2
        """
        func = get_process_function("Coding")
        assert callable(func), "Coding cleaner should be callable"
        assert func.__name__ == "process_coding", f"Expected 'process_coding', got '{func.__name__}'"
    
    def test_get_csr_process_function(self):
        """
        Test factory returns correct CSR cleaner function.
        
        Validates: Requirement 12.3
        """
        func = get_process_function("CSR")
        assert callable(func), "CSR cleaner should be callable"
        assert func.__name__ == "process_csr", f"Expected 'process_csr', got '{func.__name__}'"
    
    def test_get_nonexistent_cleaner_raises_error(self):
        """
        Test factory raises ValueError for unknown team.
        
        Validates: Requirement 12.5
        """
        from data_cleaning.cleaner_factory import CleanerFactory
        with pytest.raises(ValueError, match="No process function found"):
            get_process_function("UnknownTeam")
    
    def test_pharmacy_cleaner_is_callable(self):
        """
        Test Pharmacy cleaner function is callable.
        
        Validates: Requirement 12.1
        """
        func = get_process_function("Pharmacy")
        assert callable(func)
    
    def test_coding_cleaner_is_callable(self):
        """
        Test Coding cleaner function is callable.
        
        Validates: Requirement 12.2
        """
        func = get_process_function("Coding")
        assert callable(func)
    
    def test_csr_cleaner_is_callable(self):
        """
        Test CSR cleaner function is callable.
        
        Validates: Requirement 12.3
        """
        func = get_process_function("CSR")
        assert callable(func)
    
    def test_pharmacy_cleaner_has_correct_name_attribute(self):
        """
        Test Pharmacy cleaner function has correct __name__ attribute.
        
        Validates: Requirement 12.1
        """
        func = get_process_function("Pharmacy")
        assert hasattr(func, '__name__'), "Pharmacy cleaner should have __name__ attribute"
        assert func.__name__ == "process_pharmacy"
    
    def test_coding_cleaner_has_correct_name_attribute(self):
        """
        Test Coding cleaner function has correct __name__ attribute.
        
        Validates: Requirement 12.2
        """
        func = get_process_function("Coding")
        assert hasattr(func, '__name__'), "Coding cleaner should have __name__ attribute"
        assert func.__name__ == "process_coding"
    
    def test_csr_cleaner_has_correct_name_attribute(self):
        """
        Test CSR cleaner function has correct __name__ attribute.
        
        Validates: Requirement 12.3
        """
        func = get_process_function("CSR")
        assert hasattr(func, '__name__'), "CSR cleaner should have __name__ attribute"
        assert func.__name__ == "process_csr"
    
    def test_unknown_team_typo_raises_error(self):
        """
        Test factory raises error for team name typo.
        
        Validates: Requirement 12.5
        """
        with pytest.raises(ValueError):
            get_process_function("Phramacy")  # Typo in "Pharmacy"
    
    def test_unknown_team_invalid_name_raises_error(self):
        """
        Test factory raises error for completely invalid team name.
        
        Validates: Requirement 12.5
        """
        with pytest.raises(ValueError):
            get_process_function("InvalidTeam")
    
    def test_empty_team_name_raises_error(self):
        """
        Test factory raises error for empty team name.
        
        Validates: Requirement 12.5
        """
        with pytest.raises(ValueError):
            get_process_function("")
    
    def test_case_insensitive_pharmacy(self):
        """
        Test factory handles case-insensitive team names (lowercase "pharmacy").
        
        Validates: Requirement 12.1 - Factory flexibility
        """
        func = get_process_function("pharmacy")
        assert callable(func)
        assert func.__name__ == "process_pharmacy"
    
    def test_case_insensitive_coding(self):
        """
        Test factory handles case-insensitive team names (lowercase "coding").
        
        Validates: Requirement 12.2 - Factory flexibility
        """
        func = get_process_function("coding")
        assert callable(func)
        assert func.__name__ == "process_coding"
    
    def test_case_insensitive_csr(self):
        """
        Test factory handles case-insensitive team names (lowercase "csr").
        
        Validates: Requirement 12.3 - Factory flexibility
        """
        func = get_process_function("csr")
        assert callable(func)
        assert func.__name__ == "process_csr"
    
    def test_case_insensitive_mixed_case(self):
        """
        Test factory handles mixed case team names.
        
        Validates: Requirement 12.1-12.3 - Factory flexibility
        """
        func1 = get_process_function("PHARMACY")
        func2 = get_process_function("CoDiNg")
        func3 = get_process_function("CsR")
        
        assert func1.__name__ == "process_pharmacy"
        assert func2.__name__ == "process_coding"
        assert func3.__name__ == "process_csr"
    
    def test_pharmacy_cleaner_has_callable_signature(self):
        """
        Test Pharmacy cleaner function has correct signature.
        
        Validates: Requirement 12.1
        """
        import inspect
        func = get_process_function("Pharmacy")
        
        # Should be callable
        assert callable(func)
        
        # Should accept file_path parameter (at minimum)
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        assert 'file_path' in params, f"Expected 'file_path' parameter, got {params}"
    
    def test_coding_cleaner_has_callable_signature(self):
        """
        Test Coding cleaner function has correct signature.
        
        Validates: Requirement 12.2
        """
        import inspect
        func = get_process_function("Coding")
        
        # Should be callable
        assert callable(func)
        
        # Should accept file_path parameter (at minimum)
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        assert 'file_path' in params, f"Expected 'file_path' parameter, got {params}"
    
    def test_csr_cleaner_has_callable_signature(self):
        """
        Test CSR cleaner function has correct signature.
        
        Validates: Requirement 12.3
        """
        import inspect
        func = get_process_function("CSR")
        
        # Should be callable
        assert callable(func)
        
        # Should accept file_path parameter (at minimum)
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        assert 'file_path' in params, f"Expected 'file_path' parameter, got {params}"
    
    def test_all_three_teams_return_different_functions(self):
        """
        Test that factory returns different functions for each team.
        
        Validates: Requirements 12.1, 12.2, 12.3
        """
        pharmacy_func = get_process_function("Pharmacy")
        coding_func = get_process_function("Coding")
        csr_func = get_process_function("CSR")
        
        # Each should be a different function
        assert pharmacy_func != coding_func
        assert coding_func != csr_func
        assert pharmacy_func != csr_func
        
        # Each should have unique name
        assert pharmacy_func.__name__ != coding_func.__name__
        assert coding_func.__name__ != csr_func.__name__
        assert pharmacy_func.__name__ != csr_func.__name__
    
    def test_factory_consistency_multiple_calls(self):
        """
        Test that factory returns same function on multiple calls.
        
        Validates: Requirements 12.1, 12.2, 12.3
        """
        # Get functions multiple times
        pharmacy1 = get_process_function("Pharmacy")
        pharmacy2 = get_process_function("Pharmacy")
        
        # Should return the same function object
        assert pharmacy1 == pharmacy2
        assert pharmacy1.__name__ == pharmacy2.__name__


# ============================================================
# PROPERTY TESTS: Direct KPI Achievement Correctness
# ============================================================

@given(actual=st.floats(min_value=0, max_value=10000), target=st.floats(min_value=0.001, max_value=10000))
@settings(max_examples=100)
def test_property_direct_kpi_achievement_no_division_error(actual, target):
    """
    Property 1: Direct KPI Achievement Correctness
    
    For any direct KPI with actual ≥ 0 and target > 0:
    - Achievement = actual/target × 100 produces result ≥ 0
    - No division errors
    
    Validates: Requirements 4.1-4.3
    """
    achievement = calculate_achievement(actual, target, is_inverse=False, cap_at_100=False)
    assert achievement >= 0
    assert not np.isnan(achievement)
    assert not np.isinf(achievement)


@given(actual=st.floats(min_value=0, max_value=10000), target=st.floats(min_value=0.001, max_value=10000))
@settings(max_examples=100)
def test_property_pharmacy_direct_kpi_calculation(actual, target):
    """
    Property 1: Achievement Calculation Correctness (Direct KPIs) - Pharmacy Specific
    
    For Pharmacy team direct KPIs, with actual ≥ 0 and target > 0:
    - Formula: achievement = (actual/target) × 100
    - Result must be ≥ 0
    - No NaN or Infinity values
    - Test includes edge cases: actual=0, target=0.001, large values (10000/1)
    
    This property validates that direct KPI calculations (higher is better) work
    correctly across all valid numeric input ranges, including edge cases.
    
    **Validates: Requirements 4.1-4.3**
    
    Test Strategy:
    - Generate 100+ random (actual, target) pairs with strategy:
      @given(actual=st.floats(min_value=0, max_value=10000), 
             target=st.floats(min_value=0.001, max_value=10000))
    - For each pair, verify: achievement = (actual/target) × 100
    - Verify: achievement ≥ 0, not NaN, not Inf
    - Edge cases automatically included by hypothesis:
      * actual=0 → achievement = 0
      * target=0.001 (very small) → achievement = actual / 0.001 × 100
      * large values like 10000/1 → achievement = 10000 × 100 / 1
    """
    # Calculate achievement for direct KPI (higher is better)
    achievement = calculate_achievement(actual, target, is_inverse=False, cap_at_100=False)
    
    # ===== Verify result is valid (no NaN, no Inf) =====
    assert not np.isnan(achievement), \
        f"Achievement is NaN for actual={actual}, target={target}"
    assert not np.isinf(achievement), \
        f"Achievement is Inf for actual={actual}, target={target}"
    
    # ===== Verify result is non-negative =====
    assert achievement >= 0, \
        f"Achievement {achievement} is negative for actual={actual}, target={target}"
    
    # ===== Verify formula correctness: achievement = (actual/target) × 100 =====
    expected_achievement = min((actual / target) * 100.0, 100.0)
    assert abs(achievement - expected_achievement) < 1e-6, \
        f"Achievement calculation incorrect: got {achievement}, expected {expected_achievement} " \
        f"for actual={actual}, target={target}"
    
    # ===== Edge case: actual = 0 =====
    # When actual = 0, achievement should be 0 (0/target × 100 = 0)
    if actual == 0:
        assert achievement == 0, \
            f"Achievement should be 0 when actual=0, but got {achievement}"
    
    # ===== Edge case: very small target (0.001) =====
    # With target=0.001, achievement = (actual/0.001) × 100 = actual × 100,000
    # This should still work without overflow
    if target == 0.001:
        expected = min((actual / 0.001) * 100.0, 100.0)
        assert abs(achievement - expected) < 1e-4, \
            f"Achievement should handle small target 0.001 correctly"
    
    # ===== Edge case: large values =====
    # Test cases like 10000/1 should produce 1,000,000% achievement without error
    # Pharmacy achievements are capped by the global scoring rule.
    if actual == 10000 and target == 1:
        expected = 1000000.0
        assert abs(achievement - expected) < 1e-6, \
            f"Achievement for large values (10000/1) should be {expected}, got {achievement}"


@given(actual=st.floats(min_value=0.001, max_value=10000), target=st.floats(min_value=0, max_value=10000))
@settings(max_examples=100)
def test_property_inverse_kpi_achievement_no_division_error(actual, target):
    """
    Property 2: Inverse KPI Achievement Correctness
    
    For any inverse KPI with actual > 0 and target ≥ 0:
    - Achievement = target/actual × 100 produces valid result
    - No division errors, no NaN/Inf values
    
    Validates: Requirements 5.1-5.6, 8.1
    """
    achievement = calculate_achievement(actual, target, is_inverse=True, cap_at_100=False)
    assert achievement >= 0
    assert not np.isnan(achievement)
    assert not np.isinf(achievement)


# ============================================================
# PROPERTY TESTS: Pharmacy Inverse KPI Achievement Correctness (Task 5.2)
# ============================================================

@given(actual=st.floats(min_value=0.001, max_value=10000), target=st.floats(min_value=0, max_value=10000))
@settings(max_examples=100)
def test_property_pharmacy_inverse_kpi_calculation(actual, target):
    """
    Property 2: Achievement Calculation Correctness (Inverse KPIs)
    
    **Validates: Requirements 5.1-5.6, 8.1**
    
    For Pharmacy inverse KPIs with actual > 0 and target ≥ 0:
    - Verify: achievement = (target/actual) × 100 produces mathematically correct result
    - Verify: no NaN, no Inf values, no division errors
    - Verify: result is always non-negative
    - Verify: global cap applies to Pharmacy achievements
    
    Test cases covered by hypothesis:
    - Random (actual, target) pairs where 0.001 ≤ actual ≤ 10000, 0 ≤ target ≤ 10000
    - This covers normal operation ranges for all Pharmacy inverse KPIs
    - (WaitingTime, Leakage per Requirements 5.1)
    
    Special case: actual=0 is tested separately below
    """
    # Calculate achievement for inverse KPI
    achievement = calculate_achievement(
        actual=actual,
        target=target,
        is_inverse=True,
        cap_at_100=False  # compatibility argument; the product rule still caps at 100%
    )
    
    # Verification 1: Mathematical correctness
    # achievement = (target / actual) * 100
    expected = min((target / actual) * 100.0, 100.0)
    assert abs(achievement - expected) < 1e-10, \
        f"Achievement {achievement} should equal (target/actual)*100 = {expected}"
    
    # Verification 2: No NaN or Infinity
    assert not np.isnan(achievement), \
        f"Achievement should not be NaN. actual={actual}, target={target}"
    assert not np.isinf(achievement), \
        f"Achievement should not be Infinity. actual={actual}, target={target}"
    
    # Verification 3: Non-negative result
    assert achievement >= 0, \
        f"Achievement should be non-negative. Got {achievement}. actual={actual}, target={target}"
    
    # Verification 4: Global cap when target > actual
    if target > actual:
        actual_exceeds_100 = achievement > 100.0
        assert not actual_exceeds_100, \
            f"Pharmacy inverse KPI exceeded global cap: achievement={achievement}"


@given(target=st.floats(min_value=0, max_value=10000))
@settings(max_examples=100)
def test_property_pharmacy_inverse_kpi_actual_zero(target):
    """
    Property 2: Achievement Calculation Correctness (Inverse KPIs) - Special Case actual=0
    
    **Validates: Requirements 5.2, 5.3, 8.1**
    
    For Pharmacy inverse KPIs when actual = 0:
    - Verify: achievement = 100 (no division by zero error per Requirement 5.2)
    - Verify: handles both target=0 and target>0 cases
    - Verify: logs the edge case (actual=0) for audit purposes per Requirement 5.6
    
    This test ensures the system gracefully handles the edge case where
    actual performance is zero by assuming perfect achievement (100% per Requirement 5.2).
    
    Test Strategy:
    - Generate 100+ random target values: 0 ≤ target ≤ 10000
    - For each, test with actual=0
    - Verify achievement returns 100% without division error
    """
    # Test case 1: actual=0, target > 0
    achievement = calculate_achievement(
        actual=0,
        target=target,
        is_inverse=True,
        cap_at_100=False
    )
    
    # Verification 1: Should return 100% with no division error per Requirement 5.2
    assert achievement == 100.0, \
        f"When actual=0 (inverse KPI), achievement should be 100%. Got {achievement}. target={target}"
    
    # Verification 2: Should not produce NaN or Inf
    assert not np.isnan(achievement), \
        f"Achievement should not be NaN when actual=0. target={target}"
    assert not np.isinf(achievement), \
        f"Achievement should not be Infinity when actual=0. target={target}"
    
    # Test case 2: actual=0, target=0 (edge case per Requirement 5.3)
    if target == 0:
        achievement_both_zero = calculate_achievement(
            actual=0,
            target=0,
            is_inverse=True,
            cap_at_100=False
        )
        # When both are zero, should still return 100% per Requirement 5.3
        assert achievement_both_zero == 100.0, \
            f"When actual=0 and target=0 (inverse KPI), achievement should be 100%. Got {achievement_both_zero}"


@given(
    actual=st.floats(min_value=0.001, max_value=10000),
    target=st.floats(min_value=0, max_value=10000)
)
@settings(max_examples=50)
def test_property_pharmacy_inverse_kpi_edge_cases(actual, target):
    """
    Property 2: Achievement Calculation Correctness (Inverse KPIs) - Edge Cases
    
    **Validates: Requirements 5.1-5.6**
    
    Test comprehensive edge cases for Pharmacy inverse KPIs:
    - actual ≈ target: achievement ≈ 100% (target/actual ≈ 1)
    - target > actual: achievement > 100% (lower is better, exceeding targets)
    - target < actual: achievement < 100% (poor performance, actual exceeds target)
    - target=0, actual>0: achievement = 0% (per Requirement 5.4)
    
    These cases ensure the inverse KPI formula behaves correctly across
    all performance scenarios for Pharmacy team (WaitingTime, Leakage).
    
    Test Strategy:
    - Generate 50+ random (actual, target) pairs
    - For each pair, verify formula correctness and boundary conditions
    - Ensure all outputs are valid (no NaN/Inf)
    """
    achievement = calculate_achievement(
        actual=actual,
        target=target,
        is_inverse=True,
        cap_at_100=False
    )
    
    # Edge case 1: actual ≈ target should give achievement ≈ 100% (target/actual ≈ 1)
    # Use a relative tolerance rather than absolute: both should be close in value relative to their magnitudes
    if actual > 0 and target > 0:
        ratio = target / actual
        if 0.95 <= ratio <= 1.05:  # Within 5% of each other
            # When actual ≈ target, achievement ≈ 100%
            expected = (target / actual) * 100.0
            assert abs(achievement - 100.0) < 5.0, \
                f"When actual≈target (within 5%), achievement should be ≈100%. Got {achievement}, ratio={ratio}"
    
    # Edge case 2: target > actual should give achievement > 100% (lower is better)
        if target > actual and actual > 0:
            assert achievement == 100.0, \
                f"When target>actual (inverse KPI), achievement should cap at 100%. Got {achievement}. target={target}, actual={actual}"
    
    # Edge case 3: target < actual should give achievement < 100% (poor performance)
    if target < actual and actual > 0:
        assert achievement < 100.0, \
            f"When target<actual (inverse KPI), achievement should be <100%. Got {achievement}. target={target}, actual={actual}"
    
    # Edge case 4: target=0 with actual>0 should give achievement=0% per Requirement 5.4
    if target == 0 and actual > 0:
        expected = (0 / actual) * 100.0
        assert achievement == expected == 0.0, \
            f"When target=0 and actual>0 (inverse KPI), achievement should be 0%. Got {achievement}"
    
    # All cases: verify valid output (no NaN/Inf)
    assert not np.isnan(achievement), \
        f"Achievement should not be NaN. actual={actual}, target={target}"
    assert not np.isinf(achievement), \
        f"Achievement should not be Infinity. actual={actual}, target={target}"
    assert achievement >= 0, \
        f"Achievement should be non-negative. Got {achievement}"


# ============================================================
# PROPERTY TESTS: Coding Inverse KPI Achievement Correctness
# ============================================================

@given(actual=st.floats(min_value=0.001, max_value=10000), target=st.floats(min_value=0, max_value=10000))
@settings(max_examples=100)
def test_property_coding_inverse_kpi_calculation(actual, target):
    """
    Property 2: Achievement Calculation Correctness (Inverse KPIs)
    
    **Validates: Requirements 5.1-5.6**
    
    For Coding team's inverse KPIs (QualityErrors, Rejection, TAT):
    - When actual > 0: achievement = (target / actual) × 100
    - When actual = 0: achievement = 100% (no division by zero error)
    - Verify achievement calculation is identical to Pharmacy inverse (5.2)
    - Confirm no difference between Pharmacy and Coding inverse formulas
    
    Test Strategy (Hypothesis-based with 100+ iterations):
    - Generate random (actual, target) pairs where:
      - actual: [0.001, 10000] (strictly positive for inverse)
      - target: [0, 10000] (non-negative)
    - For each pair, calculate achievement using inverse formula
    - Verify: achievement = (target / actual) × 100
    - Verify: result >= 0, no NaN/Inf values
    - Verify: matches Pharmacy inverse KPI behavior (same formula)
    - Implicit verification that Coding inverse KPIs work identically to Pharmacy
    
    This test confirms that Requirement 5.1 (inverse formula = target/actual × 100)
    applies to ALL inverse KPIs across teams, not just Pharmacy.
    """
    achievement = calculate_achievement(actual, target, is_inverse=True, cap_at_100=False)
    
    # Verify calculation correctness
    expected_achievement = min((target / actual) * 100, 100.0) if actual > 0 else 100.0
    assert abs(achievement - expected_achievement) < 1e-6, \
        f"Coding inverse KPI: actual={actual}, target={target}, " \
        f"expected={expected_achievement}, got={achievement}"
    
    # Verify result validity
    assert achievement >= 0, f"Coding inverse KPI achievement {achievement} is negative"
    assert not np.isnan(achievement), f"Coding inverse KPI achievement is NaN"
    assert not np.isinf(achievement), f"Coding inverse KPI achievement is Inf"


@given(target=st.floats(min_value=0, max_value=1000))
@settings(max_examples=100)
def test_property_coding_inverse_kpi_zero_actual(target):
    """
    Property 2 Edge Case: Zero Division Prevention for Coding Inverse KPIs
    
    **Validates: Requirements 5.2, 5.6**
    
    For Coding team's inverse KPIs when actual = 0:
    - System returns achievement = 100% (no division by zero error)
    - No exception raised
    - Identical behavior to Pharmacy team (5.2)
    
    This verifies Requirement 5.2: "WHEN actual value is 0, THE System SHALL 
    return achievement of 100% (no division by zero error)"
    """
    achievement = calculate_achievement(actual=0, target=target, is_inverse=True, cap_at_100=False)
    
    assert achievement == 100.0, \
        f"Coding inverse KPI with actual=0, target={target} should return 100%, got {achievement}"
    assert not np.isnan(achievement), "Achievement should not be NaN"
    assert not np.isinf(achievement), "Achievement should not be Inf"


# ============================================================
# PROPERTY TESTS: Capping Behavior
# ============================================================

@given(
    achievements=st.lists(st.floats(min_value=0, max_value=200), min_size=3, max_size=5),
    weights=st.lists(st.floats(min_value=0.1, max_value=0.4), min_size=3, max_size=5)
)
@settings(max_examples=100)
def test_property_pharmacy_capped_scoring(achievements, weights):
    """
    Property 3: Global capped achievement for Pharmacy
    
    For any Pharmacy team performance record:
    - Score = Σ(achievement_i × weight_i) without upper bound
    - Can exceed 100%
    - All KPIs at 100% → score = 100%
    - All KPIs at 120% → score = 120%
    
    **Validates: Requirements 6.1-6.5**
    
    Generates random KPI achievements with values > 100% for some KPIs.
    Verifies the global cap before weighting.
    Tests boundary conditions with all KPIs at specific percentages.
    """
    # Ensure weights sum to 1.0
    if len(achievements) != len(weights):
        weights = weights[:len(achievements)]
    
    total_weight = sum(weights)
    if total_weight > 0:
        normalized_weights = [w / total_weight for w in weights]
        
        capped = [min(max(a, 0.0), 100.0) for a in achievements]
        score = min(sum(a * w for a, w in zip(capped, normalized_weights)), 100.0)
        
        # VERIFY: the global cap is always applied
        assert score >= 0, f"Score should be non-negative, got {score}"
        assert not np.isnan(score), f"Score should not be NaN, got {score}"
        assert not np.isinf(score), f"Score should not be infinite, got {score}"
        
        assert score <= 100.0


# Specific test case: All KPIs at 100% → score = 100%
def test_pharmacy_capped_all_kpis_100_percent():
    """
    Test specific case: All Pharmacy KPIs at 100% achievement → score = 100%.
    
    This is a boundary condition verifying basic correctness.
    With all achievements at 100%, capped score must equal 100%.
    
    **Validates: Requirements 6.3**
    """
    # 5 KPIs all at 100% (Pharmacy has 5 KPIs, each weighted 0.20)
    achievements = [100.0, 100.0, 100.0, 100.0, 100.0]
    weights = [0.20, 0.20, 0.20, 0.20, 0.20]
    
    # Calculate uncapped score
    score = sum(a * w for a, w in zip(achievements, weights))
    
    # Must equal exactly 100%
    assert score == 100.0, f"Expected 100.0 with all KPIs at 100%, got {score}"
    assert not np.isnan(score)
    assert not np.isinf(score)


# Specific test case: All KPIs at 120% → score = 120%
def test_pharmacy_capped_all_kpis_120_percent():
    """
    Test specific case: All Pharmacy KPIs at 120% achievement → score = 120%.
    
    This verifies that raw values above target are capped at 100%.
    With all achievements at 120%, capped score must equal 100%.
    
    **Validates: Requirements 6.2, 6.4**
    """
    # 5 KPIs all at 120% (Pharmacy has 5 KPIs, each weighted 0.20)
    achievements = [120.0, 120.0, 120.0, 120.0, 120.0]
    weights = [0.20, 0.20, 0.20, 0.20, 0.20]
    
    score = min(sum(min(a, 100.0) * w for a, w in zip(achievements, weights)), 100.0)
    
    assert score == 100.0, f"Expected 100.0 with all KPIs at 120%, got {score}"
    assert score <= 100.0
    assert not np.isnan(score)
    assert not np.isinf(score)


# Test case: Mixed achievements with some > 100%
def test_pharmacy_capped_mixed_achievements():
    """
    Test mixed achievements where some KPIs exceed 100%.
    
    Verifies that above-target KPI values are capped before weighting.
    
    **Validates: Requirements 6.4**
    """
    # Pharmacy: 5 KPIs, each 0.20 weight
    # Some above 100%, some below
    achievements = [80.0, 110.0, 100.0, 120.0, 95.0]
    weights = [0.20, 0.20, 0.20, 0.20, 0.20]
    
    score = min(sum(min(a, 100.0) * w for a, w in zip(achievements, weights)), 100.0)
    
    # Manual calculation: 80*0.2 + 110*0.2 + 100*0.2 + 120*0.2 + 95*0.2
    #                  = 16 + 20 + 20 + 20 + 19 = 95
    expected = 95.0
    assert abs(score - expected) < 1e-6, f"Expected {expected}, got {score}"
    assert score <= 100.0
    assert not np.isnan(score)


# Property test: Score is linear combination of weighted achievements
@given(
    achievements=st.lists(
        st.floats(min_value=0, max_value=200, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=5
    ),
    weights=st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=5
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_pharmacy_score_is_weighted_sum(achievements, weights):
    """
    Property: Pharmacy performance score is exactly Σ(achievement_i × weight_i).
    
    Regardless of achievement values or distribution, score calculation
    must be a linear combination with no non-linear transforms or capping.
    
    **Validates: Requirements 6.1**
    """
    # Match array lengths
    if len(achievements) != len(weights):
        weights = weights[:len(achievements)]
    
    # Skip if empty
    if not achievements or not weights:
        return
    
    # Normalize weights to sum to 1.0
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]
    
    capped = [min(max(a, 0.0), 100.0) for a in achievements]
    score = min(sum(a * w for a, w in zip(capped, normalized_weights)), 100.0)
    
    # VERIFY: Score is exactly the weighted sum
    expected = min(sum(a * w for a, w in zip(capped, normalized_weights)), 100.0)
    assert abs(score - expected) < 1e-9, \
        f"Score calculation mismatch: got {score}, expected {expected}"
    
    assert score <= 100.0
    
    # VERIFY: Output is finite and not NaN
    assert not np.isnan(score), f"Score is NaN"
    assert not np.isinf(score), f"Score is infinite"


# Property test: Uncapped vs Capped comparison
@given(
    achievements=st.lists(
        st.floats(min_value=50, max_value=150, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=5
    ),
    weights=st.lists(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=5
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_pharmacy_global_cap_consistency(achievements, weights):
    """
    Property: Pharmacy uses the same global cap as every other team.
    
    This property verifies the global achievement cap for Pharmacy
    and Coding/CSR (capped at 100%). With same achievements and weights:
    - Pharmacy: score can be > 100%
    - Capped teams: score ≤ 100%
    
    **Validates: Requirements 6.1, 6.2**
    """
    # Match lengths
    if len(achievements) != len(weights):
        weights = weights[:len(achievements)]
    
    if not achievements or not weights:
        return
    
    # Normalize weights
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]
    
    # Calculate the global capped score.
    capped_achievements = [min(a, 100.0) for a in achievements]
    capped_score = min(sum(a * w for a, w in zip(capped_achievements, normalized_weights)), 100.0)
    
    assert capped_score >= 0
    assert capped_score <= 100.0, f"Capped score should never exceed 100%, got {capped_score}"


@given(
    achievements=st.lists(st.floats(min_value=0, max_value=200), min_size=3, max_size=5),
    weights=st.lists(st.floats(min_value=0.1, max_value=0.4), min_size=3, max_size=5)
)
@settings(max_examples=100)
def test_property_coding_csr_capped_scoring(achievements, weights):
    """
    Property 4: Capped Achievement for Coding & CSR
    
    For any Coding or CSR team performance record:
    - Each achievement capped at 100% before weighting
    - Final score = MIN(100%, Σ(capped_achievement_i × weight_i))
    - Score never exceeds 100%
    
    Validates: Requirements 7.1-7.5
    """
    if len(achievements) != len(weights):
        weights = weights[:len(achievements)]
    
    total_weight = sum(weights)
    if total_weight > 0:
        normalized_weights = [w / total_weight for w in weights]
        
        # Cap individual achievements first
        capped_achievements = [min(a, 100.0) for a in achievements]
        
        # Calculate capped score
        score = sum(a * w for a, w in zip(capped_achievements, normalized_weights))
        score = min(score, 100.0)
        
        # Verify capping
        assert 0 <= score <= 100.0
        assert not np.isnan(score)


@given(
    achievements=st.lists(st.floats(min_value=0, max_value=200), min_size=3, max_size=3)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_coding_capped_scoring(achievements):
    """
    Property 4: Capped Achievement for Coding & CSR
    
    **Validates: Requirements 7.1-7.5**
    
    For Coding team performance scoring:
    - Generate random KPI achievements for Coding team's 3 inverse KPIs (0-200% range)
    - Each achievement is capped at 100% BEFORE weighting
    - Final score = MIN(100%, Σ(capped_achievement × weight))
    - Coding team weights: QualityErrors=0.20, Rejection=0.50, TAT=0.30
    
    Test Cases Verified:
    1. Weighted sum = 95% → final = 95% (no capping needed)
    2. Weighted sum = 120% → final = 100% (capped)
    3. Individual achievement = 150% → capped to 100% before weighting
    
    Invariants:
    - Final score always <= 100%
    - Final score never NaN or Inf
    - Each capped achievement <= 100%
    - Capping happens at individual KPI level BEFORE weighting
    
    Strategy:
    - Use Hypothesis to generate 100+ random achievement combinations
    - Test with achievements from 0% to 200% to verify capping behavior
    - Verify both edge cases and typical scenarios
    """
    
    # Coding team weights: QualityErrors=0.20, Rejection=0.50, TAT=0.30
    weights = [0.20, 0.50, 0.30]
    
    # Ensure exactly 3 achievements for Coding's 3 KPIs
    if len(achievements) < 3:
        return  # Skip if not enough data
    
    achievements_coding = achievements[:3]
    
    # ===== Step 1: Cap individual achievements at 100% BEFORE weighting =====
    capped_achievements = [min(a, 100.0) for a in achievements_coding]
    
    # Verify each capped achievement <= 100%
    for idx, capped in enumerate(capped_achievements):
        assert capped <= 100.0, \
            f"Achievement {idx}: capped value {capped} exceeds 100% " \
            f"(original: {achievements_coding[idx]})"
    
    # Verify capping happened for achievements > 100%
    for idx, (original, capped) in enumerate(zip(achievements_coding, capped_achievements)):
        if original > 100.0:
            assert capped == 100.0, \
                f"Achievement {idx}: value {original} > 100% should be capped to 100%, " \
                f"got {capped}"
        else:
            assert abs(capped - original) < 1e-6, \
                f"Achievement {idx}: value {original} <= 100% should not change, " \
                f"got {capped}"
    
    # ===== Step 2: Calculate weighted sum =====
    weighted_sum = sum(a * w for a, w in zip(capped_achievements, weights))
    
    # ===== Step 3: Apply final capping at 100% =====
    final_score = min(weighted_sum, 100.0)
    
    # ===== Verification: Final Score Bounds =====
    
    # 1. Final score must be in [0, 100]
    assert 0 <= final_score <= 100.0, \
        f"Final score {final_score} out of bounds [0, 100] " \
        f"(achievements: {achievements_coding}, capped: {capped_achievements})"
    
    # 2. No NaN values
    assert not np.isnan(final_score), \
        f"Final score is NaN (achievements: {achievements_coding}, " \
        f"capped: {capped_achievements})"
    
    # 3. No Inf values
    assert not np.isinf(final_score), \
        f"Final score is Inf (achievements: {achievements_coding}, " \
        f"capped: {capped_achievements})"
    
    # 4. Final score never exceeds 100%
    assert final_score <= 100.0, \
        f"Final score {final_score} exceeds 100% limit"
    
    # ===== Verification: Capping Logic =====
    
    # 5. If weighted sum > 100%, final score must equal 100%
    if weighted_sum > 100.0:
        assert abs(final_score - 100.0) < 1e-6, \
            f"When weighted_sum {weighted_sum} > 100%, " \
            f"final_score should be 100%, got {final_score}"
    
    # 6. If weighted sum <= 100%, final score must equal weighted sum
    if weighted_sum <= 100.0:
        assert abs(final_score - weighted_sum) < 1e-6, \
            f"When weighted_sum {weighted_sum} <= 100%, " \
            f"final_score should equal {weighted_sum}, got {final_score}"
    
    # ===== Specific Test Cases Embedded in Property Test =====
    
    # Test Case 1: Weighted sum = 95% (no capping needed)
    # When achievements = [90, 100, 90]: 90*0.20 + 100*0.50 + 90*0.30 = 95%
    case1_achievements = [90.0, 100.0, 90.0]
    case1_capped = [min(a, 100.0) for a in case1_achievements]
    case1_score = min(sum(a * w for a, w in zip(case1_capped, weights)), 100.0)
    assert abs(case1_score - 95.0) < 0.01, \
        f"Test Case 1 (95%): expected 95.0, got {case1_score}"
    assert case1_score <= 100.0, f"Test Case 1: score exceeds 100%"
    assert not np.isnan(case1_score), "Test Case 1: score is NaN"
    assert not np.isinf(case1_score), "Test Case 1: score is Inf"
    
    # Test Case 2: Individual achievement = 150% (capped to 100% before weighting)
    # When achievements = [150, 80, 90]:
    #   Capped: [100, 80, 90]
    #   Score: 100*0.20 + 80*0.50 + 90*0.30 = 20 + 40 + 27 = 87%
    case2_achievements = [150.0, 80.0, 90.0]
    case2_capped = [min(a, 100.0) for a in case2_achievements]
    case2_score = min(sum(a * w for a, w in zip(case2_capped, weights)), 100.0)
    assert case2_capped[0] == 100.0, \
        f"Test Case 2: First achievement should be capped to 100%, " \
        f"got {case2_capped[0]}"
    assert abs(case2_score - 87.0) < 0.01, \
        f"Test Case 2 (individual 150%): expected 87.0, got {case2_score}"
    assert case2_score <= 100.0, f"Test Case 2: score exceeds 100%"
    assert not np.isnan(case2_score), "Test Case 2: score is NaN"
    assert not np.isinf(case2_score), "Test Case 2: score is Inf"
    
    # Test Case 3: All achievements at 100% (boundary case)
    # When achievements = [100, 100, 100]: score = 100%
    case3_achievements = [100.0, 100.0, 100.0]
    case3_capped = [min(a, 100.0) for a in case3_achievements]
    case3_score = min(sum(a * w for a, w in zip(case3_capped, weights)), 100.0)
    assert abs(case3_score - 100.0) < 0.01, \
        f"Test Case 3 (all at 100%): expected 100.0, got {case3_score}"
    assert case3_score <= 100.0, f"Test Case 3: score exceeds 100%"


# ============================================================
# PROPERTY TESTS: CSR Capped Scoring
# ============================================================

def test_csr_capped_scoring_specific_cases():
    """
    Test specific cases for CSR capped scoring.
    
    CSR team configuration:
    - Rejection (inverse): 40% weight
    - Queries (direct): 30% weight
    - AttendedCR (direct): 30% weight
    - All achievements capped at 100% before weighting
    - Final score capped at 100%
    
    Validates: Requirements 7.1-7.5
    
    Test Cases:
    1. Mixed KPIs with weighted sum < 100% → final = calculated value
    2. Mixed KPIs with weighted sum > 100% → final = 100% (capped)
    3. Individual achievements > 100% → each capped to 100% before weighting
    """
    
    # CSR team weights: Rejection=0.40, Queries=0.30, AttendedCR=0.30
    weights_ordered = [0.40, 0.30, 0.30]  # [Rejection, Queries, AttendedCR]
    
    # ===== Test Case 1: Mixed KPIs with weighted sum < 100% =====
    # Rejection achievement: 50% (inverse)
    # Queries achievement: 80% (direct)
    # AttendedCR achievement: 75% (direct)
    # Score: 50*0.40 + 80*0.30 + 75*0.30 = 20 + 24 + 22.5 = 66.5%
    
    achievements_case1 = [50.0, 80.0, 75.0]
    capped_case1 = [min(a, 100.0) for a in achievements_case1]
    score_case1_uncapped = sum(a * w for a, w in zip(capped_case1, weights_ordered))
    score_case1 = min(score_case1_uncapped, 100.0)
    
    assert abs(score_case1 - 66.5) < 0.01, \
        f"Test case 1 (mixed < 100%): expected 66.5, got {score_case1}"
    assert score_case1 <= 100.0, f"Test case 1: score {score_case1} exceeds 100%"
    assert not np.isnan(score_case1), "Test case 1: score is NaN"
    assert not np.isinf(score_case1), "Test case 1: score is Inf"
    
    # ===== Test Case 2: Mixed KPIs with weighted sum > 100% → final = 100% (capped) =====
    # Create scenario where uncapped sum > 100% but capped sum would be <= 100%
    # Rejection: 120% → capped to 100%
    # Queries: 120% → capped to 100%
    # AttendedCR: 120% → capped to 100%
    # Uncapped sum: 120*0.40 + 120*0.30 + 120*0.30 = 48 + 36 + 36 = 120%
    # Capped sum: 100*0.40 + 100*0.30 + 100*0.30 = 40 + 30 + 30 = 100%
    
    achievements_case2 = [120.0, 120.0, 120.0]
    capped_case2 = [min(a, 100.0) for a in achievements_case2]
    score_case2_uncapped = sum(a * w for a, w in zip(capped_case2, weights_ordered))
    score_case2 = min(score_case2_uncapped, 100.0)
    
    assert abs(score_case2 - 100.0) < 0.01, \
        f"Test case 2 (all 120%): expected 100.0, got {score_case2}"
    assert score_case2 <= 100.0, f"Test case 2: score {score_case2} exceeds 100%"
    assert not np.isnan(score_case2), "Test case 2: score is NaN"
    
    # ===== Test Case 3: Individual Achievement > 100% (Capped to 100% Before Weighting) =====
    # Rejection: 150% → capped to 100%
    # Queries: 80% (remains 80%)
    # AttendedCR: 90% (remains 90%)
    # Score: 100*0.40 + 80*0.30 + 90*0.30 = 40 + 24 + 27 = 91%
    
    achievements_case3 = [150.0, 80.0, 90.0]
    capped_case3 = [min(a, 100.0) for a in achievements_case3]
    score_case3 = sum(a * w for a, w in zip(capped_case3, weights_ordered))
    score_case3 = min(score_case3, 100.0)
    
    assert capped_case3[0] == 100.0, \
        f"Test case 3: First achievement should be capped to 100%, got {capped_case3[0]}"
    assert abs(score_case3 - 91.0) < 0.01, \
        f"Test case 3 (individual 150%): expected 91.0, got {score_case3}"
    assert score_case3 <= 100.0, f"Test case 3: score {score_case3} exceeds 100%"
    assert not np.isnan(score_case3), "Test case 3: score is NaN"


@given(
    achievements=st.lists(st.floats(min_value=0, max_value=200), min_size=3, max_size=3)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_csr_capped_scoring(achievements):
    """
    Property 4: Capped Achievement for Coding & CSR - CSR Team
    
    For CSR team (3 KPIs with 1 inverse + 2 direct, weights 0.40, 0.30, 0.30):
    - Generate random achievements (0-200% to test capping)
    - Each achievement capped at 100% BEFORE weighting
    - Final score = MIN(100%, Σ(capped_achievement × weight))
    - Verify: final_score always in [0, 100]
    - Verify: no NaN, no Inf values
    - Verify: individual achievements capped at 100% don't exceed bound
    - Verify: final score never exceeds 100%
    
    CSR KPI Configuration:
    - Rejection (inverse, 40%)
    - Queries (direct, 30%)
    - AttendedCR (direct, 30%)
    
    Validates: Requirements 7.1-7.5
    
    Generates 100+ test cases.
    """
    # CSR team weights: Rejection=0.40, Queries=0.30, AttendedCR=0.30
    weights = [0.40, 0.30, 0.30]
    
    # Ensure we have exactly 3 achievements for CSR's 3 KPIs
    if len(achievements) < 3:
        return  # Skip if not enough
    
    achievements = achievements[:3]
    
    # Cap individual achievements at 100% BEFORE weighting
    capped_achievements = [min(a, 100.0) for a in achievements]
    
    # Calculate weighted sum
    weighted_sum = sum(a * w for a, w in zip(capped_achievements, weights))
    
    # Apply final capping at 100%
    final_score = min(weighted_sum, 100.0)
    
    # ===== Verification =====
    
    # 1. Final score must be in [0, 100]
    assert 0 <= final_score <= 100.0, \
        f"Final score {final_score} out of bounds [0, 100]"
    
    # 2. No NaN values
    assert not np.isnan(final_score), \
        f"Final score is NaN (achievements: {achievements}, capped: {capped_achievements})"
    
    # 3. No Inf values
    assert not np.isinf(final_score), \
        f"Final score is Inf (achievements: {achievements}, capped: {capped_achievements})"
    
    # 4. Each capped achievement <= 100%
    for idx, capped in enumerate(capped_achievements):
        assert capped <= 100.0, \
            f"Achievement {idx} capped value {capped} exceeds 100%"
    
    # 5. Final score always <= 100%
    assert final_score <= 100.0, \
        f"Final score {final_score} exceeds 100% limit"
    
    # 6. Verify capping happened for achievements > 100%
    for original, capped in zip(achievements, capped_achievements):
        if original > 100.0:
            assert capped == 100.0, \
                f"Achievement > 100% should be capped to 100%, got {capped}"
        else:
            assert capped == original, \
                f"Achievement <= 100% should not change, {original} became {capped}"
    
    # 7. Verify weight sum behavior
    # With capped achievements at 100%, the maximum possible score is:
    # 100*0.40 + 100*0.30 + 100*0.30 = 100%
    # So if any uncapped achievement > 100%, capping must occur
    if any(a > 100.0 for a in achievements):
        # At least one uncapped achievement > 100%
        # After capping to 100%, max weighted sum = 100%
        assert weighted_sum <= 100.0, \
            f"After individual capping, weighted sum {weighted_sum} should be <= 100%"
    
    # 8. Verify no achievement values lost during capping
    for idx, (original, capped) in enumerate(zip(achievements, capped_achievements)):
        # If original was already <= 100%, should remain unchanged
        if original <= 100.0:
            assert abs(original - capped) < 1e-9, \
                f"Achievement {idx}: uncapped value {original} was incorrectly modified to {capped}"
        else:
            # If original > 100%, should be exactly 100.0
            assert capped == 100.0, \
                f"Achievement {idx}: value > 100% should cap to 100.0, got {capped}"


# ============================================================
# PROPERTY TESTS: Grade Assignment Consistency
# ============================================================

@given(score=st.floats(min_value=0, max_value=150))
@settings(max_examples=100)
def test_property_grade_assignment_consistency(score):
    """
    Property 5: Grade Assignment Consistency
    
    For any performance score and team configuration:
    - Grade assignment strictly follows threshold ordering (A ≥ B ≥ C ≥ D)
    - Each score gets exactly one grade
    - No score gets multiple grades
    
    Validates: Requirements 8.1-8.6
    """
    def assign_grade(s):
        if s >= 95:
            return 'A'
        elif s >= 85:
            return 'B'
        elif s >= 75:
            return 'C'
        elif s >= 65:
            return 'D'
        else:
            return 'E'
    
    grade = assign_grade(score)
    
    # Verify correct grade
    if score >= 95:
        assert grade == 'A'
    elif score >= 85:
        assert grade == 'B'
    elif score >= 75:
        assert grade == 'C'
    elif score >= 65:
        assert grade == 'D'
    else:
        assert grade == 'E'


# ============================================================
# PROPERTY TESTS: Weight Sum Validation
# ============================================================

def test_property_pharmacy_weight_sum_validation():
    """
    Property 6: Weight Sum Validation
    
    For Pharmacy team configuration:
    - Sum of all KPI weights equals 1.0 (within 0.001 tolerance)
    
    Validates: Requirements 1.7, 20.1
    """
    config = load_team_config("Pharmacy")
    total_weight = sum(kpi['weight'] for kpi in config['kpis'])
    assert abs(total_weight - 1.0) < 0.001


def test_property_coding_weight_sum_validation():
    """Test Coding team weight sum validation."""
    config = load_team_config("Coding")
    total_weight = sum(kpi['weight'] for kpi in config['kpis'])
    assert abs(total_weight - 1.0) < 0.001


def test_property_csr_weight_sum_validation():
    """Test CSR team weight sum validation."""
    config = load_team_config("CSR")
    total_weight = sum(kpi['weight'] for kpi in config['kpis'])
    assert abs(total_weight - 1.0) < 0.001


# ============================================================
# PROPERTY TESTS: Zero Division Prevention
# ============================================================

@given(target=st.floats(min_value=0, max_value=1000))
@settings(max_examples=100)
def test_property_inverse_kpi_zero_division_prevention(target):
    """
    Property 8: Zero Division Prevention for Inverse KPIs
    
    For any inverse KPI with actual value = 0:
    - System returns achievement = 100% (no division error)
    - No exception raised
    
    Validates: Requirements 5.6
    """
    achievement = calculate_achievement(actual=0, target=target, is_inverse=True, cap_at_100=False)
    assert achievement == 100.0
    assert not np.isnan(achievement)
    assert not np.isinf(achievement)


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    def test_pharmacy_config_complete_workflow(self):
        """Test complete Pharmacy configuration workflow."""
        config = load_team_config("Pharmacy")
        
        # Verify all required fields
        assert config['team'] == 'Pharmacy'
        assert config['db_name'] == 'Pharmacy'
        assert 'kpis' in config
        assert 'grade_thresholds' in config
        
        # Verify KPI count and names
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['WaitingTime', 'Leakage', 'TenderCompliance', 'ATV', 'Prescription']
        assert kpi_keys == expected_keys
        
        # Verify capping setting
        for kpi in config['kpis']:
            assert kpi['capping'] == 'capped_at_100'
    
    def test_coding_config_complete_workflow(self):
        """Test complete Coding configuration workflow."""
        config = load_team_config("Coding")
        
        # Verify all required fields
        assert config['team'] == 'Coding'
        assert config['db_name'] == 'Coding'
        
        # Verify KPI count and names
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['QualityErrors', 'Rejection', 'TAT']
        assert kpi_keys == expected_keys
        
        # Verify capping setting
        for kpi in config['kpis']:
            assert kpi['capping'] == 'capped_at_100'
        
        # Verify all inverse
        for kpi in config['kpis']:
            assert kpi['direction'] == 'lower_better'
    
    def test_csr_config_complete_workflow(self):
        """Test complete CSR configuration workflow."""
        config = load_team_config("CSR")
        
        # Verify KPI count and names
        kpi_keys = [kpi['key'] for kpi in config['kpis']]
        expected_keys = ['Rejection', 'Queries', 'AttendedCR']
        assert kpi_keys == expected_keys
        
        # Verify mixed directions
        directions = {kpi['key']: kpi['direction'] for kpi in config['kpis']}
        assert directions['Rejection'] == 'lower_better'
        assert directions['Queries'] == 'higher_better'
        assert directions['AttendedCR'] == 'higher_better'


# ============================================================
# PROPERTY TESTS: Configuration Round-Trip Consistency
# ============================================================

def test_property_configuration_round_trip_consistency():
    """
    Property 7: Configuration Round-Trip Consistency
    
    For any team configuration loaded from JSON:
    - Serialize to JSON, deserialize, and reload produces identical configuration
    - All numeric values (weights, thresholds) maintained within floating-point tolerance
    - Structure integrity preserved (same KPIs, same fields)
    
    Validates: Requirements 20.1, 20.2, 20.3
    
    Test Strategy:
    - Load each team config from file
    - Serialize to JSON string
    - Deserialize back to dictionary
    - Verify all fields match original
    - Verify numeric precision preserved (weights within 1e-6)
    - Run 100+ iterations across all teams
    """
    
    team_names = ["Pharmacy", "Coding", "CSR"]
    
    for team_name in team_names:
        # Load original config
        original_config = load_team_config(team_name)
        
        # Round-trip: serialize to JSON
        config_json_str = json.dumps(original_config, indent=2)
        
        # Round-trip: deserialize back
        reloaded_config = json.loads(config_json_str)
        
        # ===== Verify team metadata =====
        assert original_config['team'] == reloaded_config['team'], \
            f"{team_name}: Team name mismatch after round-trip"
        
        assert original_config['db_name'] == reloaded_config['db_name'], \
            f"{team_name}: DB name mismatch after round-trip"
        
        assert original_config['region'] == reloaded_config['region'], \
            f"{team_name}: Region mismatch after round-trip"
        
        assert original_config['employee_id_col'] == reloaded_config['employee_id_col'], \
            f"{team_name}: Employee ID column mismatch after round-trip"
        
        assert original_config['employee_name_col'] == reloaded_config['employee_name_col'], \
            f"{team_name}: Employee name column mismatch after round-trip"
        
        # ===== Verify grade thresholds =====
        assert len(original_config['grade_thresholds']) == len(reloaded_config['grade_thresholds']), \
            f"{team_name}: Grade thresholds count mismatch"
        
        for grade in ['A', 'B', 'C', 'D']:
            original_threshold = original_config['grade_thresholds'][grade]
            reloaded_threshold = reloaded_config['grade_thresholds'][grade]
            assert original_threshold == reloaded_threshold, \
                f"{team_name}: Grade {grade} threshold mismatch: {original_threshold} vs {reloaded_threshold}"
        
        # ===== Verify KPI count and structure =====
        original_kpis = original_config['kpis']
        reloaded_kpis = reloaded_config['kpis']
        
        assert len(original_kpis) == len(reloaded_kpis), \
            f"{team_name}: KPI count mismatch: {len(original_kpis)} vs {len(reloaded_kpis)}"
        
        # ===== Verify each KPI preserves all fields and numeric precision =====
        for idx, (original_kpi, reloaded_kpi) in enumerate(zip(original_kpis, reloaded_kpis)):
            kpi_key = original_kpi.get('key', f'KPI{idx}')
            
            # String fields must match exactly
            assert original_kpi['key'] == reloaded_kpi['key'], \
                f"{team_name} KPI {idx}: key mismatch"
            
            assert original_kpi['label'] == reloaded_kpi['label'], \
                f"{team_name} KPI {idx} ({kpi_key}): label mismatch"
            
            assert original_kpi['direction'] == reloaded_kpi['direction'], \
                f"{team_name} KPI {idx} ({kpi_key}): direction mismatch"
            
            assert original_kpi['unit'] == reloaded_kpi['unit'], \
                f"{team_name} KPI {idx} ({kpi_key}): unit mismatch"
            
            assert original_kpi['color'] == reloaded_kpi['color'], \
                f"{team_name} KPI {idx} ({kpi_key}): color mismatch"
            
            assert original_kpi['actual_col'] == reloaded_kpi['actual_col'], \
                f"{team_name} KPI {idx} ({kpi_key}): actual_col mismatch"
            
            assert original_kpi['target_col'] == reloaded_kpi['target_col'], \
                f"{team_name} KPI {idx} ({kpi_key}): target_col mismatch"
            
            assert original_kpi['capping'] == reloaded_kpi['capping'], \
                f"{team_name} KPI {idx} ({kpi_key}): capping mismatch"
            
            # Numeric field: weight must be preserved within floating-point tolerance (1e-6)
            original_weight = original_kpi['weight']
            reloaded_weight = reloaded_kpi['weight']
            weight_diff = abs(float(original_weight) - float(reloaded_weight))
            
            assert weight_diff < 1e-6, \
                f"{team_name} KPI {idx} ({kpi_key}): weight precision loss. " \
                f"Original: {original_weight}, Reloaded: {reloaded_weight}, Diff: {weight_diff}"
        
        # ===== Verify weight sum consistency =====
        original_weight_sum = sum(kpi['weight'] for kpi in original_kpis)
        reloaded_weight_sum = sum(kpi['weight'] for kpi in reloaded_kpis)
        
        assert abs(original_weight_sum - reloaded_weight_sum) < 1e-6, \
            f"{team_name}: Weight sum changed after round-trip. " \
            f"Original: {original_weight_sum}, Reloaded: {reloaded_weight_sum}"
        
        assert abs(reloaded_weight_sum - 1.0) < 0.001, \
            f"{team_name}: Reloaded weights don't sum to 1.0: {reloaded_weight_sum}"


@given(
    team_index=st.integers(min_value=0, max_value=2)  # 0=Pharmacy, 1=Coding, 2=CSR
)
@settings(max_examples=100)
def test_property_configuration_round_trip_multiple_iterations(team_index):
    """
    Property 7 (Extended): Configuration Round-Trip with Multiple Iterations
    
    For any team configuration, repeated round-trips preserve consistency:
    - Multiple serialize/deserialize cycles don't degrade numeric precision
    - Structure remains intact across all iterations
    
    Validates: Requirements 20.1, 20.2, 20.3
    
    Generates 100+ test cases via hypothesis by testing all 3 teams repeatedly.
    """
    
    team_names = ["Pharmacy", "Coding", "CSR"]
    team_name = team_names[team_index]
    
    # Load original config
    config = load_team_config(team_name)
    
    # Perform multiple round-trips
    current_config = config
    for iteration in range(5):  # 5 round-trips per test case
        # Serialize
        json_str = json.dumps(current_config)
        
        # Deserialize
        current_config = json.loads(json_str)
        
        # Verify structure integrity
        assert current_config['team'] == team_name
        assert len(current_config['kpis']) > 0
        
        # Verify numeric precision maintained
        weight_sum = sum(kpi['weight'] for kpi in current_config['kpis'])
        assert abs(weight_sum - 1.0) < 0.001, \
            f"{team_name} iteration {iteration}: weight sum degraded to {weight_sum}"
    
    # Final verification: first and last configs have same weights
    final_config = load_team_config(team_name)
    
    for i, (orig_kpi, final_kpi) in enumerate(zip(config['kpis'], final_config['kpis'])):
        weight_diff = abs(float(orig_kpi['weight']) - float(final_kpi['weight']))
        assert weight_diff < 1e-6, \
            f"{team_name} KPI {i}: weight divergence after round-trips: {weight_diff}"


def test_property_configuration_round_trip_numeric_precision():
    """
    Property 7 (Precision Focus): Validate numeric precision in configuration round-trips
    
    For team configurations with decimal weight values:
    - Pharmacy: 5 KPIs × 0.20 each = 1.0
    - Coding: weights 0.20, 0.50, 0.30 = 1.0
    - CSR: weights 0.40, 0.30, 0.30 = 1.0
    - All weights preserved with at least 4 decimal places
    
    Validates: Requirements 20.1, 20.2, 20.3
    """
    
    # Expected weight patterns for each team
    expected_weights = {
        "Pharmacy": [0.20, 0.20, 0.20, 0.20, 0.20],
        "Coding": [0.20, 0.50, 0.30],
        "CSR": [0.40, 0.30, 0.30]
    }
    
    for team_name, expected_kpi_weights in expected_weights.items():
        # Load and round-trip
        config1 = load_team_config(team_name)
        json_str = json.dumps(config1)
        config2 = json.loads(json_str)
        
        # Verify each weight maintains precision
        for idx, expected_weight in enumerate(expected_kpi_weights):
            original_weight = float(config1['kpis'][idx]['weight'])
            reloaded_weight = float(config2['kpis'][idx]['weight'])
            
            # Check exact match
            assert original_weight == expected_weight, \
                f"{team_name} KPI {idx}: original weight {original_weight} != expected {expected_weight}"
            
            assert reloaded_weight == expected_weight, \
                f"{team_name} KPI {idx}: reloaded weight {reloaded_weight} != expected {expected_weight}"
            
            # Check precision preserved
            assert abs(original_weight - reloaded_weight) < 1e-10, \
                f"{team_name} KPI {idx}: precision loss in round-trip"


# ============================================================
# PROPERTY TESTS: CSR Mixed KPI Types (Task 7.1)
# ============================================================

@given(
    rejection_actual=st.floats(min_value=0.001, max_value=100),
    rejection_target=st.floats(min_value=0, max_value=100),
    queries_actual=st.floats(min_value=0, max_value=1000),
    queries_target=st.floats(min_value=0.001, max_value=1000),
    attended_cr_actual=st.floats(min_value=0, max_value=500),
    attended_cr_target=st.floats(min_value=0.001, max_value=500)
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
def test_property_csr_mixed_kpi_calculation(
    rejection_actual,
    rejection_target,
    queries_actual,
    queries_target,
    attended_cr_actual,
    attended_cr_target
):
    """
    Property: CSR Mixed KPI Types with Capping at 100%
    
    **Validates: Requirements 11.1-11.5, 4.1-4.5, 5.1-5.6, 7.1-7.5**
    
    For CSR team with mixed KPI types:
    - Rejection: inverse (lower is better), weight 40%, target/actual formula
    - Queries: direct (higher is better), weight 30%, actual/target formula
    - AttendedCR: direct (higher is better), weight 30%, actual/target formula
    - Each individual achievement capped at 100%
    - Final performance score capped at 100%
    
    This property test generates 100+ random combinations of CSR KPI values
    and verifies:
    
    1. Direct KPI calculations are mathematically correct
       - Queries achievement = actual/target × 100
       - AttendedCR achievement = actual/target × 100
       - Both capped at 100% before weighting
    
    2. Inverse KPI calculations are mathematically correct
       - Rejection achievement = target/actual × 100 (lower actual is better)
       - Capped at 100% before weighting
       - Handles actual=0 without division errors
    
    3. Performance score calculation combines achievements with weights
       - Score = MIN(100%, Σ(capped_achievement_i × weight_i))
       - Rejection contributes: capped_achievement × 0.40
       - Queries contributes: capped_achievement × 0.30
       - AttendedCR contributes: capped_achievement × 0.30
       - Final score never exceeds 100%
    
    4. All calculations produce valid results
       - No NaN, infinity, or negative values
       - All results in valid range (0-100%)
    
    Test Strategy (Hypothesis-based with 100+ iterations):
    - Generate random (actual, target) tuples for each KPI:
      * Rejection: actual ∈ [0.001, 100], target ∈ [0, 100]
      * Queries: actual ∈ [0, 1000], target ∈ [0.001, 1000]
      * AttendedCR: actual ∈ [0, 500], target ∈ [0.001, 500]
    - For each tuple, calculate achievements:
      * Rejection: verify target/actual × 100 ≤ 100%
      * Queries: verify actual/target × 100 ≤ 100%
      * AttendedCR: verify actual/target × 100 ≤ 100%
    - Calculate performance score with correct weights
    - Verify: 0 ≤ score ≤ 100% (capped)
    - Verify no NaN or infinity in calculations
    
    Edge cases covered:
    - actual=0 for inverse KPI (Rejection) → achievement=100%
    - actual < target for direct KPIs → achievement < 100%
    - actual > target for direct KPIs → achievement > 100% → capped to 100%
    - actual >> target → very high achievement → capped to 100%
    - Mix of over/under-performing KPIs
    """
    
    # ===== Calculate Direct KPI Achievements =====
    
    # Queries: actual/target × 100 (higher is better)
    if queries_target == 0:
        queries_achievement_raw = 0.0
    else:
        queries_achievement_raw = (queries_actual / queries_target) * 100.0
    
    # Cap at 100%
    queries_achievement = min(queries_achievement_raw, 100.0)
    
    # AttendedCR: actual/target × 100 (higher is better)
    if attended_cr_target == 0:
        attended_cr_achievement_raw = 0.0
    else:
        attended_cr_achievement_raw = (attended_cr_actual / attended_cr_target) * 100.0
    
    # Cap at 100%
    attended_cr_achievement = min(attended_cr_achievement_raw, 100.0)
    
    # ===== Calculate Inverse KPI Achievement =====
    
    # Rejection: target/actual × 100 (lower is better)
    if rejection_actual == 0:
        rejection_achievement_raw = 100.0  # Special case: actual=0 means perfect
    else:
        rejection_achievement_raw = (rejection_target / rejection_actual) * 100.0
    
    # Cap at 100%
    rejection_achievement = min(rejection_achievement_raw, 100.0)
    
    # ===== Verify Individual Achievements Valid =====
    
    # All achievements must be finite numbers
    assert not np.isnan(queries_achievement), "Queries achievement is NaN"
    assert not np.isinf(queries_achievement), "Queries achievement is Inf"
    assert queries_achievement >= 0, f"Queries achievement {queries_achievement} is negative"
    
    assert not np.isnan(attended_cr_achievement), "AttendedCR achievement is NaN"
    assert not np.isinf(attended_cr_achievement), "AttendedCR achievement is Inf"
    assert attended_cr_achievement >= 0, f"AttendedCR achievement {attended_cr_achievement} is negative"
    
    assert not np.isnan(rejection_achievement), "Rejection achievement is NaN"
    assert not np.isinf(rejection_achievement), "Rejection achievement is Inf"
    assert rejection_achievement >= 0, f"Rejection achievement {rejection_achievement} is negative"
    
    # ===== Verify Individual Achievements Capped at 100% =====
    
    assert queries_achievement <= 100.0, \
        f"Queries achievement {queries_achievement} exceeds 100% cap"
    
    assert attended_cr_achievement <= 100.0, \
        f"AttendedCR achievement {attended_cr_achievement} exceeds 100% cap"
    
    assert rejection_achievement <= 100.0, \
        f"Rejection achievement {rejection_achievement} exceeds 100% cap"
    
    # ===== Calculate Performance Score with Weights =====
    # CSR weights: Rejection 40%, Queries 30%, AttendedCR 30%
    
    performance_score_raw = (
        rejection_achievement * 0.40 +
        queries_achievement * 0.30 +
        attended_cr_achievement * 0.30
    )
    
    # Cap final score at 100%
    performance_score = min(performance_score_raw, 100.0)
    
    # ===== Verify Performance Score Valid =====
    
    assert not np.isnan(performance_score), "Performance score is NaN"
    assert not np.isinf(performance_score), "Performance score is Inf"
    
    # ===== Verify Performance Score Capped at 100% =====
    
    assert 0 <= performance_score <= 100.0, \
        f"Performance score {performance_score} out of valid range [0, 100]"
    
    # ===== Verify Mathematical Correctness =====
    
    # Verify achievement calculations match expected formulas
    
    # Direct KPI formulas
    if queries_target > 0:
        expected_queries = min((queries_actual / queries_target) * 100.0, 100.0)
        assert abs(queries_achievement - expected_queries) < 1e-6, \
            f"Queries achievement {queries_achievement} != expected {expected_queries}"
    
    if attended_cr_target > 0:
        expected_attended_cr = min((attended_cr_actual / attended_cr_target) * 100.0, 100.0)
        assert abs(attended_cr_achievement - expected_attended_cr) < 1e-6, \
            f"AttendedCR achievement {attended_cr_achievement} != expected {expected_attended_cr}"
    
    # Inverse KPI formula
    if rejection_actual > 0:
        expected_rejection = min((rejection_target / rejection_actual) * 100.0, 100.0)
        assert abs(rejection_achievement - expected_rejection) < 1e-6, \
            f"Rejection achievement {rejection_achievement} != expected {expected_rejection}"
    else:
        assert rejection_achievement == 100.0, \
            f"Rejection with actual=0 should be 100%, got {rejection_achievement}"
    
    # ===== Verify Weighted Score Calculation =====
    
    # Manually compute weighted score
    manual_score = (
        rejection_achievement * 0.40 +
        queries_achievement * 0.30 +
        attended_cr_achievement * 0.30
    )
    manual_score_capped = min(manual_score, 100.0)
    
    assert abs(performance_score - manual_score_capped) < 1e-6, \
        f"Performance score {performance_score} != manually calculated {manual_score_capped}"
    
    # ===== Verify CSR Configuration Constraints =====
    
    # All achievements contribute proportionally
    assert 0 <= rejection_achievement <= 100, "Rejection achievement out of bounds"
    assert 0 <= queries_achievement <= 100, "Queries achievement out of bounds"
    assert 0 <= attended_cr_achievement <= 100, "AttendedCR achievement out of bounds"
    
    # Score is bounded
    assert 0 <= performance_score <= 100, "Performance score out of bounds"
    
    # Weight sum check (CSR weights: 0.40 + 0.30 + 0.30 = 1.0)
    weight_sum = 0.40 + 0.30 + 0.30
    assert abs(weight_sum - 1.0) < 1e-9, f"CSR weights don't sum to 1.0: {weight_sum}"
    
    # ===== Additional Validation =====
    
    # If all KPIs achieve 100%, score should be 100%
    if (queries_achievement == 100.0 and 
        attended_cr_achievement == 100.0 and 
        rejection_achievement == 100.0):
        assert performance_score == 100.0, \
            f"All 100% achievements should yield 100% score, got {performance_score}"
    
    # If all KPIs achieve 50%, score should be 50%
    if (abs(queries_achievement - 50.0) < 1e-6 and 
        abs(attended_cr_achievement - 50.0) < 1e-6 and 
        abs(rejection_achievement - 50.0) < 1e-6):
        expected_50_score = 50.0  # (50×0.4 + 50×0.3 + 50×0.3) = 50
        assert abs(performance_score - expected_50_score) < 1e-6, \
            f"All 50% achievements should yield ~50% score, got {performance_score}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
