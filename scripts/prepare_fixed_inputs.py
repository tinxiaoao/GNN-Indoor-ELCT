"""Copy only manifest-bound local maps; no download, inference or rights grant."""
from pathlib import Path
import argparse, hashlib, json, os, shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True,help='Locally authorized source tree containing the listed code/ files.')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parents[1]/'experiments/fixed_inputs.json')
    args=parser.parse_args();root=args.source_root.resolve();out=args.out.resolve()
    if out.exists():raise FileExistsError('Use a new output directory')
    spec=json.loads(args.manifest.read_text(encoding='utf-8'))
    plan=[];cases=[]
    for item in spec['cases']:
        case={k:item[k] for k in ['name','sample_id','source_type','family','level','seed','sha256','modes']}
        for field in ['wall','icon','rough']:
            source=(root/item['source_paths'][field]).resolve()
            if not source.is_relative_to(root):raise ValueError('Source path escapes source root')
            if sha(source)!=item['sha256'][field]:raise ValueError('Input hash mismatch: '+item['name']+'/'+field)
            rel=Path('maps')/item['name']/(field+'.png')
            plan.append((source,out/rel));case[field]=rel.as_posix()
        cases.append(case)
    out.mkdir(parents=True)
    for src,dst in plan:
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    payload={'note':'Fixed historical maps, annotation-derived; no GNN inference. No correction reads a clean reference.','cases':cases}
    (out/'cases.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(out/'cases.json')
if __name__=='__main__':main()
