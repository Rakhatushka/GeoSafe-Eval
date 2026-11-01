"""Deterministic tiny synthetic rasters, no observations of real people."""
from pathlib import Path
import hashlib,json
import numpy as np
import rasterio
from rasterio.transform import from_origin

HOME=Path(__file__).resolve().parent

def generate(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    region={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'region_id':'R','year':2023},'geometry':{'type':'Polygon','coordinates':[[[1,1],[3,1],[3,3],[1,3],[1,1]]]}}]}
    population=np.array([[0,0,0,0],[0,100,200,0],[0,300,400,0],[0,0,0,0]],dtype='float64')
    drought=np.array([[0,0,0,0],[0,0,1,0],[0,0,1,0],[0,0,0,0]],dtype='float64')
    names=['case-17','case-42','case-63','case-85']
    for i,name in enumerate(names):
        folder=destination/name;folder.mkdir()
        (folder/'region.geojson').write_text(json.dumps(region,sort_keys=True)+'\n',encoding='utf-8')
        pop=population.copy()
        if i==2:pop[1,2]=-9999
        if i==3:
            pop[0,:]=pop[-1,:]=pop[:,0]=pop[:,-1]=-9999
        for filename,values in [('population.tif',pop),('drought.tif',drought)]:
            crs='EPSG:3857' if i==1 and filename=='drought.tif' else 'EPSG:4326'
            transform=from_origin(0,4000,1000,1000) if crs=='EPSG:3857' else from_origin(0,4,1,1)
            with rasterio.open(folder/filename,'w',driver='GTiff',height=4,width=4,count=1,dtype='float64',crs=crs,transform=transform,nodata=-9999) as dst:
                dst.write(values,1)
                dst.update_tags(year='2023',region_id='R',units='persons_per_cell' if filename=='population.tif' else 'binary',sex='female' if filename=='population.tif' else 'not_applicable')
    hashes={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')
    return names

if __name__=='__main__':
    print(generate(HOME/'datasets'))
