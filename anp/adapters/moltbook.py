"""Moltbook adapter for identity verification and social features.

This adapter allows ANP agents to:
1. Verify their Moltbook identity via profile lookup
2. Post to Moltbook channels
3. Check reputation/standing on Moltbook
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
import httpx

from anp.models.identity import IdentityProviderType


@dataclass
class MoltbookUser:
    """A Moltbook user profile."""
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    karma: int = 0
    post_count: int = 0
    comment_count: int = 0


@dataclass
class MoltbookPost:
    """A Moltbook post."""
    id: str
    title: str
    content: str
    author: str
    submolt: str
    url: str
    created_at: datetime
    upvotes: int = 0
    downvotes: int = 0
    comment_count: int = 0


@dataclass
class VerificationChallenge:
    """A challenge for Moltbook identity verification."""
    challenge_id: str
    agent_id: str
    moltbook_handle: str
    challenge_code: str
    created_at: datetime
    expires_at: datetime
    verified: bool = False


class MoltbookAdapter:
    """Adapter for interacting with Moltbook API.
    
    Provides identity verification via a challenge-response flow:
    1. Agent requests verification for a Moltbook handle
    2. Adapter generates a unique challenge code
    3. Agent posts the challenge code to their Moltbook profile or a specific post
    4. Adapter verifies the challenge was posted by the claimed handle
    """
    
    BASE_URL = "https://www.moltbook.com/api/v1"
    PROVIDER_TYPE = IdentityProviderType.MOLTBOOK
    
    # In-memory challenge storage (replace with persistent storage in production)
    _challenges: dict[str, VerificationChallenge] = {}
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the adapter.
        
        Args:
            api_key: Moltbook API key for authenticated operations.
                    Not required for reading public profiles.
        """
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def headers(self) -> dict:
        """Get request headers."""
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=self.headers,
                timeout=30.0,
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # Profile operations
    
    async def get_user(self, username: str) -> Optional[MoltbookUser]:
        """Get a Moltbook user profile.
        
        Args:
            username: Moltbook username to look up
            
        Returns:
            MoltbookUser if found, None otherwise
        """
        client = await self._get_client()
        try:
            resp = await client.get(f"/user/{username}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            
            return MoltbookUser(
                username=data.get("username", username),
                display_name=data.get("display_name"),
                bio=data.get("bio"),
                avatar_url=data.get("avatar_url"),
                karma=data.get("karma", 0),
                post_count=data.get("post_count", 0),
                comment_count=data.get("comment_count", 0),
            )
        except httpx.HTTPError:
            return None
    
    async def user_exists(self, username: str) -> bool:
        """Check if a Moltbook username exists."""
        user = await self.get_user(username)
        return user is not None
    
    # Posting operations (requires API key)
    
    async def create_post(
        self,
        title: str,
        content: str,
        submolt: str,
    ) -> Optional[MoltbookPost]:
        """Create a new post on Moltbook.
        
        Args:
            title: Post title
            content: Post body (markdown supported)
            submolt: Target submolt (without m/ prefix)
            
        Returns:
            Created post if successful, None otherwise
        """
        if not self.api_key:
            raise ValueError("API key required for posting")
        
        client = await self._get_client()
        try:
            resp = await client.post(
                "/post",
                json={
                    "title": title,
                    "content": content,
                    "submolt": submolt,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            
            post_id = data.get("id", data.get("post_id"))
            return MoltbookPost(
                id=post_id,
                title=title,
                content=content,
                author=data.get("author", ""),
                submolt=submolt,
                url=f"https://moltbook.com/post/{post_id}",
                created_at=datetime.now(timezone.utc),
            )
        except httpx.HTTPError as e:
            print(f"Failed to create post: {e}")
            return None
    
    async def get_post(self, post_id: str) -> Optional[MoltbookPost]:
        """Get a post by ID."""
        client = await self._get_client()
        try:
            resp = await client.get(f"/post/{post_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            
            return MoltbookPost(
                id=data.get("id", post_id),
                title=data.get("title", ""),
                content=data.get("content", ""),
                author=data.get("author", ""),
                submolt=data.get("submolt", ""),
                url=f"https://moltbook.com/post/{post_id}",
                created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
                upvotes=data.get("upvotes", 0),
                downvotes=data.get("downvotes", 0),
                comment_count=data.get("comment_count", 0),
            )
        except httpx.HTTPError:
            return None
    
    async def get_user_posts(
        self,
        username: str,
        limit: int = 10,
    ) -> list[MoltbookPost]:
        """Get recent posts by a user."""
        client = await self._get_client()
        try:
            resp = await client.get(
                f"/user/{username}/posts",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            
            posts = []
            for p in data.get("posts", data if isinstance(data, list) else []):
                posts.append(MoltbookPost(
                    id=p.get("id", ""),
                    title=p.get("title", ""),
                    content=p.get("content", ""),
                    author=username,
                    submolt=p.get("submolt", ""),
                    url=f"https://moltbook.com/post/{p.get('id', '')}",
                    created_at=datetime.fromisoformat(p["created_at"]) if "created_at" in p else datetime.now(timezone.utc),
                    upvotes=p.get("upvotes", 0),
                    downvotes=p.get("downvotes", 0),
                    comment_count=p.get("comment_count", 0),
                ))
            return posts
        except httpx.HTTPError:
            return []
    
    # Verification flow
    
    def create_verification_challenge(
        self,
        agent_id: str,
        moltbook_handle: str,
        expires_in_hours: int = 24,
    ) -> VerificationChallenge:
        """Create a verification challenge for a Moltbook handle.
        
        The agent must post a message containing the challenge code
        from the claimed Moltbook account.
        
        Args:
            agent_id: The ANP agent ID requesting verification
            moltbook_handle: The Moltbook username to verify
            expires_in_hours: How long the challenge is valid
            
        Returns:
            VerificationChallenge with the code to post
        """
        now = datetime.now(timezone.utc)
        
        # Generate unique challenge code
        challenge_code = f"anp-verify-{secrets.token_hex(16)}"
        challenge_id = hashlib.sha256(
            f"{agent_id}:{moltbook_handle}:{now.isoformat()}".encode()
        ).hexdigest()[:16]
        
        challenge = VerificationChallenge(
            challenge_id=challenge_id,
            agent_id=agent_id,
            moltbook_handle=moltbook_handle,
            challenge_code=challenge_code,
            created_at=now,
            expires_at=datetime(
                now.year, now.month, now.day + (expires_in_hours // 24),
                now.hour + (expires_in_hours % 24), now.minute, now.second,
                tzinfo=timezone.utc,
            ),
        )
        
        self._challenges[challenge_id] = challenge
        return challenge
    
    async def verify_challenge(
        self,
        challenge_id: str,
    ) -> tuple[bool, str]:
        """Verify a challenge by checking recent posts from the claimed handle.
        
        Args:
            challenge_id: The challenge ID to verify
            
        Returns:
            Tuple of (success, message)
        """
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            return False, "Challenge not found"
        
        if challenge.verified:
            return True, "Already verified"
        
        now = datetime.now(timezone.utc)
        if now > challenge.expires_at:
            return False, "Challenge expired"
        
        # Check if user exists
        user = await self.get_user(challenge.moltbook_handle)
        if not user:
            return False, f"Moltbook user '{challenge.moltbook_handle}' not found"
        
        # Check recent posts for the challenge code
        posts = await self.get_user_posts(challenge.moltbook_handle, limit=20)
        for post in posts:
            if challenge.challenge_code in post.content:
                challenge.verified = True
                return True, f"Verified via post {post.id}"
        
        return False, "Challenge code not found in recent posts"
    
    def get_challenge(self, challenge_id: str) -> Optional[VerificationChallenge]:
        """Get a challenge by ID."""
        return self._challenges.get(challenge_id)
    
    def get_challenge_instructions(self, challenge: VerificationChallenge) -> str:
        """Get human-readable instructions for completing verification."""
        return f"""
To verify your Moltbook identity, post a message containing this code:

{challenge.challenge_code}

Post it to any submolt from your @{challenge.moltbook_handle} account.
The verification will expire at {challenge.expires_at.isoformat()}.

Once posted, call verify_challenge('{challenge.challenge_id}') to complete verification.
""".strip()
    
    # Feed operations
    
    async def get_feed(
        self,
        submolt: Optional[str] = None,
        limit: int = 25,
    ) -> list[MoltbookPost]:
        """Get posts from a submolt or the main feed."""
        client = await self._get_client()
        try:
            if submolt:
                resp = await client.get(
                    f"/submolt/{submolt}/posts",
                    params={"limit": limit},
                )
            else:
                resp = await client.get("/feed", params={"limit": limit})
            
            resp.raise_for_status()
            data = resp.json()
            
            posts = []
            for p in data.get("posts", data if isinstance(data, list) else []):
                posts.append(MoltbookPost(
                    id=p.get("id", ""),
                    title=p.get("title", ""),
                    content=p.get("content", ""),
                    author=p.get("author", ""),
                    submolt=p.get("submolt", submolt or ""),
                    url=f"https://moltbook.com/post/{p.get('id', '')}",
                    created_at=datetime.fromisoformat(p["created_at"]) if "created_at" in p else datetime.now(timezone.utc),
                    upvotes=p.get("upvotes", 0),
                    downvotes=p.get("downvotes", 0),
                    comment_count=p.get("comment_count", 0),
                ))
            return posts
        except httpx.HTTPError:
            return []


# Synchronous wrapper for non-async contexts
class MoltbookAdapterSync:
    """Synchronous wrapper around MoltbookAdapter."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._async_adapter = MoltbookAdapter(api_key)
    
    def _run(self, coro):
        """Run a coroutine synchronously."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    def get_user(self, username: str) -> Optional[MoltbookUser]:
        return self._run(self._async_adapter.get_user(username))
    
    def user_exists(self, username: str) -> bool:
        return self._run(self._async_adapter.user_exists(username))
    
    def create_post(self, title: str, content: str, submolt: str) -> Optional[MoltbookPost]:
        return self._run(self._async_adapter.create_post(title, content, submolt))
    
    def get_post(self, post_id: str) -> Optional[MoltbookPost]:
        return self._run(self._async_adapter.get_post(post_id))
    
    def get_user_posts(self, username: str, limit: int = 10) -> list[MoltbookPost]:
        return self._run(self._async_adapter.get_user_posts(username, limit))
    
    def create_verification_challenge(
        self,
        agent_id: str,
        moltbook_handle: str,
        expires_in_hours: int = 24,
    ) -> VerificationChallenge:
        return self._async_adapter.create_verification_challenge(
            agent_id, moltbook_handle, expires_in_hours
        )
    
    def verify_challenge(self, challenge_id: str) -> tuple[bool, str]:
        return self._run(self._async_adapter.verify_challenge(challenge_id))
    
    def get_challenge(self, challenge_id: str) -> Optional[VerificationChallenge]:
        return self._async_adapter.get_challenge(challenge_id)
    
    def get_challenge_instructions(self, challenge: VerificationChallenge) -> str:
        return self._async_adapter.get_challenge_instructions(challenge)
    
    def get_feed(self, submolt: Optional[str] = None, limit: int = 25) -> list[MoltbookPost]:
        return self._run(self._async_adapter.get_feed(submolt, limit))
    
    def close(self):
        self._run(self._async_adapter.close())
