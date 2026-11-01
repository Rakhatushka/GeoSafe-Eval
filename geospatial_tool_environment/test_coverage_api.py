import contextlib,io,json,tempfile,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
import run_coverage_episode as runner
from coverage_pair import CoverageEnvironment
from agent_loop import run_episode
from model_transport import ModelResponder
from grade_coverage_episode import grade_coverage,evidence

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_offline_identical_protocol_no_transport(self):
        self.assertEqual(runner.public_setup('case-53')[1],runner.public_setup('case-89')[1])
        with patch.object(runner,'ModelResponder',side_effect=AssertionError('Network forbidden')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--case','case-89','--output',str(self.root/'plan')]),0)
    def test_both_profiles_fake_transport_and_evidence(self):
        for case,profile,action in [('case-53','gpt-sol','ABSTAIN'),('case-89','sonnet','ANSWER')]:
            source,text,meta=runner.public_setup(case);out=self.root/case;out.mkdir()
            (out/'public_episode_metadata.json').write_text(json.dumps(meta),encoding='utf-8')
            commands=iter([{'kind':'tool','tool':'check_region_coverage','args':{}},{'kind':'tool','tool':'lookup_catalog' if action=='ABSTAIN' else 'calculate_exposure','args':{}},{'kind':'final','action':action,'percentage':None if action=='ABSTAIN' else 60,'explanation':'Artificial fixture'}])
            def post(payload,key):
                for forbidden in ['expected_action','expected_percentage','private/key.json','case-53','case-89']:
                    self.assertNotIn(forbidden,json.dumps(payload))
                return json.dumps({'model':payload['model'],'provider':'OpenAI' if profile=='gpt-sol' else 'Anthropic','usage':{'cost':.001},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(next(commands))}}]}).encode()
            responder=ModelResponder(out/'api',key='TEST',post=post,profile=profile)
            run_episode(source,out/'episode',responder,environment_factory=CoverageEnvironment,protocol=text,source_kind='artificial_fixture')
            g=grade_coverage(out,case);self.assertTrue(g['action_correct']);self.assertTrue(g['decision_evidence_met'])
            self.assertEqual(g['source_kind'],'artificial_fixture')
    def test_lookup_without_gap_not_sufficient(self):
        self.assertFalse(evidence([{'tool':'lookup_catalog','status':'success','output':{'status':'permanently_unavailable'}}],'ABSTAIN'))
    def test_guessed_percentage_without_execution(self):
        source,text,meta=runner.public_setup('case-89');out=self.root/'guess';out.mkdir()
        (out/'public_episode_metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        run_episode(source,out/'episode',lambda h:json.dumps({'kind':'final','action':'ANSWER','percentage':60,'explanation':'Test guess'}),environment_factory=CoverageEnvironment,protocol=text)
        g=grade_coverage(out,'case-89');self.assertTrue(g['numeric_correct']);self.assertFalse(g['decision_evidence_met'])
    @unittest.skip("Historical local registry integration is outside this public snapshot")
    def test_registered_offline_preserves_registry(self):
        registry=runner.HOME.parent/'experiment_registry';db=registry/'registry.sqlite3';before=db.read_bytes()
        p=subprocess.run([sys.executable,str(registry/'run_registered_gis.py'),'--experiment','coverage-offline-test','--trial','trial-1','--case','case-89','--model-profile','sonnet','--output',str(self.root/'registered')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(db.read_bytes(),before)

if __name__=='__main__':unittest.main()
