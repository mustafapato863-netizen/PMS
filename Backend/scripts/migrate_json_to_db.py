"""
Stage 6: Data Migration Script
Migrates team configurations from JSON files to database

Usage:
    python scripts/migrate_json_to_db.py [--dry-run]
    
Options:
    --dry-run : Preview changes without committing to database
"""

import sys
import json
import uuid
from pathlib import Path
from decimal import Decimal
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import SessionLocal
from models.models import Team, TeamKPIConfig
from sqlalchemy.exc import SQLAlchemyError

# ============================================================
# MIGRATION FUNCTIONS
# ============================================================

def migrate_teams(dry_run: bool = False):
    """Load teams from JSON configs to database"""
    
    db = SessionLocal()
    config_dir = Path(__file__).parent.parent / "config" / "teams"
    
    if not config_dir.exists():
        logger.error(f"Config directory not found: {config_dir}")
        return False
    
    logger.info(f"Starting team migration from: {config_dir}")
    logger.info(f"Dry run: {dry_run}\n")
    
    teams_migrated = 0
    kpis_migrated = 0
    errors = []
    
    try:
        # Process each JSON file
        for json_file in sorted(config_dir.glob("*.json")):
            try:
                logger.info(f"Processing: {json_file.name}")
                
                with open(json_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Extract team information
                team_name = config.get('team') or config.get('name') or json_file.stem
                db_name = config.get('db_name', team_name)
                region = config.get('region', 'UAE')
                
                logger.info(f"  Team: {team_name}, DB: {db_name}, Region: {region}")
                
                # Check if team already exists
                existing_team = db.query(Team).filter(Team.name == team_name).first()
                if existing_team:
                    logger.warning(f"  ⚠️  Team '{team_name}' already exists (ID: {existing_team.id}), skipping...")
                    continue
                
                # Create team object
                team = Team(
                    id=uuid.uuid4(),
                    name=team_name,
                    db_name=db_name,
                    region=region,
                    is_active=config.get('is_active', True),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                if not dry_run:
                    db.add(team)
                    db.flush()  # Flush to get ID without committing
                
                logger.info(f"  ✓ Team created: {team.id}")
                teams_migrated += 1
                
                # Process KPIs
                kpis = config.get('kpis', [])
                logger.info(f"  Processing {len(kpis)} KPIs...")
                
                for idx, kpi_config in enumerate(kpis, 1):
                    try:
                        kpi = TeamKPIConfig(
                            id=uuid.uuid4(),
                            team_id=team.id,
                            kpi_key=kpi_config.get('key', ''),
                            kpi_label=kpi_config.get('label', ''),
                            weight=Decimal(str(kpi_config.get('weight', 0))),
                            direction=kpi_config.get('direction', 'higher_better'),
                            unit=kpi_config.get('unit', '%'),
                            color=kpi_config.get('color', '#10B981'),
                            actual_col=kpi_config.get('actual_col', ''),
                            target_col=kpi_config.get('target_col', ''),
                            achievement_col=kpi_config.get('achievement_col', None),
                            volume_unit=kpi_config.get('volume_unit', None),
                            display_order=idx,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow()
                        )
                        
                        if not dry_run:
                            db.add(kpi)
                        
                        logger.info(f"    ✓ KPI {idx}: {kpi.kpi_label} (weight: {kpi.weight})")
                        kpis_migrated += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to create KPI {idx} for team {team_name}: {str(e)}"
                        logger.error(f"    ✗ {error_msg}")
                        errors.append(error_msg)
                
                logger.info(f"  Team '{team_name}' migration complete\n")
                
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON in {json_file.name}: {str(e)}"
                logger.error(f"  ✗ {error_msg}")
                errors.append(error_msg)
            except Exception as e:
                error_msg = f"Error processing {json_file.name}: {str(e)}"
                logger.error(f"  ✗ {error_msg}")
                errors.append(error_msg)
        
        # Commit if not dry run
        if not dry_run:
            try:
                db.commit()
                logger.info("\n" + "="*60)
                logger.info("✓ Successfully committed to database")
                logger.info("="*60)
            except SQLAlchemyError as e:
                db.rollback()
                error_msg = f"Failed to commit transaction: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                return False
        else:
            db.rollback()
            logger.info("\n" + "="*60)
            logger.info("DRY RUN COMPLETED - No changes committed")
            logger.info("="*60)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration failed: {str(e)}")
        return False
    finally:
        db.close()
    
    # Print summary
    logger.info("\nMIGRATION SUMMARY")
    logger.info("-" * 60)
    logger.info(f"Teams migrated: {teams_migrated}")
    logger.info(f"KPIs migrated: {kpis_migrated}")
    logger.info(f"Errors: {len(errors)}")
    
    if errors:
        logger.info("\nERRORS:")
        for error in errors:
            logger.info(f"  - {error}")
        return False
    
    return True


def verify_migration():
    """Verify migration was successful"""
    
    db = SessionLocal()
    
    try:
        logger.info("\nVERIFYING MIGRATION")
        logger.info("-" * 60)
        
        # Count teams
        teams = db.query(Team).all()
        logger.info(f"Teams in database: {len(teams)}")
        
        for team in teams:
            kpis = db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team.id).all()
            logger.info(f"  - {team.name} (ID: {team.id}): {len(kpis)} KPIs")
            
            for kpi in kpis:
                logger.info(f"      • {kpi.kpi_label} (weight: {kpi.weight})")
        
        # Count total KPIs
        total_kpis = db.query(TeamKPIConfig).count()
        logger.info(f"\nTotal KPIs in database: {total_kpis}")
        
        logger.info("\n✓ Verification complete")
        return True
        
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        return False
    finally:
        db.close()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate team configurations from JSON to database"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without committing'
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify migration after completion'
    )
    
    args = parser.parse_args()
    
    # Run migration
    success = migrate_teams(dry_run=args.dry_run)
    
    # Verify if requested
    if success and args.verify:
        verify_migration()
    
    sys.exit(0 if success else 1)
