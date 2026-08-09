"""
Data Cleaner Factory
Dynamically loads and provides access to team-specific cleaners.
Supports both functional cleaners (process_* functions) and class-based cleaners.
"""

import sys
import os
from typing import Optional, Dict, Type, Callable
from importlib import import_module
from data_cleaning.base_cleaner import BaseDataCleaner


class CleanerFactory:
    """
    Factory for creating team-specific data cleaners.
    
    Supports:
    1. Class-based cleaners inheriting from BaseDataCleaner
    2. Functional cleaners with process_* functions
    
    Usage:
        # Using factory
        cleaner = CleanerFactory.get_cleaner('inbound')
        cleaned_data = cleaner.clean(df)
        
        # Or get process function directly
        process_func = CleanerFactory.get_process_function('pharmacy')
        result = process_func(file_path)
    """

    _cache: Dict[str, Type[BaseDataCleaner]] = {}
    _process_functions: Dict[str, Callable] = {}
    _loaded = False

    @staticmethod
    def _normalize_team_name(team_name: str) -> str:
        normalized = team_name.lower().replace(' ', '_').replace('-', '_')
        return normalized.replace('preapprovals', 'pre_approvals')

    @classmethod
    def get_cleaner(cls, team_name: str) -> BaseDataCleaner:
        """
        Get cleaner instance for team.
        
        Args:
            team_name: Team name (e.g., 'inbound', 'pharmacy')
            
        Returns:
            Instantiated cleaner
            
        Raises:
            ValueError: If cleaner not found
        """
        team_name_lower = cls._normalize_team_name(team_name)
        
        # Load all cleaners if not loaded
        if not cls._loaded:
            cls._load_all_cleaners()
        
        # Look for cleaner (case-insensitive)
        cleaner_class = None
        for key, cls_ref in cls._cache.items():
            if cls._normalize_team_name(key) == team_name_lower:
                cleaner_class = cls_ref
                break
        
        if cleaner_class is None:
            raise ValueError(f"No cleaner found for team: {team_name}")
        
        return cleaner_class()

    @classmethod
    def get_process_function(cls, team_name: str) -> Callable:
        """
        Get process function for team (functional cleaners).
        
        Args:
            team_name: Team name (e.g., 'pharmacy', 'coding')
            
        Returns:
            Process function
            
        Raises:
            ValueError: If function not found
        """
        team_name_lower = cls._normalize_team_name(team_name)
        
        # Load all cleaners if not loaded
        if not cls._loaded:
            cls._load_all_cleaners()
        
        # Look for process function (case-insensitive)
        process_func = None
        for key, func in cls._process_functions.items():
            if cls._normalize_team_name(key) == team_name_lower:
                process_func = func
                break
        
        if process_func is None:
            raise ValueError(f"No process function found for team: {team_name}")
        
        return process_func

    @classmethod
    def _load_all_cleaners(cls) -> None:
        """
        Dynamically load all cleaners from Data_Cleaning_Teams directory.
        """
        # Get path to Data_Cleaning_Teams directory
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cleaners_dir = os.path.join(backend_dir, 'Data_Cleaning_Teams')
        
        if not os.path.exists(cleaners_dir):
            raise RuntimeError(f"Cleaners directory not found: {cleaners_dir}")
        
        # Add directory to path if not already there
        if cleaners_dir not in sys.path:
            sys.path.insert(0, cleaners_dir)
        
        # Expected cleaner modules with their class names and process function names
        cleaner_modules = {
            'inbound': {'class': 'InboundCleaner', 'function': 'process_inbound'},
            'outbound': {'class': 'OutboundCleaner', 'function': 'process_outbound'},
            'inbound_uae': {'class': 'InboundUAECleaner', 'function': 'process_inbound_uae'},
            'pre_approvals_offshore': {'class': 'PreApprovalsOffshoreCleaner', 'function': 'process_preapprovals_offshore'},
            'preapprovals_op_dubai': {'class': None, 'function': 'process_preapprovals_op_dubai'},
            'preapprovals_ip_final_dubai': {'class': None, 'function': 'process_preapprovals_ip_final_dubai'},
            'preapprovals_ip_elective_dubai': {'class': None, 'function': 'process_preapprovals_ip_elective_dubai'},
            'preapprovals_op_final_shjajm': {'class': None, 'function': 'process_preapprovals_op_final_shj_ajm'},
            'preapprovals_ip_final_shjajm': {'class': None, 'function': 'process_preapprovals_ip_final_shj_ajm'},
            'sales': {'class': 'SalesCleaner', 'function': 'process_sales'},
            'pharmacy': {'class': None, 'function': 'process_pharmacy'},
            'coding': {'class': None, 'function': 'process_coding'},
            'csr': {'class': None, 'function': 'process_csr'},
            'submission': {'class': None, 'function': 'process_submission'},
            're_submission': {'class': None, 'function': 'process_re_submission'},
        }
        
        for module_name, config in cleaner_modules.items():
            try:
                # Try to import module
                try:
                    module = import_module(module_name)
                except ImportError:
                    # Try from Data_Cleaning_Teams subdirectory
                    sys.path.insert(0, cleaners_dir)
                    module = __import__(module_name)
                
                # Load class-based cleaner if specified
                if config['class']:
                    class_name = config['class']
                    if hasattr(module, class_name):
                        cleaner_class = getattr(module, class_name)
                        
                        # Verify it's a BaseDataCleaner subclass
                        if issubclass(cleaner_class, BaseDataCleaner):
                            cls._cache[module_name] = cleaner_class
                            print(f"Loaded cleaner class: {module_name} → {class_name}")
                    else:
                        print(f"Warning: Class {class_name} not found in {module_name}")
                
                # Load process function if specified
                if config['function']:
                    func_name = config['function']
                    if hasattr(module, func_name):
                        process_func = getattr(module, func_name)
                        cls._process_functions[module_name] = process_func
                        print(f"Loaded process function: {module_name} → {func_name}")
                    else:
                        print(f"Warning: Function {func_name} not found in {module_name}")
            
            except ImportError as e:
                print(f"Warning: Could not load cleaner {module_name}: {e}")
            except Exception as e:
                print(f"Error loading cleaner {module_name}: {e}")
        
        cls._loaded = True

    @classmethod
    def get_available_teams(cls) -> list:
        """
        Get list of available team cleaners.
        
        Returns:
            List of team names
        """
        if not cls._loaded:
            cls._load_all_cleaners()
        
        teams = set()
        teams.update(cls._cache.keys())
        teams.update(cls._process_functions.keys())
        return list(teams)

    @classmethod
    def reset(cls) -> None:
        """Reset factory (useful for testing)."""
        cls._cache.clear()
        cls._process_functions.clear()
        cls._loaded = False

    @classmethod
    def register_cleaner(cls, team_name: str, cleaner_class: Type[BaseDataCleaner]) -> None:
        """
        Manually register a class-based cleaner (useful for testing or custom teams).
        
        Args:
            team_name: Team identifier
            cleaner_class: Cleaner class (must inherit from BaseDataCleaner)
        """
        if not issubclass(cleaner_class, BaseDataCleaner):
            raise TypeError(f"{cleaner_class} must inherit from BaseDataCleaner")
        
        cls._cache[team_name] = cleaner_class

    @classmethod
    def register_process_function(cls, team_name: str, process_func: Callable) -> None:
        """
        Manually register a functional cleaner (useful for testing or custom teams).
        
        Args:
            team_name: Team identifier
            process_func: Function that processes team data
        """
        if not callable(process_func):
            raise TypeError(f"{process_func} must be callable")
        
        cls._process_functions[team_name] = process_func


# Convenience functions
def get_cleaner(team_name: str) -> BaseDataCleaner:
    """
    Get cleaner for team (convenience function).
    
    Args:
        team_name: Team name
        
    Returns:
        Cleaner instance
    """
    return CleanerFactory.get_cleaner(team_name)


def get_process_function(team_name: str) -> Callable:
    """
    Get process function for team (convenience function).
    
    Args:
        team_name: Team name
        
    Returns:
        Process function
    """
    return CleanerFactory.get_process_function(team_name)


def get_available_teams() -> list:
    """Get list of available teams (convenience function)."""
    return CleanerFactory.get_available_teams()
