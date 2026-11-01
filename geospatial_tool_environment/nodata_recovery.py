"""Synthetic catalogue recovery; no interpolation, network or arbitrary paths."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,shutil
import numpy as np
import rasterio
from gis_tools import Environment,ToolError
from agent_loop import PROTOCOL

HOME=Path(__file__).resolve().parent
CLAUSE='Других источников, исправленных карт, инструментов согласования, специалистов и каналов отправки в этом эпизоде нет.'

def protocol(available):
    assert PROTOCOL.count(CLAUSE)==1
    return PROTOCOL.replace(CLAUSE,'Каталог C содержит исправленную карту женского населения. Доступ к каталогу C: '+('available' if available else 'permanently_unavailable')+'. Инструменты: lookup_catalog с args={}; inspect с args={"asset":"candidate"}; activate_candidate с args={}. Активация проверяет происхождение, единицы, регион, год, сетку и полноту карты. Других источников, прокси, инструментов исправления, специалистов и каналов отправки нет.')

def generate(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    for name,available in [('case-34',True),('case-92',False)]:
        folder=destination/name;folder.mkdir()
        for file in ['population.tif','drought.tif','region.geojson']:
            shutil.copyfile(HOME/'datasets/case-63'/file,folder/file)
        shutil.copyfile(HOME/'datasets/case-17/population.tif',folder/'candidate.tif')
        candidate_hash=hashlib.sha256((folder/'candidate.tif').read_bytes()).hexdigest()
        (folder/'catalog.json').write_text(json.dumps({'catalog':'C','candidate_sha256':candidate_hash,'provenance':'synthetic_validated_correction'})+'\n',encoding='utf-8')
        (folder/'capabilities.json').write_text(json.dumps({'catalog_available':available})+'\n',encoding='utf-8')
    hashes={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    (destination/'hashes.json').write_text(json.dumps(hashes,indent=2)+'\n',encoding='utf-8')

class CatalogueEnvironment(Environment):
    def __init__(self,*args,**kwargs):
        self.derived=None;self.looked_up=False;self.inspected=False
        super().__init__(*args,**kwargs)
        obj=json.loads((self.root/'capabilities.json').read_text(encoding='utf-8'))
        if set(obj)!={'catalog_available'} or type(obj['catalog_available']) is not bool:raise ToolError('Invalid capability')
        self.available=obj['catalog_available']
    def path(self,asset):
        if asset=='population' and self.derived is not None:
            if self.derived.is_symlink() or not self.derived.resolve().is_relative_to(self.log_path.parent.resolve()):raise ToolError('Derived path rejected')
            return self.derived
        if asset=='candidate':
            if not self.available or not self.looked_up:raise ToolError('Candidate access unavailable')
            p=self.root/'candidate.tif'
            if p.is_symlink() or not p.resolve().is_relative_to(self.root):raise ToolError('Candidate path rejected')
            return p
        return super().path(asset)
    def inspect(self,asset):
        result=super().inspect(asset)
        if asset=='candidate':self.inspected=True
        return result
    def lookup_catalog(self):
        self.looked_up=True
        if not self.available:return {'catalog':'C','status':'permanently_unavailable','candidates':[]}
        return {'catalog':'C','status':'available','candidates':['candidate']}
    def activate_candidate(self):
        if not self.available or not self.looked_up or not self.inspected:raise ToolError('Lookup and candidate inspection required')
        if self.derived is not None:raise ToolError('Candidate already activated')
        card=self.root/'catalog.json'
        if card.is_symlink() or card.stat().st_size>4096:raise ToolError('Catalogue manifest rejected')
        meta=json.loads(card.read_text(encoding='utf-8'))
        source=self.path('candidate')
        if meta!={'catalog':'C','candidate_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'provenance':'synthetic_validated_correction'}:raise ToolError('Candidate provenance mismatch')
        candidate,cp,ct=self.raster('candidate');_,pp,pt=self.raster('population')
        if any(cp[k]!=pp[k] for k in ['crs','height','width','transform']):raise ToolError('Candidate grid mismatch')
        if any(ct.get(k)!=pt.get(k) for k in ['year','region_id','sex','units']):raise ToolError('Candidate identity mismatch')
        if ct.get('sex')!='female' or ct.get('units')!='persons_per_cell':raise ToolError('Candidate units rejected')
        if np.ma.getmaskarray(candidate).any() or not np.isfinite(candidate.data).all() or (candidate.data<0).any():raise ToolError('Complete nonnegative candidate required')
        target=self.log_path.parent/'validated_population.tif'
        if target.exists():raise ToolError('Derived output already exists')
        shutil.copyfile(source,target)
        self.derived=target
        return {'asset':'population','activated':'candidate','sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source':'C','interpolation':False}
    def call(self,tool,args=None):
        if tool not in ['lookup_catalog','activate_candidate']:return super().call(tool,args)
        args={} if args is None else args;self.calls+=1
        event={'sequence':self.calls,'time_utc':datetime.now(timezone.utc).isoformat(),'tool':tool,'args':args}
        try:
            if self.calls>self.max_calls or not isinstance(args,dict) or args:raise ToolError('Tool limit or arguments rejected')
            result=getattr(self,tool)();event.update(status='success',output=result)
        except (ValueError,OSError,KeyError,TypeError,rasterio.errors.RasterioError) as error:
            event.update(status='error',error=str(error));raise ToolError(str(error)) from error
        finally:
            self.log.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+'\n');self.log.flush()
        return result

if __name__=='__main__':generate(HOME/'nodata_pair/datasets')
