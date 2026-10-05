"""Hybrid ranking and SQL scope regression checks without a live database."""
import unittest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from sqlalchemy.dialects import postgresql

from backend.app.models.source_item import SourceItem
from backend.app.retrieval.search import SearchHit, _fuse_hits, search_chunks


def hit(number, score=0.9):
    return SearchHit(SourceItem(id=UUID(int=number)), "Document", score)


class FusionTests(unittest.TestCase):
    def test_agreement_boosts_rank_and_deduplicates(self):
        results = _fuse_hits([hit(1), hit(2)], [hit(3), hit(2)], top_k=3)
        self.assertEqual([h.chunk.id.int for h in results], [2, 1, 3])
        self.assertTrue(all(0 < h.score <= 1 for h in results))

    def test_raw_scores_do_not_control_fusion(self):
        results = _fuse_hits([hit(1, 0.01)], [hit(2, 100)], top_k=1)
        self.assertEqual(results[0].chunk.id.int, 1)

    def test_repeated_candidates_count_once(self):
        results = _fuse_hits([hit(1), hit(1)], [hit(2)], top_k=3)
        self.assertEqual([h.score for h in results], [0.5, 0.5])

    def test_empty_branch_and_limit(self):
        self.assertEqual(len(_fuse_hits([], [hit(2), hit(3)], top_k=1)), 1)
        self.assertEqual(_fuse_hits([], [], top_k=5), [])


class SearchTests(unittest.IsolatedAsyncioTestCase):
    def session(self, *rows):
        session = MagicMock()
        session.bind.dialect.name = "postgresql"
        results = []
        for batch in rows:
            result = MagicMock()
            result.all.return_value = batch
            results.append(result)
        session.execute = AsyncMock(side_effect=results)
        return session

    async def test_both_branches_preserve_owner_status_and_metadata(self):
        session = self.session([(hit(1).chunk, "Vector", 0.9)], [(hit(2).chunk, "Keyword", 0.2)])
        results = await search_chunks(session, owner_id=UUID(int=9), query_vector=[0.1], query="assessment", top_k=2, score_threshold=0.7, metadata={"paper": "COMP101"})
        self.assertEqual({h.chunk.id.int for h in results}, {1, 2})
        self.assertEqual(session.execute.await_count, 2)
        for call in session.execute.call_args_list:
            sql = str(call.args[0].compile(dialect=postgresql.dialect()))
            self.assertIn("source_documents.owner_id =", sql)
            self.assertIn("source_documents.status =", sql)
            self.assertIn("@>", sql)
        lexical_sql = str(session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("@@", lexical_sql)
        self.assertNotIn("<=>", lexical_sql)

    async def test_blank_query_keeps_vector_score(self):
        session = self.session([(hit(1).chunk, "Vector", 0.8)])
        results = await search_chunks(session, owner_id=UUID(int=9), query_vector=[0.1], query="  ", top_k=2, score_threshold=0.7)
        self.assertEqual(results[0].score, 0.8)
        session.execute.assert_awaited_once()

    async def test_zero_limit_does_not_query(self):
        session = self.session()
        self.assertEqual(await search_chunks(session, owner_id=UUID(int=9), query_vector=[0.1], query="assessment", top_k=0, score_threshold=0.7), [])
        session.execute.assert_not_awaited()
