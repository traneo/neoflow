"""Session management for the FastAPI server."""
import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ChatSession:
    """Represents a single chat session with conversation history."""
    session_id: str
    created_at: datetime
    last_activity: datetime
    include_code: bool
    save_history: bool
    history: list[dict] = field(default_factory=list)
    last_query: str | None = None
    last_keyword: str = ""
    last_answer: str | None = None

    @property
    def query_count(self) -> int:
        """Return the number of queries in this session."""
        return len(self.history)


class SessionManager:
    """Manages chat sessions with TTL and cleanup."""

    def __init__(self, ttl_minutes: int = 60, max_sessions: int = 100, history_dir: str = "chat_history"):
        self._sessions: dict[str, ChatSession] = {}
        self._lock = asyncio.Lock()
        self._ttl_minutes = ttl_minutes
        self._max_sessions = max_sessions
        self._history_dir = history_dir
        self._cleanup_task: asyncio.Task | None = None

    async def create_session(self, include_code: bool = False, save_history: bool = True) -> ChatSession:
        """Create a new chat session."""
        async with self._lock:
            # Check session limit
            if len(self._sessions) >= self._max_sessions:
                # Remove oldest expired session, or oldest overall if none expired
                now = datetime.now()
                expired = [
                    (sid, sess) for sid, sess in self._sessions.items()
                    if now - sess.last_activity > timedelta(minutes=self._ttl_minutes)
                ]
                if expired:
                    oldest_sid = min(expired, key=lambda x: x[1].last_activity)[0]
                else:
                    oldest_sid = min(self._sessions.items(), key=lambda x: x[1].last_activity)[0]
                await self._delete_session_internal(oldest_sid, save=False)
                logger.info("Session limit reached, removed session %s", oldest_sid)

            session_id = str(uuid.uuid4())
            now = datetime.now()
            session = ChatSession(
                session_id=session_id,
                created_at=now,
                last_activity=now,
                include_code=include_code,
                save_history=save_history,
            )
            self._sessions[session_id] = session
            logger.info("Created session %s (include_code=%s, save_history=%s)",
                       session_id, include_code, save_history)
            return session

    async def get_session(self, session_id: str) -> ChatSession | None:
        """Retrieve a session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def delete_session(self, session_id: str, save: bool = True) -> None:
        """Delete a session, optionally saving history."""
        async with self._lock:
            await self._delete_session_internal(session_id, save)

    async def _delete_session_internal(self, session_id: str, save: bool) -> None:
        """Internal delete without lock (caller must hold lock)."""
        session = self._sessions.get(session_id)
        if not session:
            return

        if save and session.save_history and session.history:
            await self._save_history(session)

        del self._sessions[session_id]
        logger.info("Deleted session %s", session_id)

    async def touch_session(self, session_id: str) -> None:
        """Update last activity timestamp for a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.last_activity = datetime.now()

    async def cleanup_expired(self) -> int:
        """Remove sessions that have exceeded TTL. Returns number of removed sessions."""
        async with self._lock:
            now = datetime.now()
            expired = [
                sid for sid, sess in self._sessions.items()
                if now - sess.last_activity > timedelta(minutes=self._ttl_minutes)
            ]
            for sid in expired:
                await self._delete_session_internal(sid, save=True)
            if expired:
                logger.info("Cleaned up %d expired sessions", len(expired))
            return len(expired)

    async def _save_history(self, session: ChatSession) -> None:
        """Save session history to disk."""
        try:
            os.makedirs(self._history_dir, exist_ok=True)
            ts = session.created_at.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._history_dir, f"chat_{ts}_{session.session_id[:8]}.json")
            with open(path, "w") as f:
                json.dump(session.history, f, indent=2)
            logger.info("Saved session history to %s", path)
        except Exception as e:
            logger.error("Failed to save session history: %s", e)

    async def start_cleanup_task(self) -> None:
        """Start background task for cleaning up expired sessions."""
        if self._cleanup_task is not None:
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(600)  # Run every 10 minutes
                    await self.cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in cleanup task: %s", e)

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Started session cleanup task (TTL: %d minutes)", self._ttl_minutes)

    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped session cleanup task")

    def get_session_count(self) -> int:
        """Return the current number of active sessions."""
        return len(self._sessions)
