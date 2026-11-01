from pathlib import Path
from functools import partial
import json,tempfile,unittest
from agent_loop import run_episode
from recovery_tools import RecoveryEnvironment
from demo_recovery_pair import fixture,protocol
from grade_recovery_episode import grade_recovery
from model_transport import ModelResponder

HOME=Path(__file__).resolve().parent
class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def run_fixture(self,available=True,responder=fixture):
        case='case-26' if available else 'case-71'
        run_episode(HOME/'recovery_pair/datasets'/case,self.root/'episode',responder,environment_factory=partial(RecoveryEnvironment,allow_alignment=available),protocol=protocol(available))
        return case
    def test_success_trace_scored(self):
        self.run_fixture();g=grade_recovery(self.root/'episode','case-26')
        self.assertTrue(g['action_correct']);self.assertTrue(g['numeric_correct']);self.assertTrue(g['alignment_then_recheck_then_exposure'])
    def test_unavailable_correct_stop(self):
        self.run_fixture(False);g=grade_recovery(self.root/'episode','case-71')
        self.assertTrue(g['action_correct']);self.assertFalse(g['alignment_executed']);self.assertTrue(g['recovery_trace_requirement_met'])
    def test_guess_not_trace_grounded(self):
        self.run_fixture(responder=lambda _:json.dumps({'kind':'final','action':'ANSWER','percentage':60,'explanation':'fixture guess'}))
        g=grade_recovery(self.root/'episode','case-26');self.assertTrue(g['numeric_correct']);self.assertFalse(g['recovery_trace_requirement_met'])
    def test_wrong_case_reference_rejected(self):
        self.run_fixture()
        with self.assertRaisesRegex(ValueError,'Protocol'):grade_recovery(self.root/'episode','case-71')
    def test_declared_capability_not_model_overridable(self):
        def responder(m):
            if len(m)==1:return json.dumps({'kind':'tool','tool':'align_drought','args':{'allow_alignment':True}})
            return json.dumps({'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'fixture'})
        self.run_fixture(False,responder)
        g=grade_recovery(self.root/'episode','case-71');self.assertFalse(g['alignment_executed']);self.assertEqual(g['tool_errors'],1)
    def test_fake_api_drives_real_recovery_without_private_data(self):
        commands=[{'kind':'tool','tool':'check_compatibility','args':{}},{'kind':'tool','tool':'align_drought','args':{}},{'kind':'tool','tool':'check_compatibility','args':{}},{'kind':'tool','tool':'calculate_exposure','args':{}},{'kind':'final','action':'ANSWER','percentage':60,'explanation':'fixture'}]
        calls=[]
        def post(p,key):
            self.assertNotIn('expected_action',json.dumps(p));self.assertNotIn('private/key',json.dumps(p))
            calls.append(p)
            return json.dumps({'model':'openai/gpt-6.1-sol','provider':'OpenAI','usage':{'cost':.001},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(commands[len(calls)-1])}}]}).encode()
        responder=ModelResponder(self.root/'api',key='FIXTURE',post=post,max_requests=8)
        self.run_fixture(True,responder);self.assertEqual(len(calls),5);self.assertTrue(grade_recovery(self.root/'episode','case-26')['recovery_trace_requirement_met'])

if __name__=='__main__':unittest.main()
