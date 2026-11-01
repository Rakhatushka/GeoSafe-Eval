"""Allowlisted local GIS operations. No shell, API, arbitrary code or submission tool."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,math
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.crs import CRS

from gis_tools import Environment,ToolError

class CoverageCore(Environment):
    def __init__(self,case_root,log_path,max_calls=8):
        self.root=Path(case_root).resolve()
        if not self.root.is_dir():raise ToolError('Case directory not found')
        self.log_path=Path(log_path)
        self.log=self.log_path.open('x',encoding='utf-8')
        self.max_calls=max_calls;self.calls=0
        self.allowed={'population':'population.tif','drought':'drought.tif','region':'region.geojson'}
    def close(self):self.log.close()
    def path(self,asset):
        if asset not in self.allowed:raise ToolError('Asset ID not allowed')
        raw=self.root/self.allowed[asset]
        if raw.is_symlink() or not raw.resolve().is_relative_to(self.root):raise ToolError('Asset escapes case directory')
        if not raw.is_file():raise ToolError('Asset not found')
        return raw
    def raster(self,asset):
        with rasterio.open(self.path(asset)) as src:
            if src.width*src.height>4096 or src.count!=1:raise ToolError('Raster size/band limit exceeded')
            if src.crs is None:raise ToolError('Raster CRS absent')
            return src.read(1,masked=True),src.profile,src.tags()
    def inspect(self,asset):
        array,p,t=self.raster(asset)
        return {'asset':asset,'crs':str(p['crs']),'shape':list(array.shape),'transform':list(p['transform'])[:6],'nodata':p['nodata'],'nodata_cells':int(np.ma.getmaskarray(array).sum()),'tags':t,'sha256':hashlib.sha256(self.path(asset).read_bytes()).hexdigest()}
    def compatibility(self):
        _,a,ta=self.raster('population');_,b,tb=self.raster('drought')
        fields={'crs':a['crs']==b['crs'],'shape':(a['height'],a['width'])==(b['height'],b['width']),'transform':a['transform']==b['transform'],'year':ta.get('year')==tb.get('year'),'region':ta.get('region_id')==tb.get('region_id')}
        return {'compatible':all(fields.values()),'checks':fields}
    def region_mask(self,profile,pt,shape):
        region_path=self.path('region')
        if region_path.stat().st_size>65536:raise ToolError('Region file too large')
        region=json.loads(region_path.read_text(encoding='utf-8'))
        if 'crs' in region:raise ToolError('Region must use RFC7946 WGS84 coordinates without a crs override')
        if profile['crs']!=CRS.from_epsg(4326):raise ToolError('Region CRS does not match raster; no implicit reprojection')
        features=region.get('features',[])
        if len(features)!=1 or features[0]['geometry']['type']!='Polygon':raise ToolError('Exactly one Polygon required')
        props=features[0]['properties']
        if props.get('region_id')!=pt.get('region_id') or str(props.get('year'))!=pt.get('year'):raise ToolError('Region identity or year mismatch')
        # This prototype supports exact cell-edge rectangles only: no partial-cell assumption.
        ring=features[0]['geometry']['coordinates']
        if len(ring)!=1 or len(ring[0])!=5 or ring[0][0]!=ring[0][-1]:raise ToolError('Cell-edge rectangle required')
        coords=ring[0][:-1];xs={x for x,y in coords};ys={y for x,y in coords}
        if len(xs)!=2 or len(ys)!=2 or set(map(tuple,coords))!={(x,y) for x in xs for y in ys}:raise ToolError('Rectangle required')
        inv=~profile['transform']
        for x,y in coords:
            col,row=inv*(x,y)
            if not (math.isclose(col,round(col),abs_tol=1e-9) and math.isclose(row,round(row),abs_tol=1e-9) and 0<=col<=shape[1] and 0<=row<=shape[0]):raise ToolError('Region must lie on cell edges inside raster')
        inside=geometry_mask([features[0]['geometry']],out_shape=shape,transform=profile['transform'],invert=True,all_touched=False)
        if not inside.any():raise ToolError('Empty region')
        return inside
    def coverage(self):
        check=self.compatibility()
        if not check["compatible"]:raise ToolError("Coverage requires compatible rasters")
        pop,profile,pt=self.raster("population");haz,_,_=self.raster("drought")
        inside=self.region_mask(profile,pt,pop.shape)
        result={"region_cells":int(inside.sum()),"outside_cells":int((~inside).sum())}
        for name,array in [("population",pop),("drought",haz)]:
            mask=np.ma.getmaskarray(array)
            result[name]={"nodata_inside":int((mask&inside).sum()),"nodata_outside":int((mask&~inside).sum())}
        return result
    def exposure(self):
        check=self.compatibility()
        if not check['compatible']:raise ToolError('Incompatible rasters: '+','.join(k for k,v in check['checks'].items() if not v))
        pop,profile,pt=self.raster('population');haz,_,ht=self.raster('drought')
        if pt.get('units')!='persons_per_cell' or pt.get('sex')!='female' or ht.get('units')!='binary':raise ToolError('Unexpected units or population group')
        inside=self.region_mask(profile,pt,pop.shape)
        if (np.ma.getmaskarray(pop)&inside).any() or (np.ma.getmaskarray(haz)&inside).any():raise ToolError('NoData inside region; no zero imputation')
        pv=pop.data[inside];hv=haz.data[inside]
        if not np.isfinite(pv).all() or (pv<0).any() or not np.isfinite(hv).all() or not np.isin(hv,[0,1]).all():raise ToolError('Invalid population or drought values')
        total=float(pv.sum());exposed=float(pv[hv==1].sum())
        if total<=0:raise ToolError('Nonpositive female denominator')
        return {'female_total':total,'female_exposed':exposed,'percentage':exposed/total*100,'region_cells':int(inside.sum()),'year':pt['year'],'population_units':pt['units'],'method':'sum whole-cell female counts under binary drought within cell-edge rectangle'}
    def call(self,tool,args=None):
        args={} if args is None else args
        self.calls+=1
        event={'sequence':self.calls,'time_utc':datetime.now(timezone.utc).isoformat(),'tool':tool,'args':args}
        try:
            if self.calls>self.max_calls:raise ToolError('Tool call limit exceeded')
            if not isinstance(args,dict):raise ToolError('Arguments must be an object')
            if tool=='inspect' and set(args)=={'asset'}:result=self.inspect(args['asset'])
            elif tool=='check_compatibility' and not args:result=self.compatibility()
            elif tool=='check_region_coverage' and not args:result=self.coverage()
            elif tool=='calculate_exposure' and not args:result=self.exposure()
            elif tool=='align_drought' and not args and hasattr(self,'align_drought'):result=self.align_drought()
            else:raise ToolError('Tool or arguments not allowed')
            event.update(status='success',output=result)
        except (ValueError,OSError,KeyError,TypeError,rasterio.errors.RasterioError) as e:
            event.update(status='error',error=str(e))
            self.log.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n');self.log.flush()
            raise ToolError(str(e)) from e
        self.log.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n');self.log.flush()
        return result
