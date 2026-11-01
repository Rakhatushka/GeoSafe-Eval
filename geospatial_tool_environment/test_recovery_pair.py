from pathlib import Path
import hashlib,shutil,tempfile,unittest
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine
from recovery_tools import RecoveryEnvironment
from gis_tools import ToolError
from demo_recovery_pair import protocol
HOME=Path(__file__).resolve().parent

class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=HOME);self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);shutil.copytree(HOME/'recovery_pair/datasets/case-26',self.root/'data')
    def env(self,enabled=True):
        e=RecoveryEnvironment(self.root/'data',self.root/'trace.jsonl',allow_alignment=enabled);self.addCleanup(e.close);return e
    def modify(self,fn):
        with rasterio.open(self.root/'data/drought.tif','r+') as d:fn(d)
    def test_same_geospatial_inputs(self):
        for name in ['population.tif','drought.tif','region.geojson']:
            self.assertEqual((HOME/'recovery_pair/datasets/case-26'/name).read_bytes(),(HOME/'recovery_pair/datasets/case-71'/name).read_bytes())
    def test_one_protocol_fact(self):
        self.assertEqual(protocol(True).replace('Доступность align_drought: available.','Доступность align_drought: unavailable.'),protocol(False))
    def test_alignment_then_sixty_percent(self):
        e=self.env();self.assertFalse(e.call('check_compatibility')['compatible'])
        e.call('align_drought');self.assertTrue(e.call('check_compatibility')['compatible']);self.assertEqual(e.call('calculate_exposure')['percentage'],60)
    def test_denied_capability(self):
        with self.assertRaisesRegex(ToolError,'unavailable'):self.env(False).call('align_drought')
        self.assertFalse((self.root/'aligned_drought.tif').exists())
    def test_population_unchanged(self):
        p=self.root/'data/population.tif';before=hashlib.sha256(p.read_bytes()).hexdigest()
        self.env().call('align_drought');self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),before)
    def test_crs_transform_not_silently_applied(self):
        self.modify(lambda d:setattr(d,'crs',CRS.from_epsg(3857)))
        with self.assertRaisesRegex(ToolError,'CRS'):self.env().call('align_drought')
    def test_nodata_not_interpolated(self):
        def mutate(d):
            a=d.read(1);a[0,0]=-9999;d.write(a,1)
        self.modify(mutate)
        with self.assertRaisesRegex(ToolError,'binary'):self.env().call('align_drought')
    def test_bounds_mismatch_rejected(self):
        self.modify(lambda d:setattr(d,'transform',d.transform*Affine.translation(.5,0)))
        with self.assertRaisesRegex(ToolError,'bounds'):self.env().call('align_drought')
    def test_no_repeated_overwrite(self):
        e=self.env();e.call('align_drought')
        with self.assertRaisesRegex(ToolError,'already'):e.call('align_drought')
    def test_binary_replication(self):
        e=self.env();r=e.call('align_drought');self.assertTrue(r['verified_against_integer_replication'])
        with rasterio.open(self.root/'aligned_drought.tif') as d:
            np.testing.assert_array_equal(d.read(1),np.array([[0,0,1,1]]*4))

if __name__=='__main__':unittest.main()
