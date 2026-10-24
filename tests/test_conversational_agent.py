"""End-to-end orchestration, actual file data, privacy and bounded tool authority."""
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib import error

from streamlit.testing.v1 import AppTest
from agent_hub import AgentContext, AgentRegistry, Capability
from agent_modules import build_registry
from agent_workspace import (Attachment, Workspace, WorkspaceError, Executor, run_agent_turn,
                             collect_turn, snapshot, markdown_report, MAX_ACTIONS)
from agent_llm import respond, ModelError, NoRedirect

ROOT = Path(__file__).resolve().parents[1]


class ScriptedModel:
    def __init__(self, actions):
        self.actions = list(actions)
        self.inputs = []

    def __call__(self, key, instructions, inputs, tools):
        self.inputs.append(copy.deepcopy(inputs))
        if not self.actions:
            raise AssertionError('unexpected model call')
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        name, args = action
        return {'status': 'completed', 'output': [{'type':'function_call', 'name':name,
                    'call_id':f'call_{len(self.inputs)}', 'arguments':json.dumps(args, ensure_ascii=False)}]}


def outline():
    return ('outline_task', {'steps':['取得資料', '比較來源', '整理結果']})


def finish(answer='已根據來源整理 [S1]', citations=None):
    return ('finish_report', {'answer':answer, 'citations':citations or ['S1']})


