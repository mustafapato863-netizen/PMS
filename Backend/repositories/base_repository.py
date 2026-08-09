from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """Generic CRUD repository for all models"""
    
    def __init__(self, db: Session, model: type):
        self.db = db
        self.model = model
    
    def create(self, obj_in: dict) -> Optional[T]:
        """Create new record"""
        try:
            db_obj = self.model(**obj_in)
            self.db.add(db_obj)
            self.db.commit()
            self.db.refresh(db_obj)
            logger.info(f"Created {self.model.__name__}: {db_obj.id if hasattr(db_obj, 'id') else 'N/A'}")
            return db_obj
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"Failed to create {self.model.__name__}: {str(e)}")
            raise Exception(f"Failed to create {self.model.__name__}: {str(e)}")
    
    def get_by_id(self, id: any, include_deleted: bool = False) -> Optional[T]:
        """Get record by ID"""
        try:
            if isinstance(id, str):
                import uuid
                try:
                    id = uuid.UUID(id)
                except ValueError:
                    pass
            query = self.db.query(self.model).filter(self.model.id == id)
            if not include_deleted and hasattr(self.model, 'is_active'):
                query = query.filter(self.model.is_active == True)
            return query.first()
        except Exception as e:
            logger.error(f"Failed to fetch {self.model.__name__} by ID: {str(e)}")
            raise
    
    def get_all(self, skip: int = 0, limit: int = 100, include_deleted: bool = False) -> List[T]:
        """Get all records with pagination"""
        try:
            query = self.db.query(self.model)
            if not include_deleted and hasattr(self.model, 'is_active'):
                query = query.filter(self.model.is_active == True)
            return query.offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Failed to fetch all {self.model.__name__}: {str(e)}")
            raise
    
    def update(self, id: any, obj_in: dict) -> Optional[T]:
        """Update record"""
        try:
            db_obj = self.get_by_id(id, include_deleted=True)
            if db_obj:
                for key, value in obj_in.items():
                    setattr(db_obj, key, value)
                self.db.commit()
                self.db.refresh(db_obj)
                logger.info(f"Updated {self.model.__name__}: {id}")
            return db_obj
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update {self.model.__name__}: {str(e)}")
            raise
    
    def delete(self, id: any) -> bool:
        """Hard delete record"""
        try:
            db_obj = self.get_by_id(id, include_deleted=True)
            if db_obj:
                self.db.delete(db_obj)
                self.db.commit()
                logger.info(f"Deleted {self.model.__name__}: {id}")
                return True
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to delete {self.model.__name__}: {str(e)}")
            raise
    
    def count(self, include_deleted: bool = False) -> int:
        """Count all records"""
        try:
            query = self.db.query(self.model)
            if not include_deleted and hasattr(self.model, 'is_active'):
                query = query.filter(self.model.is_active == True)
            return query.count()
        except Exception as e:
            logger.error(f"Failed to count {self.model.__name__}: {str(e)}")
            raise
