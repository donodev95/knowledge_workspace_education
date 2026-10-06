import unittest
from unittest.mock import patch
from sqlalchemy import select, func
from backend.tests import test_ownership
from backend.app.models import SourceDocument, SourceItem, SourceItemLink, DocumentType, DocumentStatus, ItemType, CoverageBatchAttempt
from backend.app.llm import pair_judge
from backend.app.services import coverage_analysis
from backend.app.schemas.coverage import BatchJudgment, RequirementJudgments, OutcomeMatch


class FakeJudge:
    def __init__(self, verdict='addresses'):
        self.verdict=verdict
        self.calls=[]
    async def judge_batch(self, requirements, outcomes, eligible_pairs):
        self.calls.append(len(requirements))
        return BatchJudgment(results=[RequirementJudgments(requirement_id=r.id,
            matches=[] if self.verdict=='does_not_address' else [OutcomeMatch(outcome_id=o.id,verdict=self.verdict,rationale='Evidence') for o in outcomes if (r.id,o.id) in eligible_pairs],
            no_match=self.verdict=='does_not_address') for r in requirements])


class CoverageInputTests(unittest.TestCase):
    setUp=test_ownership.OwnershipTests.setUp
    headers=test_ownership.OwnershipTests.headers

    def prepare(self,count=1):
        self.items[0].item_type=ItemType.LEARNING_OUTCOME
        self.items[0].label='lo_1'
        assessment=SourceDocument(paper_id=self.paper.id,document_type=DocumentType.ASSESSMENT_BRIEF,assessment_number=1,
            original_filename='brief.pdf',display_name='Brief',mime_type='application/pdf',file_size=1,content_hash='a'*64,status=DocumentStatus.EXTRACTED)
        self.session.add(assessment);self.session.flush()
        for n in range(count):
            self.session.add(SourceItem(source_document_id=assessment.id,item_type=ItemType.ASSESSMENT_REQUIREMENT,
                chunk_index=n,label=f'unknown_{n}',content=f'Requirement {n}',normalized_content=f'Requirement {n}',content_hash='b'*64,token_count=2))
        self.session.commit()
        return assessment

    def run_analysis(self,judge,**kwargs):
        payload={'paper_id':str(self.paper.id),'assessment_number':1,**kwargs}
        original = coverage_analysis.create_links
        async def capture(*args, **options):
            summary = await original(*args, **options)
            self.analysis_summary = summary.model_dump(mode='json')
            return summary
        with patch.object(pair_judge,'get_pair_judge',return_value=judge), patch.object(coverage_analysis, 'create_links', side_effect=capture):
            return self.client.post('/api/v1/source-item-links',headers=self.headers(),json=payload)

    def test_multiple_assessment_briefs_combined(self):
        first = self.prepare(2)
        second = self.prepare(3)
        second.assessment_number = 2
        self.session.commit()
        judge = FakeJudge()
        response = self.run_analysis(judge, assessment_number=None,
            assessment_document_ids=[str(first.id), str(second.id), str(first.id)])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['proposed_link_count'], 5)
        self.assertEqual(self.analysis_summary['requirement_count'], 5)
        self.assertEqual(set(self.analysis_summary['assessment_document_ids']), {str(first.id), str(second.id)})
        self.assertIsNone(self.analysis_summary['assessment_number'])
        query = f'/api/v1/source-item-links/proposed?paper_id={self.paper.id}&assessment_document_ids={first.id}&assessment_document_ids={second.id}'
        proposals = self.client.get(query, headers=self.headers()).json()
        self.assertEqual(proposals['proposed_link_count'], 5)
        self.assertEqual({p['assessment_number'] for p in proposals['outcomes'][0]['supporting_requirements']}, {1, 2})

    def test_multi_selection_rejects_wrong_document_type(self):
        self.prepare()
        response = self.run_analysis(FakeJudge(), assessment_document_ids=[str(self.doc.id)])
        self.assertEqual(response.status_code, 422)

    def test_multi_selection_requires_documents(self):
        self.assertEqual(self.run_analysis(FakeJudge(), assessment_number=None, assessment_document_ids=[]).status_code, 422)

    def test_analysis_response_count_and_empty_message(self):
        self.prepare(2)
        empty = self.run_analysis(FakeJudge('does_not_address'))
        self.assertEqual(empty.json(), {'proposed_link_count': 0, 'message': 'No link was created.'})
        created = self.run_analysis(FakeJudge())
        self.assertEqual(created.json(), {'proposed_link_count': 2, 'message': '2 proposed links available.'})

    def test_list_proposals_grouped_and_protected(self):
        brief = self.prepare(2)
        self.assertEqual(self.run_analysis(FakeJudge()).status_code, 200)
        path = f'/api/v1/source-item-links/proposed?paper_id={self.paper.id}'
        self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get(path, headers=self.headers(1)).status_code, 404)
        response = self.client.get(path, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['proposed_link_count'], 2)
        self.assertEqual(len(data['outcomes']), 1)
        group = data['outcomes'][0]
        self.assertEqual(group['learning_outcome']['id'], str(self.items[0].id))
        self.assertEqual(len(group['supporting_requirements']), 2)
        support = group['supporting_requirements'][0]
        self.assertEqual(support['requirement']['source_document_id'], str(brief.id))
        self.assertTrue(support['link']['rationale'])
        self.assertEqual(self.client.get(path + '&assessment_number=2', headers=self.headers()).json()['outcomes'], [])
        self.assertEqual(self.client.get(path + f'&assessment_document_id={brief.id}', headers=self.headers()).json()['proposed_link_count'], 2)
        self.client.patch('/api/v1/source-item-links/' + support['link']['id'], headers=self.headers(), json={'status': 'confirmed'})
        self.assertEqual(self.client.get(path, headers=self.headers()).json()['proposed_link_count'], 1)

    def test_small_batch_compares_all_outcomes(self):
        self.prepare(3)
        for n in range(2, 6):
            self.session.add(SourceItem(source_document_id=self.doc.id,
                item_type=ItemType.LEARNING_OUTCOME, chunk_index=n,
                label=f'LO{n}', content=f'Outcome {n}', normalized_content=f'Outcome {n}',
                content_hash='c'*64, token_count=2))
        self.session.commit()
        class Judge(FakeJudge):
            async def judge_batch(self, requirements, outcomes, eligible_pairs):
                assert len(outcomes) == 5
                return await super().judge_batch(requirements, outcomes, eligible_pairs)
        judge = Judge()
        response = self.run_analysis(judge)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(judge.calls, [3])
        self.assertEqual(self.analysis_summary['pair_count'], 15)
        self.assertEqual(len(self.analysis_summary['outcome_reviews']), 5)
        self.assertTrue(all(len(group['pairs']) == 3 for group in self.analysis_summary['outcome_reviews']))

    def test_small_batches_and_negative_results_are_reanalyzed(self):
        self.prepare(9)
        judge=FakeJudge('does_not_address')
        response=self.run_analysis(judge)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(judge.calls,[4,4,1])
        self.assertEqual(self.analysis_summary['analyzed_pair_count'],9)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(CoverageBatchAttempt)),0)
        again=self.run_analysis(judge)
        self.assertEqual(self.analysis_summary['model_call_count'],3)
        self.assertNotIn('cached_pair_count', self.analysis_summary)
        self.assertNotIn('cached', self.analysis_summary['pairs'][0])
        self.assertEqual(len(self.analysis_summary['outcomes_with_no_suggested_match']),1)

    def test_refresh_preserves_proposals_and_review(self):
        self.prepare()
        response=self.run_analysis(FakeJudge())
        link=self.analysis_summary['proposed_links'][0]['link']
        negative=self.run_analysis(FakeJudge('does_not_address'),refresh_proposals=True)
        self.assertEqual(self.analysis_summary['proposed_links'][0]['link']['rationale'],link['rationale'])
        self.assertEqual(self.analysis_summary['pairs'][0]['verdict'],'does_not_address')
        review=self.client.patch(f"/api/v1/source-item-links/{link['id']}",headers=self.headers(),json={'status':'confirmed'})
        self.assertEqual(review.json()['confirmed_coverage'],1)
        judge=FakeJudge()
        self.run_analysis(judge,refresh_proposals=True)
        self.assertEqual(self.analysis_summary['model_call_count'],0)

    def test_missing_requirements_never_become_negative(self):
        self.prepare(2)
        class Bad(FakeJudge):
            async def judge_batch(self,*args): return BatchJudgment(results=[])
        response=self.run_analysis(Bad())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(self.analysis_summary['pairs_needing_review']),2)
        self.assertEqual(self.analysis_summary['outcomes_with_no_suggested_match'],[])

    def test_timeout_is_unresolved_without_automatic_retries(self):
        self.prepare(2)
        class Slow(FakeJudge):
            async def judge_batch(self,reqs,outcomes,keys):
                if len(reqs)>1: raise TimeoutError()
                return await super().judge_batch(reqs,outcomes,keys)
        response=self.run_analysis(Slow())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.analysis_summary['model_call_count'],1)
        self.assertEqual(self.analysis_summary['analyzed_pair_count'],0)
        self.assertEqual([b['status'] for b in self.analysis_summary['batches']],['failed'])

    def test_budget_leaves_unresolved(self):
        import asyncio
        self.prepare()
        class Slow(FakeJudge):
            async def judge_batch(self,*args): await asyncio.sleep(5)
        response=self.run_analysis(Slow(),time_budget_seconds=1)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(len(self.analysis_summary['pairs_needing_review']),1)
        self.assertEqual(self.analysis_summary['outcomes_with_no_suggested_match'],[])

    def test_authorization_and_ambiguity(self):
        self.prepare()
        payload={'paper_id':str(self.paper.id),'assessment_number':1}
        self.assertEqual(self.client.post('/api/v1/source-item-links',json=payload).status_code,401)
        self.assertEqual(self.client.post('/api/v1/source-item-links',headers=self.headers(1),json=payload).status_code,404)
        self.prepare()
        self.assertEqual(self.run_analysis(FakeJudge()).status_code,409)

    def test_caller_work_is_not_rolled_back(self):
        self.prepare()
        # No flush: caller's pending edits must survive service-owned transactions.
        self.paper.title='Pending caller edit'
        response=self.run_analysis(FakeJudge())
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(self.paper,self.session.dirty)
        self.assertEqual(self.paper.title,'Pending caller edit')
