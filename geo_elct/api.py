"""New explicit dispatch wrapper; numerical routines retain snapshot behavior."""
from __future__ import annotations
import copy, hashlib, importlib.metadata, json, os, shutil, sys, time, tempfile
from pathlib import Path
from . import DEFAULT_OPENING_AGGREGATION, OPENING_AGGREGATIONS

PACKAGE = Path(__file__).resolve().parent
MODES = ("none", "legacy_revised", "reference_faithful", "correction_v2")
FULL = "fragment_plus_wall_plus_opening"

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def verify_source_manifest():
    records = json.loads((PACKAGE / "source_provenance.json").read_text(encoding="utf-8"))
    for record in records:
        path = PACKAGE.parent / record["package_path"]
        if sha256(path) != record["packaged_sha256"]:
            raise ValueError(f"Source provenance mismatch: {record['package_path']}. Record intentional source changes before running.")
    return records

def file_record(path):
    from PIL import Image
    path = Path(path)
    with Image.open(path) as im:
        return {"filename":path.name, "sha256":sha256(path), "width":im.width, "height":im.height, "image_mode":im.mode}

def load_case(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != 1:
        raise ValueError("Expected case schema_version=1")
    extraction = config.get("extraction", {})
    unsupported = set(extraction) - {"mode", "lightweight", "opening_aggregation"}
    if unsupported:
        raise ValueError(f"Numerical overrides are not supported: {sorted(unsupported)}")
    if extraction.get("lightweight", False) is not False:
        raise ValueError("This interface always exports both Excel tables (lightweight=False)")
    mode = extraction.get("mode", "none")
    if mode not in MODES:
        raise ValueError(f"Unknown correction identity: {mode}")
    opening_aggregation = extraction.get("opening_aggregation", DEFAULT_OPENING_AGGREGATION)
    if opening_aggregation not in OPENING_AGGREGATIONS:
        raise ValueError(f"Unknown opening aggregation: {opening_aggregation}")
    maps = {}
    for name in ("wall", "icon", "rough"):
        spec = config["maps"][name]
        source = (path.parent / spec["path"]).resolve()
        actual = file_record(source)
        for field in ("sha256", "width", "height"):
            if field in spec and actual[field] != spec[field]:
                raise ValueError(f"Input {name} {field} does not match the declared case")
        maps[name] = source
    if (maps["wall"] == maps["icon"]):
        raise ValueError("Wall and icon maps must be supplied separately")
    return {"config":config, "config_sha256":sha256(path), "wall":maps["wall"], "icon":maps["icon"], "rough":maps["rough"], "mode":mode,
            "opening_aggregation":opening_aggregation,
            "out":(path.parent/config["outputs"]["directory"]).resolve(), "source_type":config.get("input_source_type", "unknown")}

def extract(wall, icon, rough, out, *, mode="none", source_type="unknown", case_metadata=None,
            opening_aggregation=DEFAULT_OPENING_AGGREGATION):
    """Run exactly one selected correction pipeline. No reference-data argument exists."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if opening_aggregation not in OPENING_AGGREGATIONS:
        raise ValueError(f"opening_aggregation must be one of {OPENING_AGGREGATIONS}")
    if source_type not in {"unknown", "annotation_derived", "model_prediction"}:
        raise ValueError("Invalid declared source type")
    source_records = verify_source_manifest()
    if mode == "correction_v2":
        versioned = json.loads((PACKAGE / "correction_v2_provenance.json").read_text(encoding="utf-8"))
        for record in versioned:
            if sha256(PACKAGE.parent / record["package_path"]) != record["packaged_sha256"]:
                raise ValueError("correction_v2 source provenance mismatch")
        source_records = source_records + versioned
    inputs = {key:Path(value).resolve() for key,value in {"wall":wall,"icon":icon,"rough":rough}.items()}
    records = {key:file_record(value) for key,value in inputs.items()}
    if (records["wall"]["width"],records["wall"]["height"]) != (records["icon"]["width"],records["icon"]["height"]):
        raise ValueError("Wall and icon dimensions differ")
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Output already exists; choose a new run directory: {out}")
    out.mkdir(parents=True)
    (out/"inputs").mkdir()
    (out/"environment").mkdir()
    tempfile.tempdir = str(out/"environment")
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", str(out/"environment"))
    local = {}
    for key,value in inputs.items():
        dest=out/"inputs"/f"{key}.png"
        shutil.copyfile(value,dest)
        if sha256(dest)!=records[key]["sha256"]:
            raise ValueError("Input changed while being copied")
        local[key]=dest
    # All extraction/correction reads below use run-local maps. References are absent.
    from . import debug_topology as core
    from . import self_correction as independent
    from .extract_rooms import DEFAULT_INTERIOR_NOISE_PARAMS, ROOM_EXCLUDE_LABELS
    started=time.perf_counter()
    corrected_wall,corrected_icon=local["wall"],local["icon"]
    numerical_mode="baseline"
    if mode=="correction_v2":
        from . import correction_v2 as versioned
        correction=versioned.correct_maps(corrected_wall,corrected_icon,out/"correction")
        corrected_wall=out/"correction/corrected_wall_svg.png"
        corrected_icon=out/"correction/corrected_icon_svg.png"
        identity=versioned.VERSION + " -> B.debug_topology.run_topology(baseline)"
        parameters=copy.deepcopy(versioned.CONFIG)
    elif mode=="reference_faithful":
        correction=independent.correct_maps(corrected_wall,corrected_icon,out/"correction",mode=FULL)
        corrected_wall=out/"correction/corrected_wall_svg.png"
        corrected_icon=out/"correction/corrected_icon_svg.png"
        identity="B.self_correction.correct_maps -> B.debug_topology.run_topology(baseline)"
        parameters=copy.deepcopy(independent.REFERENCE_FREE_CONFIG)
    elif mode=="legacy_revised":
        numerical_mode=FULL
        identity="B.debug_topology.run_topology inline legacy correction"
        parameters={"legacy":copy.deepcopy(core._CONSERVATIVE_REPAIR_PARAMS),"fragment":copy.deepcopy(DEFAULT_INTERIOR_NOISE_PARAMS)}
    else:
        identity="B.debug_topology.run_topology baseline; no correction"
        parameters={}
    summary=core.run_topology(str(corrected_wall),str(corrected_icon),str(local["rough"]),str(out),correction_mode=numerical_mode,lightweight=False,
                              opening_aggregation=opening_aggregation)
    runtime=independent.reference_free_runtime_validation(out)
    write_json(out/"runtime_validation.json",runtime)
    v2_diagnostics = None
    if mode=="correction_v2":
        v2_diagnostics = versioned.runtime_diagnostics(out, correction, runtime)
        write_json(out/"correction_v2_diagnostics.json",v2_diagnostics)
    if mode=="legacy_revised":
        corrected_wall=out/"wall_svg_corrected.png";corrected_icon=out/"icon_svg_corrected.png"
    import numpy as np
    from PIL import Image
    changes={key:int(np.count_nonzero(np.asarray(Image.open(local[key]).convert("P")) != np.asarray(Image.open(candidate).convert("P")))) for key,candidate in (("wall",corrected_wall),("icon",corrected_icon))}
    write_json(out/"input_pixel_changes.json",changes)
    loaded=[]
    for name,module in sorted(sys.modules.items()):
        if name=="geo_elct" or name.startswith("geo_elct."):
            file=getattr(module,"__file__",None)
            if file:
                resolved=Path(file).resolve()
                if not resolved.is_relative_to(PACKAGE):
                    raise RuntimeError(f"Unexpected project module location: {name}")
                loaded.append({"module":name,"package_file":resolved.relative_to(PACKAGE.parent).as_posix(),"sha256":sha256(resolved)})
    metadata={"schema_version":1,"mode":mode,"algorithm_identity":identity,"extractor_correction_mode":numerical_mode,
              "opening_aggregation":opening_aggregation,
              "independent_correction_mode":FULL if mode=="reference_faithful" else None,"lightweight":False,
              "parameters_read_from_implementation":parameters,"excluded_room_labels":sorted(ROOM_EXCLUDE_LABELS),
              "fixed_extraction_rules":{"source":"geo_elct/extract_rooms.py; detect_adjacency.py; exterior_wall.py", "internal_search":"round(min(perimeter/10)); original stopping rule", "external_search":"last enumerated room perimeter/10; original stopping rule", "room_enumeration":"ascending semantic labels then 8-connected component order", "units":"length px; area px^2"},
              "source_type_declared":source_type,"inputs":records,"source_modules":source_records,"loaded_project_modules":loaded,
              "outputs":{"room_table":"debug_roomself.xlsx","edge_table":"debug_topology_edges.xlsx","topology_image":"debug_topology_result.png","room_mask":"region_id_map.npy","runtime":"runtime_validation.json","extractor_summary":"topology_summary.json"},
              "python_version":sys.version,"packages":package_versions(),
              "elapsed_seconds":time.perf_counter()-started,"case_metadata":case_metadata,
              "validation_scope":{"runtime_valid":runtime["passed"],"geometric_preservation":"NOT ESTABLISHED by runtime validation", "reference_results_read":False},
              "known_issue_notice":"Optional correction can delete clean exterior windows. Successful execution or migration equivalence is not geometric correctness."}
    write_json(out/"run_manifest.json",metadata)
    result = {"mode":mode,"algorithm_identity":identity,"room_count":summary["room_count"],"runtime_validation_passed":runtime["passed"],"input_pixel_changes":changes,"output":str(out),"geometric_correctness":"not established; review known issues and separate evaluation"}
    if v2_diagnostics is not None:
        metadata["versioned_correction_mode"] = versioned.VERSION
        metadata["outputs"]["versioned_diagnostics"] = "correction_v2_diagnostics.json"
        metadata["validation_scope"]["correction_v2"] = v2_diagnostics
        write_json(out/"run_manifest.json",metadata)
        result["correction_v2_diagnostics"] = {k:v2_diagnostics[k] for k in ("unresolved_component_count","unresolved_event_count","manual_review_required","all_implemented_checks_passed","em_ready")}
    return result

def package_versions():
    # Conda's cv2 build need not have an opencv-python distribution record.
    import numpy,cv2,pandas,openpyxl,PIL,matplotlib
    return {module.__name__:module.__version__ for module in [numpy,cv2,pandas,openpyxl,PIL,matplotlib]}
