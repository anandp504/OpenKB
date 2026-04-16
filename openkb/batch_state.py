from __future__ import annotations
import asyncio


class BatchState:
    def __init__(
        self,
        concept_briefs: dict[str, str],
        system_msg: dict,
        batch_concurrency: int = 3,
    ) -> None:
        self.concept_briefs = concept_briefs
        self.system_msg = system_msg

        self.index_lock = asyncio.Lock()
        self.hashes_lock = asyncio.Lock()
        self.log_lock = asyncio.Lock()
        self.print_lock = asyncio.Lock()

        self._concept_locks: dict[str, asyncio.Lock] = {}
        self._concept_locks_meta = asyncio.Lock()

        self.batch_semaphore = asyncio.Semaphore(batch_concurrency)
        self.pending_hashes: list[tuple[str, dict]] = []

    async def get_concept_lock(self, slug: str) -> asyncio.Lock:
        async with self._concept_locks_meta:
            if slug not in self._concept_locks:
                self._concept_locks[slug] = asyncio.Lock()
            return self._concept_locks[slug]

    def update_concept_brief(self, slug: str, brief: str) -> None:
        """Called while holding concept_lock[slug] — safe without extra lock."""
        self.concept_briefs[slug] = brief

    def format_for_prompt(self) -> str:
        """80-char truncation + 100-concept cap (most recently inserted = last)."""
        items = list(self.concept_briefs.items())
        if len(items) > 100:
            items = items[-100:]
        lines = [f"- {slug}: {brief[:80]}" for slug, brief in items]
        return "\n".join(lines) or "(none yet)"
