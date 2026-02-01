"""Repository for agent identity operations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from anp.models.identity import AgentIdentity, IdentityProvider, IdentityProviderType, ServiceOrientation
from anp.storage.database import Database, get_database


class IdentityRepository:
    """Repository for CRUD operations on agent identities."""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
    
    def create(self, identity: AgentIdentity) -> AgentIdentity:
        """Create a new agent identity."""
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT INTO identities (
                    id, version, name, description, created_at, updated_at,
                    service_orientation, public_key, signature, avatar_url,
                    website_url, capabilities_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.id,
                    identity.version,
                    identity.name,
                    identity.description,
                    identity.created_at.isoformat(),
                    identity.updated_at.isoformat(),
                    identity.service_orientation.value,
                    identity.public_key,
                    identity.signature,
                    identity.avatar_url,
                    identity.website_url,
                    json.dumps(identity.capabilities),
                ),
            )
            
            # Insert identity providers
            for provider in identity.identity_providers:
                self._insert_provider(conn, identity.id, provider)
        
        return identity
    
    def _insert_provider(self, conn, identity_id: str, provider: IdentityProvider):
        """Insert an identity provider link."""
        conn.execute(
            """
            INSERT INTO identity_providers (
                identity_id, type, handle, profile_url, verified, verified_at, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity_id,
                provider.type.value,
                provider.handle,
                provider.profile_url,
                1 if provider.verified else 0,
                provider.verified_at.isoformat() if provider.verified_at else None,
                provider.fingerprint,
            ),
        )
    
    def get(self, identity_id: str) -> Optional[AgentIdentity]:
        """Get an agent identity by ID."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM identities WHERE id = ?",
                (identity_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get providers
            provider_cursor = conn.execute(
                "SELECT * FROM identity_providers WHERE identity_id = ?",
                (identity_id,),
            )
            providers = [self._row_to_provider(p) for p in provider_cursor.fetchall()]
            
            return self._row_to_identity(row, providers)
    
    def get_by_provider(
        self,
        provider_type: IdentityProviderType,
        handle: str,
    ) -> Optional[AgentIdentity]:
        """Find an identity by provider handle."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT i.* FROM identities i
                JOIN identity_providers p ON i.id = p.identity_id
                WHERE p.type = ? AND p.handle = ?
                """,
                (provider_type.value, handle),
            )
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get all providers for this identity
            provider_cursor = conn.execute(
                "SELECT * FROM identity_providers WHERE identity_id = ?",
                (row["id"],),
            )
            providers = [self._row_to_provider(p) for p in provider_cursor.fetchall()]
            
            return self._row_to_identity(row, providers)
    
    def update(self, identity: AgentIdentity) -> AgentIdentity:
        """Update an existing identity."""
        identity.updated_at = datetime.now(timezone.utc)
        
        with self.db.connection() as conn:
            conn.execute(
                """
                UPDATE identities SET
                    version = ?, name = ?, description = ?, updated_at = ?,
                    service_orientation = ?, public_key = ?, signature = ?,
                    avatar_url = ?, website_url = ?, capabilities_json = ?
                WHERE id = ?
                """,
                (
                    identity.version,
                    identity.name,
                    identity.description,
                    identity.updated_at.isoformat(),
                    identity.service_orientation.value,
                    identity.public_key,
                    identity.signature,
                    identity.avatar_url,
                    identity.website_url,
                    json.dumps(identity.capabilities),
                    identity.id,
                ),
            )
            
            # Replace providers (delete and re-insert)
            conn.execute("DELETE FROM identity_providers WHERE identity_id = ?", (identity.id,))
            for provider in identity.identity_providers:
                self._insert_provider(conn, identity.id, provider)
        
        return identity
    
    def delete(self, identity_id: str) -> bool:
        """Delete an identity. Returns True if deleted."""
        with self.db.connection() as conn:
            cursor = conn.execute("DELETE FROM identities WHERE id = ?", (identity_id,))
            return cursor.rowcount > 0
    
    def list(
        self,
        service_orientation: Optional[ServiceOrientation] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AgentIdentity]:
        """List identities with optional filtering."""
        with self.db.connection() as conn:
            if service_orientation:
                cursor = conn.execute(
                    """
                    SELECT * FROM identities
                    WHERE service_orientation = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (service_orientation.value, limit, offset),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM identities
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                )
            
            identities = []
            for row in cursor.fetchall():
                provider_cursor = conn.execute(
                    "SELECT * FROM identity_providers WHERE identity_id = ?",
                    (row["id"],),
                )
                providers = [self._row_to_provider(p) for p in provider_cursor.fetchall()]
                identities.append(self._row_to_identity(row, providers))
            
            return identities
    
    def search(self, query: str, limit: int = 20) -> list[AgentIdentity]:
        """Search identities by name or description."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM identities
                WHERE name LIKE ? OR description LIKE ?
                ORDER BY name
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
            
            identities = []
            for row in cursor.fetchall():
                provider_cursor = conn.execute(
                    "SELECT * FROM identity_providers WHERE identity_id = ?",
                    (row["id"],),
                )
                providers = [self._row_to_provider(p) for p in provider_cursor.fetchall()]
                identities.append(self._row_to_identity(row, providers))
            
            return identities
    
    def link_provider(self, identity_id: str, provider: IdentityProvider) -> bool:
        """Add a provider link to an identity."""
        with self.db.connection() as conn:
            try:
                self._insert_provider(conn, identity_id, provider)
                return True
            except Exception:
                return False
    
    def verify_provider(
        self,
        identity_id: str,
        provider_type: IdentityProviderType,
        handle: str,
    ) -> bool:
        """Mark a provider as verified."""
        with self.db.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE identity_providers
                SET verified = 1, verified_at = ?
                WHERE identity_id = ? AND type = ? AND handle = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    identity_id,
                    provider_type.value,
                    handle,
                ),
            )
            return cursor.rowcount > 0
    
    def _row_to_identity(self, row, providers: list[IdentityProvider]) -> AgentIdentity:
        """Convert a database row to an AgentIdentity."""
        return AgentIdentity(
            id=row["id"],
            version=row["version"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            service_orientation=ServiceOrientation(row["service_orientation"]),
            public_key=row["public_key"],
            signature=row["signature"],
            avatar_url=row["avatar_url"],
            website_url=row["website_url"],
            capabilities=json.loads(row["capabilities_json"]),
            identity_providers=providers,
        )
    
    def _row_to_provider(self, row) -> IdentityProvider:
        """Convert a database row to an IdentityProvider."""
        return IdentityProvider(
            type=IdentityProviderType(row["type"]),
            handle=row["handle"],
            profile_url=row["profile_url"],
            verified=bool(row["verified"]),
            verified_at=datetime.fromisoformat(row["verified_at"]) if row["verified_at"] else None,
            fingerprint=row["fingerprint"],
        )
