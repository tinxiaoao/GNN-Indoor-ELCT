"""Local-only example preparation; assets are not distributed with the candidate."""
from pathlib import Path
import copy,json,os,shutil
from .api import PACKAGE,file_record,write_json

def prepare_examples(source_root,destination,config_dir):
    source_root,destination,config_dir=map(lambda p:Path(p).resolve(),(source_root,destination,config_dir))
    if destination.exists() or config_dir.exists():
        raise FileExistsError("Choose new local asset and config directories; preparation never overwrites")
    plans=[]
    for building in ["A","B","C"]:
        template=json.loads((PACKAGE.parent/"configs"/f"building_{building}.json").read_text(encoding="utf-8"))
        sample=template["sample_id"]
        for name,spec in template["maps"].items():
            filename=Path(spec["path"]).name
            src=source_root/"high_quality_architectural"/sample/filename
            actual=file_record(src)
            for key in ["sha256","width","height"]:
                if actual[key]!=spec[key]:raise ValueError(f"Local {sample}/{filename} does not match the audited asset ({key})")
            plans.append((src,destination/sample/filename))
        for name,spec in template["maps"].items():
            spec["path"]=os.path.relpath(destination/sample/Path(spec["path"]).name,config_dir).replace("\\","/")
        template["outputs"]["directory"]=os.path.relpath(destination.parent/"runs"/f"building_{building}_none",config_dir).replace("\\","/")
        template["reference_results"]["status"]="Not supplied by this command; keep separately and use only for evaluation."
        plans.append((template,config_dir/f"building_{building}.json"))
    destination.mkdir(parents=True);config_dir.mkdir(parents=True)
    for source,target in plans:
        target.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(source,dict):write_json(target,source)
        else:shutil.copyfile(source,target)
    return {"copied_maps":9,"cases":3,"config_dir":str(config_dir),"asset_directory":str(destination),"source_type":"annotation_derived","redistribution":"NOT AUTHORIZED by this preparation command"}
