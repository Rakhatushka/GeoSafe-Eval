"""A deliberately narrow binary-hazard grid alignment, never population interpolation."""
from pathlib import Path
import hashlib,math
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.transform import array_bounds
from gis_tools import Environment,ToolError

class RecoveryEnvironment(Environment):
    def __init__(self,*args,allow_alignment=False,**kwargs):
        self.derived=None;self.allow_alignment=allow_alignment
        super().__init__(*args,**kwargs)
    def path(self,asset):
        if asset=='drought' and self.derived is not None:
            p=self.derived
            if p.is_symlink() or not p.resolve().is_relative_to(self.log_path.parent.resolve()):raise ToolError('Derived asset escapes episode')
            return p
        return super().path(asset)
    def align_drought(self):
        if not self.allow_alignment:raise ToolError('Alignment capability unavailable in this episode')
        if self.derived is not None:raise ToolError('Alignment already performed; derived file never overwritten')
        pop,pp,pt=self.raster('population');haz,hp,ht=self.raster('drought')
        if pp['crs']!=hp['crs']:raise ToolError('This tool does not transform between CRS')
        if pt.get('year')!=ht.get('year') or pt.get('region_id')!=ht.get('region_id'):raise ToolError('Identity/year mismatch')
        if ht.get('units')!='binary' or np.ma.getmaskarray(haz).any() or not np.isin(haz.data,[0,1]).all():raise ToolError('Complete binary hazard required')
        if not np.allclose(array_bounds(pop.shape[0],pop.shape[1],pp['transform']),array_bounds(haz.shape[0],haz.shape[1],hp['transform']),rtol=0,atol=1e-9):raise ToolError('Different raster bounds')
        if pp['transform'].b or pp['transform'].d or hp['transform'].b or hp['transform'].d:raise ToolError('Only north-up grids supported')
        fy=pop.shape[0]/haz.shape[0];fx=pop.shape[1]/haz.shape[1]
        if fx<1 or fy<1 or not fx.is_integer() or not fy.is_integer():raise ToolError('Only integer upsampling supported')
        destination=np.full(pop.shape,-9999.,dtype='float64')
        reproject(source=haz.data,destination=destination,src_transform=hp['transform'],src_crs=hp['crs'],dst_transform=pp['transform'],dst_crs=pp['crs'],src_nodata=-9999,dst_nodata=-9999,resampling=Resampling.nearest)
        expected=np.repeat(np.repeat(haz.data,int(fy),axis=0),int(fx),axis=1)
        if not np.array_equal(destination,expected):raise ToolError('Nearest alignment verification failed')
        path=self.log_path.parent/'aligned_drought.tif'
        if path.exists():raise ToolError('Derived output already exists')
        with rasterio.open(path,'w',**pp) as dst:
            dst.write(destination,1);dst.update_tags(**ht)
        self.derived=path
        return {'asset':'drought','method':'nearest_binary_integer_upsampling','shape':list(destination.shape),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'population_modified':False,'verified_against_integer_replication':True}
