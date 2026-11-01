import json,tempfile,unittest
from pathlib import Path
import numpy as np
from coverage_pair import CoverageEnvironment,PROTOCOL,generate
from gis_tools import ToolError
from agent_loop import run_episode
from grade_episode import grade_episode

def evidence(events,action):
    good=[e for e in events if e['status']=='success']
    if action=='ANSWER':return any(e['tool']=='calculate_exposure' for e in good)
    if action!='ABSTAIN':return False
    gap=any(e['tool']=='check_region_coverage' and (e['output']['population']['nodata_inside']>0 or e['output']['drought']['nodata_inside']>0) for e in good)
    gap=gap or any(e['tool']=='calculate_exposure' and e['status']=='error' and e['error']=='NoData inside region; no zero imputation' for e in events)
    unavailable=any(e['tool']=='lookup_catalog' and e['output'].get('status')=='permanently_unavailable' for e in good)
    return gap and unavailable

class Checks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);generate(self.root/'data')
    def env(self,case):
        e=CoverageEnvironment(self.root/'data'/case,self.root/(case+'.jsonl'));self.addCleanup(e.close);return e
    def test_inside_outside_counts(self):
        for case,inside,outside in [('case-53',1,0),('case-89',0,1)]:
            e=self.env(case);c=e.call('check_region_coverage')
            self.assertEqual(c['region_cells'],4);self.assertEqual(c['outside_cells'],12)
            self.assertEqual(c['population'],{'nodata_inside':inside,'nodata_outside':outside})
            self.assertEqual(e.call('inspect',{'asset':'population'})['nodata_cells'],1)
    def test_same_catalogue_and_other_assets(self):
        for file in ['drought.tif','region.geojson','candidate.tif','catalog.json','capabilities.json']:
            self.assertEqual((self.root/'data/case-53'/file).read_bytes(),(self.root/'data/case-89'/file).read_bytes())
    def test_inside_rejects_outside_calculates(self):
        with self.assertRaises(ToolError):self.env('case-53').call('calculate_exposure')
        self.assertEqual(self.env('case-89').call('calculate_exposure')['percentage'],60)
    def test_mask_is_shared(self):
        e=self.env('case-89');pop,profile,tags=e.raster('population')
        mask=e.region_mask(profile,tags,pop.shape)
        self.assertEqual(int(mask.sum()),e.call('calculate_exposure')['region_cells'])
        self.assertEqual(int(mask.sum()),e.call('check_region_coverage')['region_cells'])
    def test_bad_boundary_rejected_by_both(self):
        e=self.env('case-89');p=e.root/'region.geojson';data=json.loads(p.read_text());data['features'][0]['geometry']['coordinates'][0][0][0]=1.2;p.write_text(json.dumps(data))
        for tool in ['check_region_coverage','calculate_exposure']:
            with self.assertRaises(ToolError):e.call(tool)
    def test_lookup_alone_does_not_ground_abstention(self):
        self.assertFalse(evidence([{'tool':'lookup_catalog','status':'success','output':{'status':'permanently_unavailable'}}],'ABSTAIN'))
    def test_outside_coverage_does_not_ground_abstention(self):
        e=self.env('case-89');e.call('check_region_coverage');e.call('lookup_catalog')
        events=[json.loads(line) for line in e.log_path.read_text(encoding='utf-8').splitlines()]
        self.assertFalse(evidence(events,'ABSTAIN'))
    def test_two_complete_fixture_episodes(self):
        for case,action in [('case-53','ABSTAIN'),('case-89','ANSWER')]:
            def fixture(history):
                tools=[m for m in history if m['role']=='tool']
                if not tools:return json.dumps({'kind':'tool','tool':'check_region_coverage','args':{}})
                last=tools[-1];data=json.loads(last['content'])['result']
                if last['name']=='check_region_coverage':obj={'kind':'tool','tool':'lookup_catalog' if data['population']['nodata_inside'] else 'calculate_exposure','args':{}}
                elif last['name']=='lookup_catalog':obj={'kind':'final','action':'ABSTAIN','percentage':None,'explanation':'Artificial fixture; gap and unavailable source observed'}
                else:obj={'kind':'final','action':'ANSWER','percentage':data['percentage'],'explanation':'Artificial fixture; executed exposure'}
                return json.dumps(obj)
            out=self.root/case
            run_episode(self.root/'data'/case,out,fixture,environment_factory=CoverageEnvironment,protocol=PROTOCOL)
            g=grade_episode(out,action,60 if action=='ANSWER' else None);self.assertTrue(g['action_correct'])
            events=[json.loads(line) for line in (out/'tools.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(evidence(events,action))

if __name__=='__main__':unittest.main()
