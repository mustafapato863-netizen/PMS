"""
Onboarding State Repository

Manages persistence of team onboarding state to database.
Allows recovery of onboarding process after system restart.
"""

from sqlalchemy.orm import Session
from repositories.base_repository import BaseRepository
from models.models import OnboardingState
from datetime import datetime
import logging
import uuid

logger = logging.getLogger(__name__)


class OnboardingRepository(BaseRepository[OnboardingState]):
    """Repository for OnboardingState model"""
    
    def get_by_team(self, team_id) -> OnboardingState:
        """Get onboarding state for a specific team"""
        try:
            return self.db.query(OnboardingState).filter(
                OnboardingState.team_id == team_id
            ).first()
        except Exception as e:
            logger.error(f"Failed to get onboarding state for team {team_id}: {str(e)}")
            raise
    
    def get_or_create(self, team_id) -> OnboardingState:
        """Get existing onboarding state or create new one"""
        try:
            state = self.get_by_team(team_id)
            if not state:
                logger.info(f"Creating new onboarding state for team {team_id}")
                state = OnboardingState(
                    id=uuid.uuid4(),
                    team_id=team_id,
                    current_step=0,
                    status="pending",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.db.add(state)
                self.db.commit()
                self.db.refresh(state)
                logger.info(f"Onboarding state created: {state.id}")
            return state
        except Exception as e:
            logger.error(f"Failed to get or create onboarding state: {str(e)}")
            raise
    
    def update_step(self, team_id, step: int, status: str = None) -> OnboardingState:
        """Update current step and optionally status"""
        try:
            state = self.get_by_team(team_id)
            if state:
                state.current_step = step
                if status:
                    state.status = status
                state.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(state)
                logger.info(f"Updated onboarding state for team {team_id}: step={step}, status={status or state.status}")
            return state
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update onboarding step: {str(e)}")
            raise
    
    def mark_started(self, team_id) -> OnboardingState:
        """Mark onboarding as started"""
        try:
            state = self.get_by_team(team_id)
            if state:
                state.status = "in_progress"
                state.started_at = datetime.utcnow()
                state.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(state)
                logger.info(f"Marked onboarding as started for team {team_id}")
            return state
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark onboarding as started: {str(e)}")
            raise
    
    def mark_completed(self, team_id) -> OnboardingState:
        """Mark onboarding as completed"""
        try:
            state = self.get_by_team(team_id)
            if state:
                state.status = "completed"
                state.completed_at = datetime.utcnow()
                state.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(state)
                logger.info(f"Marked onboarding as completed for team {team_id}")
            return state
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark onboarding as completed: {str(e)}")
            raise
    
    def mark_failed(self, team_id, error_message: str) -> OnboardingState:
        """Mark onboarding as failed with error message"""
        try:
            state = self.get_by_team(team_id)
            if state:
                state.status = "failed"
                state.last_error = error_message
                state.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(state)
                logger.error(f"Marked onboarding as failed for team {team_id}: {error_message}")
            return state
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark onboarding as failed: {str(e)}")
            raise
    
    def reset(self, team_id) -> OnboardingState:
        """Reset onboarding state to pending"""
        try:
            state = self.get_by_team(team_id)
            if state:
                state.current_step = 0
                state.status = "pending"
                state.started_at = None
                state.completed_at = None
                state.last_error = None
                state.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(state)
                logger.info(f"Reset onboarding state for team {team_id}")
            return state
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to reset onboarding state: {str(e)}")
            raise
    
    def get_pending_teams(self) -> list:
        """Get all teams with pending onboarding"""
        try:
            return self.db.query(OnboardingState).filter(
                OnboardingState.status == "pending"
            ).all()
        except Exception as e:
            logger.error(f"Failed to get pending teams: {str(e)}")
            raise
    
    def get_in_progress_teams(self) -> list:
        """Get all teams with onboarding in progress"""
        try:
            return self.db.query(OnboardingState).filter(
                OnboardingState.status == "in_progress"
            ).all()
        except Exception as e:
            logger.error(f"Failed to get in-progress teams: {str(e)}")
            raise
    
    def get_failed_teams(self) -> list:
        """Get all teams with failed onboarding"""
        try:
            return self.db.query(OnboardingState).filter(
                OnboardingState.status == "failed"
            ).all()
        except Exception as e:
            logger.error(f"Failed to get failed teams: {str(e)}")
            raise
