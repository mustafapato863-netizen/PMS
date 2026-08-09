from typing import Dict, List, Optional, Tuple
from models.schemas import CorrectiveAction
from repositories.base import CorrectiveActionsRepository

class LearningService:
    def __init__(self, actions_repo: CorrectiveActionsRepository):
        self.actions_repo = actions_repo

    def get_historical_recommendations(
        self, team: str, score: float, grade: str, root_cause: str, default_suggestion: str
    ) -> Tuple[str, Dict[str, float]]:
        """
        Analyzes corrective_actions.json to find similar employees.
        Returns:
          - primary_recommendation (str): Action with highest percentage (e.g. "PIP (70% historical manager preference)")
          - preferences (dict): Map of action to percentage
        """
        history = self.actions_repo.get_history()
        if not history:
            return f"{default_suggestion} (100% AI recommendation - no manager history yet)", {default_suggestion: 100.0}

        # Step 1: Match by Team, Grade, Root Cause, and Score +/- 10
        matches = [
            h for h in history
            if h.team == team
            and h.grade == grade
            and h.root_cause == root_cause
            and abs(h.score - score) <= 10.0
        ]

        # Step 2: Fallback to Team, Grade, Root Cause
        if not matches:
            matches = [
                h for h in history
                if h.team == team
                and h.grade == grade
                and h.root_cause == root_cause
            ]

        # Step 3: Fallback to Grade and Root Cause
        if not matches:
            matches = [
                h for h in history
                if h.grade == grade
                and h.root_cause == root_cause
            ]

        # Step 4: Fallback to Root Cause only
        if not matches:
            matches = [
                h for h in history
                if h.root_cause == root_cause
            ]

        if not matches:
            return f"{default_suggestion} (100% AI recommendation - no similar history)", {default_suggestion: 100.0}

        # Calculate percentages
        counts = {}
        for m in matches:
            action = m.manager_action
            counts[action] = counts.get(action, 0) + 1

        total = len(matches)
        preferences = {action: float(round((cnt / total) * 100, 1)) for action, cnt in counts.items()}
        
        # Sort preferences descending
        sorted_prefs = sorted(preferences.items(), key=lambda x: x[1], reverse=True)
        primary_action, primary_pct = sorted_prefs[0]

        primary_recommendation = f"{primary_action} ({primary_pct}% historical manager preference)"
        return primary_recommendation, preferences
