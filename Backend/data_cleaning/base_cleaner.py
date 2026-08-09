"""
Base Data Cleaner Class
Provides generic interface for cleaning team performance data.
All team-specific cleaners inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
from datetime import datetime


class BaseDataCleaner(ABC):
    """
    Abstract base class for team data cleaners.
    
    Subclasses should override specific methods for team-specific logic.
    The framework provides common functionality.
    
    Usage:
        class InboundCleaner(BaseDataCleaner):
            team_name = 'Inbound'
            required_columns = ['Date', 'Employee', ...]
            
            def transform_custom_fields(self, row):
                # Team-specific logic
                return row
        
        cleaner = InboundCleaner()
        cleaned_data = cleaner.clean(df)
    """

    # Override in subclass
    team_name: str = "Unknown"
    required_columns: List[str] = []
    optional_columns: List[str] = []
    
    # Standard column mappings (can be overridden)
    column_mappings: Dict[str, str] = {}
    
    # Performance thresholds (customize per team)
    min_performance: float = 0.0
    max_performance: float = 100.0
    
    def __init__(self):
        """Initialize cleaner with team name and config."""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, Any] = {
            'total_rows': 0,
            'cleaned_rows': 0,
            'removed_rows': 0,
            'errors_count': 0,
        }

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Main cleaning pipeline.
        
        Args:
            df: Raw data from Excel
            
        Returns:
            Cleaned DataFrame
        """
        self.errors = []
        self.warnings = []
        self.stats['total_rows'] = len(df)

        try:
            # Step 1: Validate input
            self.validate_columns(df)
            
            # Step 2: Map columns
            df = self.map_columns(df)
            
            # Step 3: Clean each row
            df = df.apply(self.clean_row, axis=1)
            
            # Step 4: Remove nulls/blanks
            df = self.remove_blanks(df)
            
            # Step 5: Validate values
            df = self.validate_values(df)
            
            # Step 6: Transform fields
            df = self.transform_fields(df)
            
            # Step 7: Team-specific logic
            df = self.transform_custom_fields(df)
            
            # Step 8: Final cleanup
            df = self.final_cleanup(df)
            
            self.stats['cleaned_rows'] = len(df)
            self.stats['removed_rows'] = self.stats['total_rows'] - len(df)
            
            return df

        except Exception as e:
            self.add_error(f"Cleaning failed: {str(e)}")
            raise

    def validate_columns(self, df: pd.DataFrame) -> None:
        """
        Validate that required columns exist.
        
        Args:
            df: Input DataFrame
            
        Raises:
            ValueError: If required columns missing
        """
        missing = set(self.required_columns) - set(df.columns)
        if missing:
            msg = f"Missing required columns: {missing}"
            raise ValueError(msg)

    def map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Rename columns to standard names.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with renamed columns
        """
        if self.column_mappings:
            df = df.rename(columns=self.column_mappings)
        return df

    def clean_row(self, row: pd.Series) -> pd.Series:
        """
        Clean individual row (string trimming, type conversion, etc.).
        
        Args:
            row: Single row from DataFrame
            
        Returns:
            Cleaned row
        """
        # Strip whitespace from string columns
        for col in row.index:
            if isinstance(row[col], str):
                row[col] = row[col].strip()
                # Convert empty strings to None
                if row[col] == '':
                    row[col] = None
        
        return row

    def remove_blanks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove rows where required columns are null/blank.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with blanks removed
        """
        before = len(df)
        df = df.dropna(subset=self.required_columns, how='any')
        removed = before - len(df)
        
        if removed > 0:
            self.add_warning(f"Removed {removed} rows with missing required values")
        
        return df

    def validate_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate that values are in acceptable ranges.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with validated values
        """
        # Subclass can override for specific validation
        return df

    def transform_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transform common fields (dates, numbers, percentages).
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with transformed fields
        """
        # Subclass can override for field-specific transforms
        return df

    @abstractmethod
    def transform_custom_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Team-specific field transformation.
        MUST be overridden by subclass.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with custom transforms applied
        """
        raise NotImplementedError("Subclass must implement transform_custom_fields")

    def final_cleanup(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Final cleanup before returning.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Cleaned DataFrame ready for use
        """
        # Reset index
        df = df.reset_index(drop=True)
        
        # Ensure consistent data types
        df = self.ensure_data_types(df)
        
        return df

    def ensure_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure columns have correct data types.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with corrected data types
        """
        # Subclass can override for type-specific logic
        return df

    def add_error(self, message: str) -> None:
        """Add error message to log."""
        self.errors.append(message)
        self.stats['errors_count'] += 1

    def add_warning(self, message: str) -> None:
        """Add warning message to log."""
        self.warnings.append(message)

    def get_report(self) -> Dict[str, Any]:
        """
        Get cleaning report.
        
        Returns:
            Dictionary with stats, errors, warnings
        """
        return {
            'team': self.team_name,
            'timestamp': datetime.now().isoformat(),
            'stats': self.stats,
            'errors': self.errors,
            'warnings': self.warnings,
            'success': len(self.errors) == 0,
        }
