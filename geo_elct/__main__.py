"""Portable public entry: extract, evaluate, and local asset preparation."""
import argparse,json,sys
from pathlib import Path
from .api import MODES,extract,load_case,verify_source_manifest,write_json

def parser():
    p=argparse.ArgumentParser(description="Geo-ELCT from supplied semantic maps. Default: no correction.")
    sub=p.add_subparsers(dest="command",required=True)
    e=sub.add_parser("extract")
    e.add_argument("--config",type=Path)
    for n in ["wall","icon","rough","out"]:e.add_argument("--"+n,type=Path)
    e.add_argument("--mode",choices=MODES,default=None)
    e.add_argument("--source-type",choices=["unknown","annotation_derived","model_prediction"],default=None)
    v=sub.add_parser("evaluate")
    v.add_argument("--definition",choices=["legacy_relation","strict_tables"],required=True)
    for n in ["reference","candidate","out"]:v.add_argument("--"+n,type=Path,required=True)
    prep=sub.add_parser("prepare-examples",help="Copy locally held, hash-verified maps. Does not download or grant redistribution rights.")
    prep.add_argument("--source-root",type=Path,required=True)
    prep.add_argument("--destination",type=Path,required=True)
    prep.add_argument("--config-dir",type=Path,required=True)
    return p

def main(argv=None):
    p=parser();args=p.parse_args(argv)
    try:
        if args.command=="extract":
            if args.config:
                if any([args.wall,args.icon,args.rough]):raise ValueError("Use a config or direct map paths, not both")
                case=load_case(args.config)
                out=args.out or case["out"]
                config=case["config"]
                info=extract(case["wall"],case["icon"],case["rough"],out,mode=args.mode or case["mode"],source_type=args.source_type or case["source_type"],
                             case_metadata={"sample_id":config.get("sample_id"),"building":config.get("building"),"config_sha256":case["config_sha256"]})
            else:
                if not all([args.wall,args.icon,args.out]):raise ValueError("Provide --config or --wall --icon --out")
                info=extract(args.wall,args.icon,args.rough or args.wall,args.out,mode=args.mode or "none",source_type=args.source_type or "unknown")
        elif args.command=="evaluate":
            verify_source_manifest()
            if args.out.exists():raise FileExistsError("Evaluation output exists; choose a new directory")
            if args.definition=="strict_tables":
                from .evaluation.evaluate_reference_faithful_tables import evaluate_tables
                info=evaluate_tables(args.reference,args.candidate,args.out)
            else:
                from .evaluation.compare_elct_tables import run_comparison
                info=run_comparison(args.reference,args.candidate,args.out)
            write_json(args.out/"evaluation_identity.json",{"definition":args.definition,"source_modules":verify_source_manifest(),"note":"Separate historical relation / strict topology / room table / edge table measures; not a combined correctness pass."})
        else:
            from .prepare import prepare_examples
            info=prepare_examples(args.source_root,args.destination,args.config_dir)
        print(json.dumps(info,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,FileNotFoundError,FileExistsError,KeyError) as e:
        p.exit(2,f"{type(e).__name__}: {e}\n")

if __name__=="__main__":sys.exit(main())
