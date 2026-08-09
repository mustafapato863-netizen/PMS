"""
Standard Column Mappings
Provides common column name mappings used across teams.
Reduces duplication and ensures consistency.
"""

import math
from typing import Dict

# Common Excel column name variations across different teams
EMPLOYEE_COLUMN_VARIATIONS = [
    'Employee',
    'Employee Name',
    'Staff Name',
    'Name',
    'Staff',
    'Team Member',
]

DATE_COLUMN_VARIATIONS = [
    'Date',
    'Performance Date',
    'Record Date',
    'Report Date',
    'Month',
]

PERFORMANCE_COLUMN_VARIATIONS = [
    'Performance',
    'Performance Score',
    'Total Score',
    'KPI Score',
    'Score',
    'Performance %',
]

GRADE_COLUMN_VARIATIONS = [
    'Grade',
    'Performance Grade',
    'Rating',
    'Classification',
]

ATTENDANCE_COLUMN_VARIATIONS = [
    'Attendance',
    'Attendance %',
    'Attendance Score',
    'Attendance Rate',
]

PRODUCTIVITY_COLUMN_VARIATIONS = [
    'Productivity',
    'Productivity %',
    'Productivity Score',
]

QUALITY_COLUMN_VARIATIONS = [
    'Quality',
    'Quality %',
    'Quality Score',
    'Quality Rate',
]

BOOKINGS_COLUMN_VARIATIONS = [
    'Bookings',
    'Booking Count',
    'Total Bookings',
    'Approved Bookings',
]

# Mapping dictionaries (from variation → standard name)
STANDARD_MAPPINGS = {
    'employee': {col: 'Employee' for col in EMPLOYEE_COLUMN_VARIATIONS},
    'date': {col: 'Date' for col in DATE_COLUMN_VARIATIONS},
    'performance': {col: 'Performance' for col in PERFORMANCE_COLUMN_VARIATIONS},
    'grade': {col: 'Grade' for col in GRADE_COLUMN_VARIATIONS},
    'attendance': {col: 'Attendance' for col in ATTENDANCE_COLUMN_VARIATIONS},
    'productivity': {col: 'Productivity' for col in PRODUCTIVITY_COLUMN_VARIATIONS},
    'quality': {col: 'Quality' for col in QUALITY_COLUMN_VARIATIONS},
    'bookings': {col: 'Bookings' for col in BOOKINGS_COLUMN_VARIATIONS},
}

# Reverse mapping (find which category a column belongs to)
COLUMN_CATEGORY = {}
for category, mappings in STANDARD_MAPPINGS.items():
    for col in mappings.keys():
        COLUMN_CATEGORY[col.lower()] = category


def get_standard_mapping(column_name: str) -> str:
    """
    Get standard name for a column.
    
    Args:
        column_name: Column name (any variation)
        
    Returns:
        Standard name (or original if no mapping found)
    """
    # Check each category
    for category, mappings in STANDARD_MAPPINGS.items():
        # Case-insensitive check
        for variation, standard in mappings.items():
            if variation.lower() == column_name.lower():
                return standard
    
    # No mapping found, return original
    return column_name


def create_mapping_dict(columns: list) -> Dict[str, str]:
    """
    Create mapping dictionary for given columns.
    
    Args:
        columns: List of column names from Excel
        
    Returns:
        Dictionary mapping original names to standard names
    """
    mapping = {}
    for col in columns:
        standard = get_standard_mapping(col)
        if standard != col:
            mapping[col] = standard
    
    return mapping


def is_numeric_column(column_name: str) -> bool:
    """Check if column should be numeric (Performance, Attendance, etc.)."""
    numeric_keywords = [
        'performance', 'score', 'attendance', 'productivity',
        'quality', 'bookings', 'count', '%', 'rate',
    ]
    
    col_lower = column_name.lower()
    return any(keyword in col_lower for keyword in numeric_keywords)


def is_date_column(column_name: str) -> bool:
    """Check if column should be a date."""
    date_keywords = ['date', 'month', 'time', 'period']
    col_lower = column_name.lower()
    return any(keyword in col_lower for keyword in date_keywords)


# Grade thresholds (shared across teams)
GRADE_THRESHOLDS = {
    'A': 95,
    'B': 85,
    'C': 75,
    'D': 65,
    'E': 0,
}


def calculate_grade(score: float, thresholds: Dict[str, float] = None) -> str:
    """
    Calculate grade from performance score.
    
    Args:
        score: Performance score (0-100)
        
    Returns:
        Grade letter (A, B, C, D, F)
    """
    thresholds = thresholds or GRADE_THRESHOLDS
    if score >= thresholds['A']:
        return 'A'
    elif score >= thresholds['B']:
        return 'B'
    elif score >= thresholds['C']:
        return 'C'
    elif score >= thresholds['D']:
        return 'D'
    return 'E'


GLOBAL_ACHIEVEMENT_CAP_PERCENT = 100.0


def calculate_achievement(
    actual: float,
    target: float,
    is_inverse: bool = False,
    cap_at_100: bool = False,
) -> float:
    """Calculate direct or inverse KPI achievement on a 0-100 scale.

    ``cap_at_100`` remains in the signature for compatibility with existing
    cleaners, but the product rule is now global: no KPI achievement can exceed
    100% regardless of the legacy flag supplied by a caller.
    """
    def _safe_float(value) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    actual = _safe_float(actual)
    target = _safe_float(target)
    achievement = (target / actual * 100.0) if is_inverse and actual else (
        actual / target * 100.0 if not is_inverse and target else 100.0 if is_inverse else 0.0
    )
    return min(achievement, GLOBAL_ACHIEVEMENT_CAP_PERCENT)


# Data type conversions
def to_numeric(value) -> float:
    """Convert value to numeric, handling common formats."""
    if value is None or value == '':
        return None
    
    if isinstance(value, (int, float)):
        return float(value)
    
    # Convert string
    value_str = str(value).strip()
    
    # Remove percentage signs
    if '%' in value_str:
        value_str = value_str.replace('%', '').strip()
    
    try:
        return float(value_str)
    except ValueError:
        return None


def to_date(value) -> str:
    """Convert value to ISO date string."""
    if value is None or value == '':
        return None
    
    if isinstance(value, str):
        # Try to parse (very basic, can be enhanced)
        return value
    
    try:
        # Assume pandas datetime or similar
        return str(value.date()) if hasattr(value, 'date') else str(value)
    except Exception:
        return None
