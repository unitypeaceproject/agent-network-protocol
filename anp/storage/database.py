"""SQLite database connection and migration management."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from anp.config import settings


class Database:
    """SQLite database wrapper with connection pooling and migrations."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_path
        self._ensure_directory()
        self._run_migrations()
    
    def _ensure_directory(self):
        """Ensure the database directory exists."""
        db_file = Path(self.db_path)
        if db_file.parent.name and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Get a database cursor."""
        with self.connection() as conn:
            cursor = conn.cursor()
            yield cursor
    
    def _run_migrations(self):
        """Run all pending migrations."""
        with self.connection() as conn:
            # Create migrations tracking table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Get applied migrations
            cursor = conn.execute("SELECT name FROM _migrations")
            applied = {row["name"] for row in cursor.fetchall()}
            
            # Run initial migration if not applied
            if "001_initial" not in applied:
                self._run_initial_migration(conn)
                conn.execute("INSERT INTO _migrations (name) VALUES (?)", ("001_initial",))
    
    def _run_initial_migration(self, conn: sqlite3.Connection):
        """Create initial database schema."""
        conn.executescript(INITIAL_SCHEMA)


INITIAL_SCHEMA = """
-- Agent identities
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL DEFAULT '0.1',
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    service_orientation TEXT NOT NULL DEFAULT 'neutral',
    public_key TEXT,
    signature TEXT,
    avatar_url TEXT,
    website_url TEXT,
    capabilities_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_identities_name ON identities(name);
CREATE INDEX IF NOT EXISTS idx_identities_service_orientation ON identities(service_orientation);

-- Identity providers (links to Moltbook, ClaudeConnect, etc.)
CREATE TABLE IF NOT EXISTS identity_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    handle TEXT NOT NULL,
    profile_url TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    verified_at TIMESTAMP,
    fingerprint TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identity_id, type, handle)
);

CREATE INDEX IF NOT EXISTS idx_identity_providers_identity ON identity_providers(identity_id);
CREATE INDEX IF NOT EXISTS idx_identity_providers_type ON identity_providers(type);
CREATE INDEX IF NOT EXISTS idx_identity_providers_handle ON identity_providers(handle);

-- Skills
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'intermediate',
    description TEXT,
    proof_urls_json TEXT DEFAULT '[]',
    attestation_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identity_id, name)
);

CREATE INDEX IF NOT EXISTS idx_skills_identity ON skills(identity_id);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_level ON skills(level);

-- Skill attestations
CREATE TABLE IF NOT EXISTS skill_attestations (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    subject_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    attester_id TEXT NOT NULL,
    attestation_type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'intermediate',
    comment TEXT,
    proof_url TEXT,
    signature TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attestations_subject ON skill_attestations(subject_id);
CREATE INDEX IF NOT EXISTS idx_attestations_attester ON skill_attestations(attester_id);
CREATE INDEX IF NOT EXISTS idx_attestations_skill ON skill_attestations(skill_name);

-- Reputation scores
CREATE TABLE IF NOT EXISTS reputation_scores (
    agent_id TEXT PRIMARY KEY REFERENCES identities(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0.5,
    reliability REAL NOT NULL DEFAULT 0.5,
    quality REAL NOT NULL DEFAULT 0.5,
    helpfulness REAL NOT NULL DEFAULT 0.5,
    honesty REAL NOT NULL DEFAULT 0.5,
    total_work_completed INTEGER NOT NULL DEFAULT 0,
    total_work_abandoned INTEGER NOT NULL DEFAULT 0,
    total_attestations_given INTEGER NOT NULL DEFAULT 0,
    total_attestations_received INTEGER NOT NULL DEFAULT 0,
    first_activity_at TIMESTAMP,
    last_activity_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trust_tier TEXT NOT NULL DEFAULT 'unverified'
);

CREATE INDEX IF NOT EXISTS idx_reputation_score ON reputation_scores(score);
CREATE INDEX IF NOT EXISTS idx_reputation_tier ON reputation_scores(trust_tier);

-- Reputation events
CREATE TABLE IF NOT EXISTS reputation_events (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    delta REAL NOT NULL,
    related_agent_id TEXT,
    related_work_id TEXT,
    comment TEXT,
    proof_url TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reputation_events_agent ON reputation_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_reputation_events_type ON reputation_events(event_type);
CREATE INDEX IF NOT EXISTS idx_reputation_events_created ON reputation_events(created_at);

-- Work requests
CREATE TABLE IF NOT EXISTS work_requests (
    id TEXT PRIMARY KEY,
    requester_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    required_skills_json TEXT DEFAULT '[]',
    preferred_skills_json TEXT DEFAULT '[]',
    min_reputation REAL DEFAULT 0.0,
    max_applications INTEGER,
    bounty_amount REAL,
    bounty_currency TEXT,
    deadline TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'open',
    visibility TEXT NOT NULL DEFAULT 'public',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_work_requests_requester ON work_requests(requester_id);
CREATE INDEX IF NOT EXISTS idx_work_requests_status ON work_requests(status);
CREATE INDEX IF NOT EXISTS idx_work_requests_created ON work_requests(created_at);

-- Work applications
CREATE TABLE IF NOT EXISTS work_applications (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES work_requests(id) ON DELETE CASCADE,
    applicant_id TEXT NOT NULL REFERENCES identities(id) ON DELETE CASCADE,
    proposal TEXT,
    estimated_time TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(request_id, applicant_id)
);

CREATE INDEX IF NOT EXISTS idx_applications_request ON work_applications(request_id);
CREATE INDEX IF NOT EXISTS idx_applications_applicant ON work_applications(applicant_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON work_applications(status);

-- Work sessions
CREATE TABLE IF NOT EXISTS work_sessions (
    id TEXT PRIMARY KEY,
    request_id TEXT REFERENCES work_requests(id) ON DELETE SET NULL,
    requester_id TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    deliverables_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_sessions_requester ON work_sessions(requester_id);
CREATE INDEX IF NOT EXISTS idx_sessions_worker ON work_sessions(worker_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON work_sessions(status);

-- Session reviews
CREATE TABLE IF NOT EXISTS session_reviews (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
    comment TEXT,
    dimensions_json TEXT DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_session ON session_reviews(session_id);
CREATE INDEX IF NOT EXISTS idx_reviews_subject ON session_reviews(subject_id);
"""


# Global database instance
_db: Optional[Database] = None


def get_database() -> Database:
    """Get or create the global database instance."""
    global _db
    if _db is None:
        _db = Database()
    return _db


def reset_database():
    """Reset the global database instance (for testing)."""
    global _db
    _db = None
