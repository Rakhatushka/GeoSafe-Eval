import json,tempfile,unittest,urllib.error
from pathlib import Path
from model_transport import ModelResponder,TransportError,wire_messages
from agent_loop import run_episode
from grade_episode import grade_episode

HOME=Path(__file__).resolve().parent
def response(text,model='openai/gpt-6.1-sol',provider='OpenAI',cost=.001,stop='stop'):
    return json.dumps({'model':model,'provider':provider,'usage':{'cost':cost},'choices':[{'finish_reason':stop,'message':{'content':text}}]}).encode()

class TransportChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.calls=[]
    def make(self,post,**kwargs):return ModelResponder(self.root/'api',key='LOCAL_FIXTURE_SECRET',post=post,**kwargs)
    def test_payload_and_secret_separation(self):
        def post(p,k):self.calls.append(p);return response('{"kind":"tool","tool":"check_compatibility","args":{}}')
        m=self.make(post);m([{'role':'user','content':'fixture'}])
        p=self.calls[0];self.assertFalse(p['provider']['allow_fallbacks']);self.assertEqual(p['provider']['only'],['openai'])
        for f in (self.root/'api').glob('*'):
            self.assertNotIn('LOCAL_FIXTURE_SECRET',f.read_text())
    def test_wire_does_not_use_unmatched_native_tool_messages(self):
        wire=wire_messages([{'role':'tool','name':'inspect','content':'{"status":"success"}'}])
        self.assertEqual(wire[1]['role'],'user');self.assertIn('HOST_TOOL_RESULT',wire[1]['content'])
    def test_http_no_retry(self):
        def post(*args):self.calls.append(1);raise urllib.error.HTTPError('https://openrouter.ai',404,'fixture',{},None)
        m=self.make(post)
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
        self.assertEqual(len(self.calls),1);self.assertTrue(m.unknown_charge)
    def test_wrong_model_stops(self):
        m=self.make(lambda *a:response('{}',model='other/model'))
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
    def test_incomplete_stops(self):
        m=self.make(lambda *a:response('{}',stop='length'))
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
    def test_missing_cost_stops(self):
        m=self.make(lambda *a:json.dumps({'model':'openai/gpt-6.1-sol'}).encode())
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
        self.assertTrue(m.unknown_charge)
    def test_observed_budget_stops_next_call(self):
        def post(*args):self.calls.append(1);return response('{}',cost=.02)
        m=self.make(post,max_usd='.01');m([{'role':'user','content':'fixture'}])
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
        self.assertEqual(len(self.calls),1)
    def test_request_cap(self):
        m=self.make(lambda *a:response('{}'),max_requests=1);m([{'role':'user','content':'fixture'}])
        with self.assertRaises(TransportError):m([{'role':'user','content':'fixture'}])
    def test_entire_loop_with_fake_transport_and_real_gis(self):
        outputs=[{'kind':'tool','tool':'inspect','args':{'asset':'population'}},{'kind':'tool','tool':'inspect','args':{'asset':'drought'}},{'kind':'tool','tool':'check_compatibility','args':{}},{'kind':'tool','tool':'calculate_exposure','args':{}},{'kind':'final','action':'ANSWER','percentage':60,'explanation':'Artificial transport fixture'}]
        def post(payload,key):
            self.calls.append(payload)
            return response(json.dumps(outputs[len(self.calls)-1]))
        m=self.make(post)
        # This remains explicitly a software fixture despite exercising the API adapter.
        result=run_episode(HOME/'datasets/case-17',self.root/'episode',m,source_kind='artificial_fixture')
        self.assertEqual(result['status'],'final');self.assertEqual(len(self.calls),5)
        self.assertTrue(grade_episode(self.root/'episode','ANSWER',60)['answer_matches_executed_exposure'])
        self.assertNotIn('expected_percentage',json.dumps(self.calls));self.assertNotIn('scoring_key',json.dumps(self.calls))
    def test_transport_failure_recorded_in_episode(self):
        def fail(*a):raise TimeoutError('fixture')
        m=self.make(fail)
        result=run_episode(HOME/'datasets/case-17',self.root/'episode',m)
        self.assertEqual(result['status'],'responder_error');self.assertIsNone(result['final'])

if __name__=='__main__':unittest.main()