class AgentWorkflowTests(unittest.TestCase):
    def test_model_replans_after_source_failure_and_integrates_two_csv_files(self):
        state = Workspace()
        files = [Attachment('a.csv', b'item,value\na,10\nb,20\n'),
                 Attachment('b.csv', b'item,value\na,15\nb,25\n')]
        state.add_files(files)
        reg = build_registry()
        reg._capabilities['web.search'] = Capability('web.search','test',lambda c,p:{'results':[
            {'url':'https://example.org/bad'}, {'url':'https://example.org/good'}]})
        def read(ctx, params):
            url = params['urls'][0]
            return {'sources':[{'url':url, 'status':'unavailable'} if url.endswith('bad') else
                               {'url':url,'title':'Report','status':'completed','text_preview':'A public report'}]}
        reg._capabilities['web.research_selected'] = Capability('web.research_selected','test',read)
        model = ScriptedModel([outline(), ('search_web',{'query':'public report','freshness':''}),
            ('read_web',{'url':'https://example.org/bad'}), ('read_web',{'url':'https://example.org/good'}),
            ('inspect_file',{'file_id':files[0].id}), ('inspect_file',{'file_id':files[1].id}),
            finish('已綜合公開報告與兩個 CSV 的欄位概況 [S2] [S3] [S4]', ['S2','S3','S4'])])
        out = run_agent_turn(state, '比較兩份資料並查公開報告', openai_key='openai-private',
                             brave_key='brave-private', registry=reg, model_call=model)
        self.assertEqual(out['status'],'completed')
        self.assertEqual(len(state.sources),4)
        self.assertEqual(state.sources[0]['status'],'unavailable')
        self.assertEqual(state.trace[2]['status'],'unavailable')
        self.assertEqual(len([r for r in state.records if r['kind']=='csv']),2)
        outputs = [x for x in model.inputs[-1] if x.get('type')=='function_call_output']
        self.assertEqual(len(outputs),6)
        self.assertEqual(outputs[0]['call_id'],'call_1')
        serialized = json.dumps(snapshot(state))
        self.assertNotIn('openai-private',serialized)
        self.assertNotIn('brave-private',serialized)
        self.assertIn('[S2]',markdown_report(state))
        followup = ScriptedModel([outline(), finish('沿用之前的公開資料比較 [S2]', ['S2'])])
        run_agent_turn(state, '接著比較前面的公開資料', openai_key='openai-private',
                       registry=reg, model_call=followup)
        self.assertIn('A public report', json.dumps(followup.inputs))
        self.assertEqual(len(state.sources), 4)

    def test_attachment_content_is_not_sent_without_consent_and_revocation_hides_old_answers(self):
        state = Workspace(); file = Attachment('private.csv', b'name,amount\nPRIVATE_ROW,19\n')
        state.add_files([file])
        model = ScriptedModel([outline(),('inspect_file',{'file_id':file.id}),finish()])
        run_agent_turn(state,'分析欄位',openai_key='openai-private',model_call=model)
        self.assertNotIn('PRIVATE_ROW',json.dumps(model.inputs))
        self.assertFalse(state.sources[0]['content_shared'])
        model2 = ScriptedModel([outline(),('inspect_file',{'file_id':file.id}),
                                finish('資料包含 PRIVATE_ROW [S1]')])
        run_agent_turn(state,'再讀內文',openai_key='openai-private',allow_file_ai=True,model_call=model2)
        self.assertIn('PRIVATE_ROW',json.dumps(model2.inputs))
        model3 = ScriptedModel([outline(),('ask_user',{'question':'你想比較哪一項？'})])
        out = run_agent_turn(state,'接著比較',openai_key='openai-private',allow_file_ai=False,model_call=model3)
        self.assertNotIn('PRIVATE_ROW',json.dumps(model3.inputs))
        self.assertEqual(out['status'],'needs_input')
        self.assertIn('再讀內文',json.dumps(model3.inputs,ensure_ascii=False))

    def test_unknown_url_training_and_extra_credentials_never_execute(self):
        state=Workspace(); reg=build_registry(); calls=[]
        reg._capabilities['csv.train']=Capability('csv.train','test',lambda c,p:calls.append(p))
        executor=Executor(state, registry=reg)
        executor.dispatch('outline_task',{'steps':['inspect']})
        with self.assertRaises(WorkspaceError):
            executor.dispatch('read_web',{'url':'https://invented.example/secret'})
        with self.assertRaises(WorkspaceError):
            executor.dispatch('csv.train',{'target':'amount'})
        with self.assertRaises(WorkspaceError):
            executor.dispatch('read_web',{'url':'https://example.org','api_key':'leak'})
        self.assertEqual(calls,[])
        model=ScriptedModel([('csv.train',{'target':'y'})]*MAX_ACTIONS)
        result=run_agent_turn(state,'訓練這份資料',openai_key='openai-private',model_call=model,registry=reg)
        self.assertEqual(result['status'],'step_limit')
        self.assertEqual(len(state.trace),MAX_ACTIONS)
        self.assertEqual(calls,[])

    def test_hallucinated_citation_is_rejected_and_model_can_correct_it(self):
        state=Workspace(); file=Attachment('data.csv',b'x,y\n1,a\n2,b\n');state.add_files([file])
        model=ScriptedModel([outline(),('inspect_file',{'file_id':file.id}),
                             finish('錯誤編號 [S99]',['S99']),finish('根據欄位概況 [S1]')])
        out=run_agent_turn(state,'分析資料',openai_key='openai-private',model_call=model)
        self.assertEqual(out['status'],'completed')
        self.assertEqual(state.trace[-2]['status'],'unavailable')
        self.assertEqual(out['citations'],['S1'])

    def test_model_failure_preserves_real_sources_and_cannot_claim_completion(self):
        state=Workspace();file=Attachment('data.csv',b'x,y\n1,a\n2,b\n');state.add_files([file])
        model=ScriptedModel([outline(),('inspect_file',{'file_id':file.id}),ModelError('provider secret')])
        out=run_agent_turn(state,'分析資料',openai_key='openai-private',model_call=model)
        self.assertEqual(out['status'],'partial')
        self.assertEqual(len(state.sources),1)
        self.assertNotIn('provider secret',json.dumps(snapshot(state)))

    def test_no_key_mode_combines_csv_and_subtitles_and_keeps_conversation(self):
        state=Workspace();state.add_files([Attachment('a.csv',b'x,y\n1,a\n2,b\n'),
                                           Attachment('captions.srt',b'1\n00:00:01 --> 00:00:02\nHello\n')])
        result=collect_turn(state,'整理這兩份檔案')
        self.assertEqual(result['status'],'completed')
        self.assertEqual({s['kind'] for s in state.sources},{'csv','subtitles'})
        self.assertEqual(len(state.sources),2)
        collect_turn(state,'接著看看欄位')
        self.assertEqual(len(state.sources),2)
        self.assertEqual(state.turn,2)
        self.assertEqual(state.objective,'整理這兩份檔案')
        self.assertEqual(len(state.messages),4)
        self.assertIn('Hello',state.sources[1]['local_data']['text'])

    def test_training_proposal_is_read_only_and_validates_target(self):
        state=Workspace();file=Attachment('data.csv',b'x,y\n1,a\n2,b\n');state.add_files([file])
        executor=Executor(state)
        executor.dispatch('outline_task',{'steps':['inspect']})
        executor.dispatch('inspect_file',{'file_id':file.id})
        out=executor.dispatch('propose_training',{'file_id':file.id,'target':'y','time_column':'','forecast_intent':False})
        self.assertEqual(out['suggested_options']['target'],'y')
        self.assertEqual(state.records[-1]['kind'],'training_plan')
        self.assertNotIn('bundle',out)
        self.assertIn('未訓練',out['next_step'])

    def test_private_destinations_are_unavailable_before_any_get(self):
        state=Workspace();executor=Executor(state,known_urls=['http://127.0.0.1/data'])
        executor.dispatch('outline_task',{'steps':['read']})
        with patch('agent_modules.web_crawler._get') as network:
            result=executor.dispatch('read_web',{'url':'http://127.0.0.1/data'})
            network.assert_not_called()
        self.assertEqual(result['status'],'unavailable')

    def test_disabled_network_cannot_be_overridden_by_a_model(self):
        state=Workspace();reg=build_registry()
        executor=Executor(state,registry=reg,allow_web=False,brave_key='brave-private',
                          known_urls=['https://example.org'])
        with patch('agent_modules.research_tools.search') as network:
            for name,args in [('search_web',{'query':'report','freshness':''}),
                              ('read_web',{'url':'https://example.org'}),
                              ('analyze_stock',{'symbol':'2330','months':6})]:
                with self.assertRaises(WorkspaceError): executor.dispatch(name,args)
            network.assert_not_called()

    def test_public_pdf_and_publication_metadata_use_actual_sources(self):
        from pypdf import PdfWriter
        from agent_modules.document_media import public_pdf
        from agent_modules.web_crawler import _Extractor
        writer=PdfWriter();writer.add_blank_page(width=200,height=200);buf=io.BytesIO();writer.write(buf)
        with patch('agent_modules.web_crawler._destination'), \
             patch('agent_modules.web_crawler._robots_allowed',return_value=True), \
             patch('agent_modules.web_crawler._get',return_value=('https://example.org/a.pdf',buf.getvalue(),'application/pdf',200)):
            report=public_pdf(AgentContext(),{'url':'https://example.org/a.pdf'})
        self.assertEqual(report['pages'],1)
        parser=_Extractor();parser.feed('<meta property="article:published_time" content="2026-10-01"><p>text</p>')
        self.assertEqual(parser.published_at,'2026-10-01')

    def test_file_and_instruction_limits(self):
        state=Workspace()
        with self.assertRaises(WorkspaceError):
            state.add_files([Attachment(str(i)+'.csv',b'x\n1\n') for i in range(7)])
        self.assertEqual(state.attachments,{})
        with self.assertRaises(WorkspaceError):
            collect_turn(state,'sk-'+'a'*25)
        with self.assertRaises(WorkspaceError):
            run_agent_turn(state,'分析資料',openai_key='')


