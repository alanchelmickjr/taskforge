"""
TaskForge Memory Interface

Integration with memoRable's salient memory system for storing and retrieving
playbook memories with intelligent salience scoring.

Features:
- Store playbook steps as salient memories
- Track task completions and patterns
- Retrieve relevant past playbooks by topic/people
- Generate pre-task briefings from memory

Requires memoRable salience service running (see https://github.com/alanchelmickjr/memoRable)
"""

import os
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime

# Try to import httpx for async HTTP, fall back to requests
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    try:
        import requests
        HAS_REQUESTS = True
    except ImportError:
        HAS_REQUESTS = False


@dataclass
class MemoryConfig:
    """Configuration for memoRable connection"""
    base_url: str = "http://localhost:3100"  # Default memoRable salience service port
    user_id: str = None  # Will be generated from machine ID if not set
    api_key: Optional[str] = None
    timeout: int = 30
    enabled: bool = True

    def __post_init__(self):
        # Load from environment if not explicitly set
        self.base_url = os.environ.get('MEMORABLE_URL', self.base_url)
        self.user_id = os.environ.get('MEMORABLE_USER_ID', self.user_id)
        self.api_key = os.environ.get('MEMORABLE_API_KEY', self.api_key)

        # Generate user ID from machine if not set
        if not self.user_id:
            self.user_id = self._generate_user_id()

    def _generate_user_id(self) -> str:
        """Generate a consistent user ID from machine characteristics"""
        try:
            # Use hostname and home directory as identity
            import socket
            identity = f"{socket.gethostname()}:{Path.home()}"
            return hashlib.sha256(identity.encode()).hexdigest()[:32]
        except:
            return "taskforge-default-user"


@dataclass
class PlaybookMemory:
    """A playbook stored as a salient memory"""
    playbook_id: str
    title: str
    summary: str
    steps_count: int
    tools_required: List[str]
    parts_required: List[str]
    topics: List[str]
    estimated_time: str
    created_at: str
    recording_path: Optional[str] = None
    playbook_path: Optional[str] = None

    def to_memory_text(self) -> str:
        """Convert to text format for salience processing"""
        lines = [
            f"Task Playbook: {self.title}",
            f"Summary: {self.summary}",
            f"Steps: {self.steps_count}",
            f"Estimated time: {self.estimated_time}",
        ]
        if self.tools_required:
            lines.append(f"Tools needed: {', '.join(self.tools_required)}")
        if self.parts_required:
            lines.append(f"Parts needed: {', '.join(self.parts_required)}")
        if self.topics:
            lines.append(f"Topics: {', '.join(self.topics)}")
        return "\n".join(lines)


@dataclass
class MemorySearchResult:
    """Result from searching salient memories"""
    memory_id: str
    text: str
    salience_score: float
    topics: List[str]
    created_at: str
    playbook_data: Optional[Dict[str, Any]] = None


