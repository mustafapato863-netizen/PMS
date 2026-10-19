"""Team references for team-level actions resolve to exactly one team.

The frontend sends the canonical route id of the team page (types.ts teamPath). Each
route id must reach the team row that stores its notes, and no reference may land on
Marketing (or any other row) by accident.
"""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, Team
from services.team_action_service import TeamActionService

# (name, db_name, display_name) for the team rows the dashboards read. Display names are the
# logical team names; the unique index on them mirrors the production table.
TEAM_ROWS = [
    ("inbound", "Inbound", "Inbound"),
    ("outbound", "Outbound", "Outbound"),
    ("pre_approvals_offshore", "Pre-Approvals IP Offshore", "Pre-Approvals IP Offshore"),
    ("coding", "Coding", "Coding"),
    ("csr", "CSR", "CSR"),
    ("sales", "Sales", "Sales"),
    ("pharmacy", "Pharmacy", "Pharmacy"),
    ("submission", "Submission", "Submission"),
    ("re_submission", "Re-Submission", "Re-Submission"),
    ("pre_approvals_op_dubai", "Pre-Approvals OP Dubai", "Pre-Approvals OP Dubai"),
    ("pre_approvals_op_final_shj_ajm", "Pre-Approvals OP Final SHJAJM", "Pre-Approvals OP Final SHJAJM"),
    ("pre_approvals_ip_final_dubai", "Pre-Approvals IP Final Dubai", "Pre-Approvals IP Final Dubai"),
    ("pre_approvals_ip_final_shj_ajm", "Pre-Approvals IP Final SHJAJM", "Pre-Approvals IP Final SHJAJM"),
    ("pre_approvals_ip_elective_dubai", "Pre-Approvals IP Elective Dubai", "Pre-Approvals IP Elective Dubai"),
    ("marketing", "Marketing", "Marketing"),
    ("rcm", "RCM", "RCM"),
    ("call_center", "Call Center", "Call Center"),
    ("pre_approvals_uae", "Pre-Approvals", "Pre-Approvals"),
]

# Every canonical route id teamPath can produce (types.ts TEAM_ID_MAP values), with the
# team row that stores its notes. Merged and parent views keep the stored-row
# behaviour described in TeamActionService._SLUG_ALIASES.
CANONICAL_ROUTE_IDS = {
    "rcm": "RCM",
    "call-center": "Call Center",
    "inbound": "Inbound",
    "outbound": "Outbound",
    "pre-approvals": "Pre-Approvals IP Offshore",
    "sales": "Sales",
    "coding": "Coding",
    "csr": "CSR",
    "pharmacy": "Pharmacy",
    "submission": "Submission",
    "re-submission": "Re-Submission",
    "pre-approvals-op-final": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final": "Pre-Approvals IP Final Dubai",
    "pre-approvals-uae": "Pre-Approvals",
    "pre-approvals-op-dubai": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final-dubai": "Pre-Approvals IP Final Dubai",
    "pre-approvals-ip-elective-dubai": "Pre-Approvals IP Elective Dubai",
    "pre-approvals-op-final-shj-ajm": "Pre-Approvals OP Dubai",
    "pre-approvals-ip-final-shj-ajm": "Pre-Approvals IP Final Dubai",
    "marketing": "Marketing",
}


def add_team(db, name: str, db_name: str, display: str, *, active: bool = True) -> None:
    db.add(Team(id=uuid.uuid4(), name=name, db_name=db_name, display_name=display, region="UAE", team_level="employee", is_active=active))


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[Team.__table__])
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    for name, db_name, display in TEAM_ROWS:
        add_team(session, name, db_name, display)
    session.commit()
    yield session
    session.close()


def resolved_display(db, reference: str) -> str:
    team = TeamActionService(db)._team(reference)
    return team.display_name


@pytest.mark.parametrize(("route_id", "expected"), sorted(CANONICAL_ROUTE_IDS.items()))
def test_every_canonical_route_id_resolves_to_its_team(db, route_id, expected):
    assert resolved_display(db, route_id) == expected


def test_no_canonical_route_id_lands_on_marketing_except_marketing(db):
    landed = {route_id: resolved_display(db, route_id) for route_id in CANONICAL_ROUTE_IDS}
    assert [route_id for route_id, team in landed.items() if team == "Marketing"] == ["marketing"]


def test_legacy_display_and_db_names_resolve_to_their_team(db):
    assert resolved_display(db, "Inbound") == "Inbound"
    assert resolved_display(db, "Pre-Approvals IP Offshore") == "Pre-Approvals IP Offshore"
    assert resolved_display(db, "pre-approvals-ip-offshore") == "Pre-Approvals IP Offshore"
    assert resolved_display(db, "Pre-Approvals IP Elective") == "Pre-Approvals IP Elective Dubai"


@pytest.mark.parametrize("reference", ["pre-approvals-ip-offshor", "not-a-team", "randd-team", ""])
def test_an_unknown_reference_raises_team_not_found(db, reference):
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team(reference)


def test_an_alias_never_falls_back_to_another_team(db):
    # Elective is an alias to a row that is missing here; the lookup must not pick any other team.
    db.query(Team).filter(Team.display_name == "Pre-Approvals IP Elective Dubai").delete()
    db.commit()
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team("pre-approvals-ip-elective-dubai")


def test_an_inactive_parent_still_resolves_and_source_teams_do_not(db):
    db.query(Team).filter(Team.display_name == "Call Center").update({"is_active": False})
    db.query(Team).filter(Team.display_name == "Inbound").update({"is_active": False})
    db.commit()
    assert resolved_display(db, "call-center") == "Call Center"
    with pytest.raises(ValueError, match="Team not found"):
        TeamActionService(db)._team("inbound")


def test_a_reference_matching_two_teams_raises_instead_of_picking_one(db):
    # Two rows carry the name "foo" (case-insensitively), so the reference is not unique.
    add_team(db, "foo", "Bar Team", "Bar Team Logical")
    add_team(db, "Foo", "Baz Team", "Baz Team Logical")
    db.commit()
    with pytest.raises(ValueError, match="more than one team"):
        TeamActionService(db)._team("Foo")
