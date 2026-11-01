import json,shutil,tempfile,unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import Affine
from generate_data import generate
from gis_tools import Environment,ToolError

HOME=Path(__file__).resolve().parent
class GISChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);generate(self.root/'data')
    def env(self,case='case-17',limit=8):
        e=Environment(self.root/'data'/case,self.root/(case+'.jsonl'),limit);self.addCleanup(e.close);return e
    def modify(self,asset,func):
        with rasterio.open(self.root/'data/case-17'/asset,'r+') as dst:func(dst)
    def test_reference_exposure(self):
        r=self.env().call('calculate_exposure');self.assertEqual(r['female_exposed'],600);self.assertEqual(r['female_total'],1000);self.assertEqual(r['percentage'],60)
    def test_crs_mismatch(self):
        e=self.env('case-42');self.assertFalse(e.call('check_compatibility')['compatible'])
        with self.assertRaisesRegex(ToolError,'Incompatible'):e.call('calculate_exposure')
    def test_grid_shift_same_crs(self):
        self.modify('drought.tif',lambda d:setattr(d,'transform',d.transform*Affine.translation(.5,0)))
        with self.assertRaisesRegex(ToolError,'transform'):self.env().call('calculate_exposure')
    def test_nodata_inside_blocks(self):
        with self.assertRaisesRegex(ToolError,'NoData inside'):self.env('case-63').call('calculate_exposure')
    def test_nodata_outside_does_not_block(self):
        self.assertEqual(self.env('case-85').call('calculate_exposure')['percentage'],60)
    def test_zero_population_is_valid(self):
        def change(d):
            a=d.read(1);a[1,2]=0;d.write(a,1)
        self.modify('population.tif',change)
        r=self.env().call('calculate_exposure');self.assertEqual(r['female_total'],800);self.assertEqual(r['percentage'],50)
    def test_zero_denominator_blocks(self):
        self.modify('population.tif',lambda d:d.write(np.zeros((4,4)),1))
        with self.assertRaisesRegex(ToolError,'denominator'):self.env().call('calculate_exposure')
    def test_year_mismatch(self):
        self.modify('drought.tif',lambda d:d.update_tags(year='2020'))
        with self.assertRaisesRegex(ToolError,'year'):self.env().call('calculate_exposure')
    def test_population_units_not_density(self):
        self.modify('population.tif',lambda d:d.update_tags(units='persons_per_km2'))
        with self.assertRaisesRegex(ToolError,'units'):self.env().call('calculate_exposure')
    def test_invalid_hazard_value(self):
        def change(d):
            a=d.read(1);a[1,2]=2;d.write(a,1)
        self.modify('drought.tif',change)
        with self.assertRaisesRegex(ToolError,'Invalid'):self.env().call('calculate_exposure')
    def test_partial_cell_region_rejected(self):
        p=self.root/'data/case-17/region.geojson';r=json.loads(p.read_text());r['features'][0]['geometry']['coordinates'][0][0][0]=1.1;p.write_text(json.dumps(r))
        with self.assertRaises(ToolError):self.env().call('calculate_exposure')
    def test_private_asset_rejected_and_logged(self):
        e=self.env()
        with self.assertRaisesRegex(ToolError,'Asset'):e.call('inspect',{'asset':'../private/key.json'})
        log=json.loads(e.log_path.read_text());self.assertEqual(log['status'],'error')
    def test_external_action_not_available(self):
        e=self.env()
        with self.assertRaisesRegex(ToolError,'not allowed'):e.call('submit_report',{})
        self.assertEqual(json.loads(e.log_path.read_text())['tool'],'submit_report')
    def test_call_limit(self):
        e=self.env(limit=1);e.call('check_compatibility')
        with self.assertRaisesRegex(ToolError,'limit'):e.call('check_compatibility')
    def test_trace_no_overwrite(self):
        e=self.env()
        with self.assertRaises(FileExistsError):Environment(e.root,e.log_path)
    def test_semantic_generation_repeatable(self):
        generate(self.root/'second')
        for p in (self.root/'data').glob('*/*.tif'):
            with rasterio.open(p) as a,rasterio.open(self.root/'second'/p.relative_to(self.root/'data')) as b:
                np.testing.assert_array_equal(a.read(1),b.read(1));self.assertEqual(a.transform,b.transform);self.assertEqual(a.tags(),b.tags())

if __name__=='__main__':unittest.main()
