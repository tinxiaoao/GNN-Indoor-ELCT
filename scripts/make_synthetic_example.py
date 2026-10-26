"""Create an author-independent two-room interface example; this is not GNN output."""
from pathlib import Path
import argparse, hashlib, json, os
import numpy as np
from PIL import Image

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    wall=np.zeros((160,220),dtype=np.uint8)
    wall[10:150,10:210]=2
    wall[20:140,20:105]=3
    wall[20:140,115:200]=4
    icon=np.zeros_like(wall)
    icon[65:95,105:115]=2
    icon[10:20,40:75]=1
    palette=[v for i in range(256) for v in (i,(i*37)%256,(i*83)%256)]
    maps={}
    for name,arr in [('wall',wall),('icon',icon),('rough',wall)]:
        img=Image.fromarray(arr,mode='P');img.putpalette(palette)
        path=out/(name+'.png');img.save(path)
        maps[name]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'width':220,'height':160}
    config={'schema_version':1,'building':'synthetic_two_rooms','sample_id':'synthetic_two_rooms',
            'input_source_type':'unknown','provenance':'New synthetic semantic maps. Not a dataset sample or GNN prediction.',
            'maps':maps,'extraction':{'mode':'none','lightweight':False},
            'outputs':{'directory':os.path.relpath(out.parent.parent/'runs/synthetic_two_rooms_none',out).replace('\\','/')}}
    (out/'case.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    print(out/'case.json')

if __name__=='__main__':main()
