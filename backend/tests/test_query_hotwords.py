import unittest
from unittest.mock import patch

from app.agent.query_hotwords import analyze_hotwords, hotword_catalogue
from app.agent.query_agent import QueryAgent, normalize_question, query_preview
from app.core.config import Settings
from app.schemas.chat import QueryPlanRead


class QueryHotwordTests(unittest.TestCase):
    def test_curated_correction_repeated_terms_and_original_offsets(self):
        text = 'GB 2760-2024 中菌落总树和菌落总树，0.5 mg/kg？'
        result = analyze_hotwords(text)
        self.assertEqual(result['corrected_question'], text.replace('菌落总树', '菌落总数'))
        self.assertEqual(len(result['corrections']), 2)
        for item in result['corrections']:
            self.assertEqual(text[item['start']:item['end']], item['original'])

    def test_distinct_valid_terms_and_subtypes_are_preserved(self):
        text = '亚硝酸盐和硝酸盐，山梨酸钾与苯甲酸钠，黄曲霉毒素B1与M1，大肠杆菌O157:H7'
        result = analyze_hotwords(text)
        self.assertEqual(result['corrected_question'], text)
        self.assertEqual(result['corrections'], [])
        self.assertEqual(result['suggestions'], [])
        self.assertIn('亚硝酸盐', [m['term'] for m in result['hotword_matches']])

    def test_fuzzy_ambiguity_requires_confirmation(self):
        text = '大肠杆群的要求是什么？'
        result = analyze_hotwords(text)
        self.assertEqual(result['corrected_question'], text)
        self.assertEqual(result['corrections'], [])
        self.assertIn('大肠菌群', result['suggestions'][0]['candidates'])

    def test_identifiers_urls_files_and_latin_suffix_are_protected(self):
        text = 'https://example.test/菌落总树 菌落总树.pdf XTVBN GB/T 5009.228-2016 0.5mg/kg 黄曲霉毒索B10'
        self.assertEqual(analyze_hotwords(text)['corrected_question'], text)
        self.assertNotIn('挥发性盐基氮', normalize_question('XTVBN'))
        self.assertEqual(analyze_hotwords('黄曲霉毒索B1')['corrected_question'], '黄曲霉毒素B1')
        self.assertEqual(normalize_question('https://example.test/DON DON.txt'), 'https://example.test/DON DON.txt')
        self.assertEqual(normalize_question('查看 https://example.test/TVBN TVBN.pdf 中的要求'), '查看 https://example.test/TVBN TVBN.pdf 中的要求')

    def test_longest_match_and_local_alias_rewrite(self):
        result = query_preview('脱氢已酸钠和DON、TVBN的检测')
        self.assertEqual(result['corrections'][0]['replacement'], '脱氢乙酸钠')
        self.assertIn('脱氧雪腐镰刀菌烯醇', result['normalized_question'])
        self.assertIn('挥发性盐基氮', result['normalized_question'])

    def test_preview_matches_actual_plan_without_llm(self):
        question = '菌落总树和过氧化直的要求是什么？'
        settings = Settings(_env_file=None, OPENAI_API_KEY='', QUERY_AGENT_LLM_ENABLED=False)
        with patch('app.agent.query_agent.get_settings', return_value=settings), patch('app.agent.query_agent.OpenAICompatibleLLM', side_effect=AssertionError('No paid model')):
            plan = QueryAgent().plan(question)
        preview = query_preview(question)
        self.assertEqual(plan.original_question, question)
        self.assertEqual(plan.normalized_question, preview['normalized_question'])
        self.assertEqual(plan.corrections, preview['corrections'])
        self.assertIn('过氧化值', plan.metrics)
        self.assertEqual(QueryPlanRead.model_validate(plan.to_dict()).corrections, plan.corrections)

    def test_disabled_agent_still_has_deterministic_correction(self):
        settings = Settings(_env_file=None, QUERY_AGENT_ENABLED=False)
        with patch('app.agent.query_agent.get_settings', return_value=settings):
            plan = QueryAgent().plan('沙门市菌检测')
        self.assertIn('沙门氏菌', plan.normalized_question)
        self.assertEqual(len(plan.corrections), 1)
        self.assertFalse(plan.llm_used)

    def test_optional_llm_plan_keeps_deterministic_correction_trace(self):
        settings = Settings(_env_file=None, QUERY_AGENT_LLM_ENABLED=True)
        with patch('app.agent.query_agent.get_settings', return_value=settings), patch('app.agent.query_agent.OpenAICompatibleLLM') as llm:
            llm.return_value.complete_json.return_value = {'normalized_question': '菌落总树限量', 'rewritten_queries': ['菌落总树限量']}
            plan = QueryAgent().plan('菌落总树限量')
        self.assertEqual(plan.normalized_question, '菌落总数限量')
        self.assertEqual(len(plan.corrections), 1)
        self.assertTrue(plan.llm_used)

    def test_generation_uses_corrected_question_but_history_retains_original(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.models import Base, User, Document, ChatLog
        from app.agent.evidence_judge import EvidenceDecision
        from app.services.rag_service import RagService
        from app.schemas.chat import ChatResponse
        from app.services.log_service import chat_log_to_read
        settings = Settings(_env_file=None, OPENAI_API_KEY='', QUERY_AGENT_LLM_ENABLED=False)
        question = '菌落总树的检测要求？'
        with patch('app.agent.query_agent.get_settings', return_value=settings): plan = QueryAgent().plan(question)
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as db, patch('app.services.rag_service.get_settings', return_value=settings):
            user = User(username='synthetic', hashed_password='test'); db.add(user); db.flush()
            doc = Document(filename='synthetic.txt', storage_path='synthetic', file_type='txt', owner_id=user.id, status='indexed')
            db.add(doc); db.commit()
            hits = [{'id':'test', 'score':.9, 'text':'菌落总数。这是用于验证纠错管线的完整合成文本，不是真实文档或业务结论。', 'metadata':{'document_id':doc.id,'filename':'synthetic.txt','chunk_type':'text'}}]
            with patch('app.services.rag_service.PermissionAwareRetriever') as retriever, patch('app.services.rag_service.EvidenceJudge') as judge, patch.object(RagService, '_generate_answer', return_value=ChatResponse(answer='合成回答')) as generate:
                retriever.return_value.retrieve_with_plan.return_value = (hits, [], plan)
                judge.return_value.judge.return_value = EvidenceDecision(sufficient=True)
                response = RagService().answer(db, user=user, question=question)
                self.assertEqual(generate.call_args.args[0], '菌落总数的检测要求？')
                self.assertNotIn('菌落总树', generate.call_args.kwargs['generation_prompt'])
            log = db.get(ChatLog, response.log_id)
            self.assertEqual(log.question, question)
            restored = chat_log_to_read(log).response.query_plan
            self.assertEqual(restored.original_question, question)
            self.assertEqual(restored.corrections, plan.corrections)
        engine.dispose()

    def test_catalogue_is_versioned_sourced_and_bounded(self):
        catalogue = hotword_catalogue()
        self.assertEqual(len(catalogue['entries']), 48)
        self.assertEqual(set(e['category'] for e in catalogue['entries']), set(catalogue['categories']))
        self.assertTrue(all(e['source']['url'].startswith('https://www.nhc.gov.cn/') for e in catalogue['entries']))
        with self.assertRaises(ValueError): analyze_hotwords('中'*4001)
        result = analyze_hotwords('大肠杆群'*100)
        self.assertLessEqual(len(result['suggestions']), 5)


if __name__ == '__main__':
    unittest.main()