class ModelTransportTests(unittest.TestCase):
    def test_strict_response_tools_and_no_saved_response(self):
        seen={}
        class Response(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self,*args): self.close()
        class Opener:
            def open(self,req,timeout):
                seen['body']=json.loads(req.data);seen['url']=req.full_url;seen['timeout']=timeout
                return Response(b'{"status":"completed","output":[]}')
        from agent_workspace import tool_specs
        with patch('agent_llm.request.build_opener',return_value=Opener()):
            respond('openai-private','instructions',[{'role':'user','content':'test'}],tool_specs())
        self.assertFalse(seen['body']['store'])
        self.assertFalse(seen['body']['parallel_tool_calls'])
        self.assertEqual(seen['body']['tool_choice'], 'required')
        self.assertEqual(seen['body']['model'], 'gpt-6-luna')
        self.assertEqual(seen['body']['reasoning']['effort'], 'none')
        self.assertNotIn('openai-private',json.dumps(seen['body']))
        self.assertTrue(all(t['strict'] and not t['parameters']['additionalProperties'] for t in seen['body']['tools']))
        with self.assertRaises(ModelError):
            NoRedirect().redirect_request(None,None,302,'redirect',{},'https://evil.example')

    def test_rate_limit_error_does_not_expose_response_body(self):
        with patch('agent_llm.request.build_opener') as opener:
            opener.return_value.open.side_effect=error.HTTPError('https://api.openai.com',429,'SECRET',{},None)
            with self.assertRaises(ModelError) as caught:
                respond('openai-private','test',[],[])
            self.assertNotIn('SECRET',str(caught.exception))


class ConversationUITests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file(str(ROOT/'pages/0_AI_Workspace.py'),default_timeout=30).run()
        app.radio(key='workspace_mode').set_value('對話與多來源 Agent').run()
        return app

    def test_mode_is_clear_without_key_and_existing_files_can_be_reused(self):
        app=self.app()
        self.assertFalse(app.exception)
        self.assertFalse(app.checkbox(key='conversation_use_ai').value)
        state=Workspace();state.add_files([Attachment('a.csv',b'x,y\n1,a\n2,b\n')])
        app.session_state['conversation_workspace']=state
        app.text_area(key='conversation_goal_0').set_value('整理已提供資料').run()
        app.button(key='conversation_start').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['conversation_workspace'].sources),1)
        self.assertTrue(app.chat_input)
        app.chat_input[0].set_value('接著查看').run()
        self.assertEqual(app.session_state['conversation_workspace'].turn,2)
        self.assertEqual(len(app.session_state['conversation_workspace'].sources),1)
        app.button(key='conversation_new').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state['conversation_workspace'].sources)

    def test_ai_mode_missing_key_is_explicit(self):
        app=self.app()
        app.checkbox(key='conversation_use_ai').check().run()
        app.text_area(key='conversation_goal_0').set_value('請分析資料').run()
        app.button(key='conversation_start').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertIn('OpenAI',app.error[0].value)


if __name__=='__main__':
    unittest.main()
