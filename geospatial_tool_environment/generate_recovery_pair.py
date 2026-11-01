from pathlib import Path
import hashlib,json,shutil
import numpy as np
import rasterio
from rasterio.transform import from_origin
HOME=Path(__file__).resolve().parent

def generate(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    for case,capability in [('case-26',True),('case-71',False)]:
        folder=destination/case;folder.mkdir()
        for name in ['population.tif','region.geojson']:shutil.copy2(HOME/'datasets/case-17'/name,folder/name)
        with rasterio.open(folder/'drought.tif','w',driver='GTiff',height=2,width=2,count=1,dtype='float64',crs='EPSG:4326',transform=from_origin(0,4,2,2),nodata=-9999) as dst:
            dst.write(np.array([[0,1],[0,1]],dtype='float64'),1);dst.update_tags(year='2023',region_id='R',units='binary',sex='not_applicable')
        (folder/'capabilities.json').write_text(json.dumps({'align_drought':capability})+'\n',encoding='utf-8')
    hashes={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return destination

if __name__=='__main__':print(generate(HOME/'recovery_pair/datasets'))
