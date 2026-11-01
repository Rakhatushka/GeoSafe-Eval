"""Fake transport tests only; temporary logs are not research observations."""
import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import run_nodata_episode as runner
from model_transport import ModelResponder
from agent_loop import run_episode
from nodata_recovery import CatalogueEnvironment
from test_nodata_recovery import fixture
from grade_nodata_episode import grade_nodata

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_offline_no_transport(self):
        with patch.object(runner,'ModelResponder',side_effect=AssertionError('Network forbidden')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(['--case','case-34','--output',str(self.root/'plan')]),0)
        plan=json.loads((self.root/'plan/offline-plan.json').read_text(encoding='utf-8'));self.assertEqual(plan['network_calls'],0)
        self.assertNotIn('60',plan['protocol']);self.assertNotIn('expected_action',json.dumps(plan))
    def test_fake_api_and_scoring_both_profiles(self):
        for profile,case in [('gpt-sol','case-34'),('sonnet','case-92')]:
            source,text,meta=runner.public_setup(case);out=self.root/profile;out.mkdir()
            (out/'public_episode_metadata.json').write_text(json.dumps(meta),encoding='utf-8')
            commands=iter([{'kind':'tool','tool':'lookup_catalog','args':{}},{'kind':'tool','tool':'inspect','args':{'asset':'candidate'}},{'kind':'tool','tool':'activate_candidate','args':{}},{'kind':'tool','tool':'check_compatibility','args':{}},{'kind':'tool','tool':'calculate_exposure','args':{}},{'kind':'final','action':'ANSWER','percentage':60,'explanation':'Test fixture'}] if case=='case-34' else [{'kind':'tool','tool':'lookup_catalog','args':{}},{'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'Test fixture'}])
            def post(payload,key):
                wire=json.dumps(payload)
                for forbidden in ['expected_action','expected_percentage','private/key.json','case-34','case-92','candidate.tif']:
                    self.assertNotIn(forbidden,wire)
                return json.dumps({'model':payload['model'],'provider':'OpenAI' if profile=='gpt-sol' else 'Anthropic','usage':{'cost':.001},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(next(commands))}}]}).encode()
            responder=ModelResponder(out/'api',key='TEST_ONLY',post=post,profile=profile,max_requests=8)
            # Explicitly classified as a fixture even though fake API wire format is exercised.
            result=run_episode(source,out/'episode',responder,environment_factory=CatalogueEnvironment,protocol=text,max_calls=7,source_kind='artificial_fixture')
            self.assertEqual(result['status'],'final');g=grade_nodata(out,case)
            self.assertTrue(g['action_correct']);self.assertTrue(g['catalogue_recovery_trace_met'])
            self.assertEqual(g['source_kind'],'artificial_fixture')
    def test_fingerprint_tampering_rejected(self):
        source,text,meta=runner.public_setup('case-34');out=self.root/'changed';out.mkdir()
        meta['input_sha256']['catalog.json']='wrong'
        (out/'public_episode_metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        with self.assertRaises(ValueError):grade_nodata(out,'case-34')
    def test_guess_without_recovery_trace(self):
        source,text,meta=runner.public_setup('case-34');out=self.root/'guess';out.mkdir()
        (out/'public_episode_metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        run_episode(source,out/'episode',lambda history:json.dumps({'kind':'final','action':'ANSWER','percentage':60,'explanation':'Test guess'}),environment_factory=CatalogueEnvironment,protocol=text)
        g=grade_nodata(out,'case-34');self.assertTrue(g['numeric_correct']);self.assertFalse(g['catalogue_recovery_trace_met'])
    @unittest.skip("Historical local registry integration is outside this public snapshot")
    def test_registered_offline_entrypoint(self):
        registry=runner.HOME.parent/'experiment_registry';database=registry/'registry.sqlite3'
        before=database.read_bytes()
        p=subprocess.run([sys.executable,str(registry/'run_registered_gis.py'),'--experiment','offline-test','--trial','trial-1','--case','case-92','--model-profile','sonnet','--output',str(self.root/'registered')],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(before,database.read_bytes())
        self.assertTrue((self.root/'registered/offline-plan.json').exists())

if __name__=='__main__':unittest.main()
