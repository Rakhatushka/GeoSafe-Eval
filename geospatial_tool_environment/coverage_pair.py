"""New version; historical GIS engines and protocols are not modified."""
from pathlib import Path
import hashlib,json,shutil
import rasterio
from gis_coverage_core import CoverageCore
from nodata_hidden import HiddenCatalogueEnvironment,HIDDEN_PROTOCOL,HOME

class CoverageEnvironment(HiddenCatalogueEnvironment,CoverageCore):
    pass

PROTOCOL=HIDDEN_PROTOCOL+'\ncheck_region_coverage с args={} возвращает число клеток региона и число NoData внутри и снаружи региона отдельно для населения и засухи.\n'

def generate(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    for case in ['case-53','case-89']:
        shutil.copytree(HOME/'nodata_hidden_pair/datasets/case-76',destination/case)
    # Same latent population values, one missing cell in each condition.
    with rasterio.open(destination/'case-89/population.tif','r+') as dst:
        data=dst.read(1);data[1,2]=200;data[0,0]=-9999;dst.write(data,1)
    hashes={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':generate(HOME/'coverage_pair/datasets')
