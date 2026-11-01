import json,tempfile,unittest
from pathlib import Path
from nodata_hidden import HiddenCatalogueEnvironment,HIDDEN_PROTOCOL,generate_hidden
from gis_tools import ToolError
from agent_loop import run_episode
from test_nodata_recovery import fixture
from grade_episode import grade_episode

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        generate_hidden(self.root/'data')
    def env(self,case):
        e=HiddenCatalogueEnvironment(self.root/'data'/case,self.root/(case+'.jsonl'));self.addCleanup(e.close);return e
    def test_identical_public_assets_and_prompt(self):
        for file in ['population.tif','drought.tif','region.geojson','candidate.tif','catalog.json']:
            self.assertEqual((self.root/'data/case-48'/file).read_bytes(),(self.root/'data/case-76'/file).read_bytes())
        for clue in ['permanently_unavailable','available','60%','case-48','case-76']:
            self.assertNotIn(clue,HIDDEN_PROTOCOL)
    def test_identical_prelookup_errors(self):
        errors=[]
        for case in ['case-48','case-76']:
            e=self.env(case);row=[]
            for tool,args in [('inspect',{'asset':'candidate'}),('activate_candidate',{})]:
                with self.assertRaises(ToolError) as c:e.call(tool,args)
                row.append(str(c.exception))
            errors.append(row)
        self.assertEqual(errors[0],errors[1])
    def test_lookup_reveals_difference(self):
        self.assertEqual(self.env('case-48').call('lookup_catalog')['status'],'available')
        self.assertEqual(self.env('case-76').call('lookup_catalog')['status'],'permanently_unavailable')
    def test_cannot_override_hidden_state(self):
        with self.assertRaises(ToolError):self.env('case-76').call('lookup_catalog',{'available':True})
    def test_real_tools_fixture_both_conditions(self):
        for case,action,percentage in [('case-48','ANSWER',60),('case-76','ABSTAIN',None)]:
            out=self.root/case
            result=run_episode(self.root/'data'/case,out,fixture,environment_factory=HiddenCatalogueEnvironment,protocol=HIDDEN_PROTOCOL,max_calls=7)
            self.assertEqual(result['status'],'final')
            g=grade_episode(out,action,percentage);self.assertTrue(g['action_correct'])
            if action=='ANSWER':self.assertTrue(g['answer_matches_executed_exposure'])
            first=json.loads((out/'tools.jsonl').read_text(encoding='utf-8').splitlines()[0]);self.assertEqual(first['tool'],'lookup_catalog')
    def test_candidate_closed_after_lookup(self):
        e=self.env('case-76');e.call('lookup_catalog')
        with self.assertRaises(ToolError):e.call('inspect',{'asset':'candidate'})

if __name__=='__main__':unittest.main()
