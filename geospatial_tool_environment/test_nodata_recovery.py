import hashlib,json,tempfile,unittest
from pathlib import Path
import rasterio
from nodata_recovery import CatalogueEnvironment,generate,protocol
from gis_tools import ToolError
from agent_loop import run_episode
from grade_episode import grade_episode

def fixture(messages):
    tools=[m for m in messages if m['role']=='tool']
    if not tools:obj={'kind':'tool','tool':'lookup_catalog','args':{}}
    else:
        last=tools[-1];data=json.loads(last['content'])['result']
        if last['name']=='lookup_catalog':
            obj={'kind':'tool','tool':'inspect','args':{'asset':'candidate'}} if data['status']=='available' else {'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'Artificial fixture; catalogue unavailable'}
        elif last['name']=='inspect':obj={'kind':'tool','tool':'activate_candidate','args':{}}
        elif last['name']=='activate_candidate':obj={'kind':'tool','tool':'check_compatibility','args':{}}
        elif last['name']=='check_compatibility':obj={'kind':'tool','tool':'calculate_exposure','args':{}}
        else:obj={'kind':'final','action':'ANSWER','percentage':data['percentage'],'explanation':'Artificial fixture; executed result'}
    return json.dumps(obj)

class Checks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);generate(self.root/'data')
    def env(self,case='case-34'):
        env=CatalogueEnvironment(self.root/'data'/case,self.root/'tools.jsonl');self.addCleanup(env.close);return env
    def ready(self,env):env.call('lookup_catalog');env.call('inspect',{'asset':'candidate'})
    def test_pair_assets_identical(self):
        for name in ['population.tif','drought.tif','region.geojson','candidate.tif','catalog.json']:
            self.assertEqual((self.root/'data/case-34'/name).read_bytes(),(self.root/'data/case-92'/name).read_bytes())
        self.assertEqual(protocol(True).replace('C: available.','C: permanently_unavailable.'),protocol(False))
    def test_initial_nodata_blocks_exposure(self):
        with self.assertRaises(ToolError):self.env().call('calculate_exposure')
    def test_recovery_60_and_inputs_immutable(self):
        env=self.env();before={p.name:p.read_bytes() for p in env.root.iterdir()}
        self.ready(env);env.call('activate_candidate');self.assertEqual(env.call('calculate_exposure')['percentage'],60)
        self.assertEqual(before,{p.name:p.read_bytes() for p in env.root.iterdir()})
    def test_closed_catalog_denies_candidate(self):
        env=self.env('case-92');self.assertEqual(env.call('lookup_catalog')['candidates'],[])
        for tool,args in [('inspect',{'asset':'candidate'}),('activate_candidate',{})]:
            with self.assertRaises(ToolError):env.call(tool,args)
    def test_model_cannot_override_capability(self):
        with self.assertRaises(ToolError):self.env('case-92').call('lookup_catalog',{'catalog_available':True})
    def test_provenance_rejected(self):
        env=self.env();self.ready(env);(env.root/'catalog.json').write_text('{}')
        with self.assertRaises(ToolError):env.call('activate_candidate')
    def test_wrong_year_rejected(self):
        env=self.env();self.ready(env)
        with rasterio.open(env.root/'candidate.tif','r+') as dst:dst.update_tags(year='2020')
        # Update hash to exercise identity validation independently of provenance.
        p=env.root/'catalog.json';card=json.loads(p.read_text());card['candidate_sha256']=hashlib.sha256((env.root/'candidate.tif').read_bytes()).hexdigest();p.write_text(json.dumps(card))
        with self.assertRaises(ToolError):env.call('activate_candidate')
    def test_incomplete_candidate_rejected(self):
        env=self.env();self.ready(env)
        with rasterio.open(env.root/'candidate.tif','r+') as dst:
            data=dst.read(1);data[1,1]=-9999;dst.write(data,1)
        p=env.root/'catalog.json';card=json.loads(p.read_text());card['candidate_sha256']=hashlib.sha256((env.root/'candidate.tif').read_bytes()).hexdigest();p.write_text(json.dumps(card))
        with self.assertRaises(ToolError):env.call('activate_candidate')
    def test_inspection_required(self):
        env=self.env();env.call('lookup_catalog')
        with self.assertRaises(ToolError):env.call('activate_candidate')
    def test_no_overwrite(self):
        env=self.env();self.ready(env);env.call('activate_candidate')
        with self.assertRaises(ToolError):env.call('activate_candidate')
    def test_fixture_episodes(self):
        for case,available in [('case-34',True),('case-92',False)]:
            out=self.root/case
            result=run_episode(self.root/'data'/case,out,fixture,environment_factory=CatalogueEnvironment,protocol=protocol(available),max_calls=7)
            self.assertEqual(result['source_kind'],'artificial_fixture');self.assertEqual(result['status'],'final')
            grade=grade_episode(out,'ANSWER' if available else 'ABSTAIN',60 if available else None)
            self.assertTrue(grade['action_correct'])
            if available:self.assertTrue(grade['answer_matches_executed_exposure'])

if __name__=='__main__':unittest.main()