class SalientMemoryClient:
    """
    Client for memoRable's salient memory service.

    Stores TaskForge playbooks as memories with salience scoring,
    enabling intelligent retrieval based on relevance and recency.
    """

    def __init__(self, config: Optional[MemoryConfig] = None):
        self.config = config or MemoryConfig()
        self._client = None

    def _get_client(self):
        """Get HTTP client (lazy initialization)"""
        if self._client is None:
            if HAS_HTTPX:
                self._client = httpx.Client(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    headers=self._get_headers()
                )
            elif HAS_REQUESTS:
                # Use requests as fallback
                self._client = "requests"
            else:
                raise RuntimeError(
                    "No HTTP client available. Install httpx or requests:\n"
                    "  pip install httpx\n"
                    "  # or\n"
                    "  pip install requests"
                )
        return self._client

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Dict:
        """Make HTTP request to memoRable service"""
        client = self._get_client()

        url = f"{self.config.base_url}{path}"

        try:
            if client == "requests":
                import requests
                if method == "GET":
                    resp = requests.get(url, headers=self._get_headers(),
                                       timeout=self.config.timeout)
                else:
                    resp = requests.post(url, json=data, headers=self._get_headers(),
                                        timeout=self.config.timeout)
                resp.raise_for_status()
                return resp.json()
            else:
                # httpx client
                if method == "GET":
                    resp = client.get(path)
                else:
                    resp = client.post(path, json=data)
                resp.raise_for_status()
                return resp.json()

        except Exception as e:
            # Return error but don't crash - memory is optional
            print(f"   ⚠️  Memory service unavailable: {e}")
            return {"success": False, "error": str(e)}

    def is_available(self) -> bool:
        """Check if memoRable service is available"""
        if not self.config.enabled:
            return False

        try:
            result = self._request("GET", "/health")
            return result.get("status") == "healthy" or result.get("alive", False)
        except:
            return False

    def store_playbook(self, playbook: 'Playbook', recording_path: Optional[Path] = None,
                       playbook_path: Optional[Path] = None) -> Optional[str]:
        """
        Store a playbook as a salient memory.

        Returns memory_id if successful, None if failed.
        """
        if not self.config.enabled:
            return None

        # Create playbook memory
        memory = PlaybookMemory(
            playbook_id=hashlib.sha256(
                f"{playbook.title}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16],
            title=playbook.title,
            summary=playbook.summary,
            steps_count=len(playbook.steps),
            tools_required=playbook.tools_required,
            parts_required=playbook.parts_required,
            topics=self._extract_topics(playbook),
            estimated_time=playbook.estimated_time,
            created_at=datetime.now().isoformat(),
            recording_path=str(recording_path) if recording_path else None,
            playbook_path=str(playbook_path) if playbook_path else None,
        )

        # Store via salience service
        result = self._request("POST", "/api/salience/enrich", {
            "memoryId": memory.playbook_id,
            "text": memory.to_memory_text(),
            "userId": self.config.user_id,
            "context": {
                "detectedContext": "work_meeting",  # Task documentation is work
            },
            "metadata": {
                "type": "taskforge_playbook",
                "playbook": asdict(memory),
            }
        })

        if result.get("success"):
            print(f"   📝 Stored playbook in memory (salience: {result.get('salience', {}).get('score', 'N/A')})")
            return memory.playbook_id
        else:
            return None

    def search_playbooks(self, query: str, limit: int = 10) -> List[MemorySearchResult]:
        """
        Search for relevant playbooks based on query.

        Uses salience-aware retrieval to find most relevant matches.
        """
        if not self.config.enabled:
            return []

        result = self._request("POST", "/api/salience/retrieve", {
            "query": query,
            "userId": self.config.user_id,
            "filter": {
                "metadata.type": "taskforge_playbook"
            },
            "limit": limit,
            "minSalience": 20,  # Only return somewhat relevant results
        })

        if not result.get("success"):
            return []

        memories = []
        for item in result.get("memories", []):
            memories.append(MemorySearchResult(
                memory_id=item.get("memoryId", ""),
                text=item.get("text", ""),
                salience_score=item.get("salience", {}).get("score", 0),
                topics=item.get("extractedFeatures", {}).get("topics", []),
                created_at=item.get("createdAt", ""),
                playbook_data=item.get("metadata", {}).get("playbook"),
            ))

        return memories

    def get_task_briefing(self, task_description: str) -> Optional[Dict[str, Any]]:
        """
        Get a briefing before starting a new task.

        Returns relevant past playbooks, tools commonly used,
        and suggestions based on memory.
        """
        if not self.config.enabled:
            return None

        # Search for related playbooks
        related = self.search_playbooks(task_description, limit=5)

        if not related:
            return None

        # Aggregate tools and parts from related playbooks
        all_tools = set()
        all_parts = set()
        for mem in related:
            if mem.playbook_data:
                all_tools.update(mem.playbook_data.get("tools_required", []))
                all_parts.update(mem.playbook_data.get("parts_required", []))

        return {
            "related_playbooks": [
                {
                    "title": m.playbook_data.get("title") if m.playbook_data else "Unknown",
                    "salience": m.salience_score,
                    "path": m.playbook_data.get("playbook_path") if m.playbook_data else None,
                }
                for m in related
            ],
            "suggested_tools": list(all_tools),
            "suggested_parts": list(all_parts),
            "tip": f"Found {len(related)} related playbooks from past tasks.",
        }

    def log_task_completion(self, playbook_id: str, duration_seconds: float,
                            notes: Optional[str] = None) -> bool:
        """
        Log that a playbook/task was completed.

        Helps the salience system learn which playbooks are actually useful.
        """
        if not self.config.enabled:
            return False

        result = self._request("POST", "/api/salience/feedback", {
            "memoryId": playbook_id,
            "userId": self.config.user_id,
            "feedback": "helpful",
            "actionType": "task_completed",
            "metadata": {
                "duration_seconds": duration_seconds,
                "notes": notes,
            }
        })

        return result.get("success", False)

    def _extract_topics(self, playbook: 'Playbook') -> List[str]:
        """Extract topics from playbook content"""
        topics = set()

        # Add from title
        title_words = playbook.title.lower().split()
        topics.update(w for w in title_words if len(w) > 3)

        # Add from tools
        for tool in playbook.tools_required:
            topics.add(tool.lower())

        # Add from step titles
        for step in playbook.steps:
            step_words = step.title.lower().split()
            topics.update(w for w in step_words if len(w) > 4)

        return list(topics)[:10]  # Limit to 10 topics

    def close(self):
        """Close HTTP client"""
        if self._client and HAS_HTTPX and self._client != "requests":
            self._client.close()
            self._client = None


# Singleton instance for convenience
_memory_client: Optional[SalientMemoryClient] = None


def get_memory_client(config: Optional[MemoryConfig] = None) -> SalientMemoryClient:
    """Get the global memory client instance"""
    global _memory_client
    if _memory_client is None or config is not None:
        _memory_client = SalientMemoryClient(config)
    return _memory_client


def store_playbook_memory(playbook: 'Playbook', recording_path: Optional[Path] = None,
                          playbook_path: Optional[Path] = None) -> Optional[str]:
    """Convenience function to store a playbook in memory"""
    client = get_memory_client()
    return client.store_playbook(playbook, recording_path, playbook_path)


def search_related_playbooks(query: str, limit: int = 10) -> List[MemorySearchResult]:
    """Convenience function to search playbooks"""
    client = get_memory_client()
    return client.search_playbooks(query, limit)


def get_task_briefing(task_description: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get task briefing"""
    client = get_memory_client()
    return client.get_task_briefing(task_description)
