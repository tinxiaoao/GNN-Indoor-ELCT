#!/usr/bin/env python3
"""Rebuild SVG links, retain archived C-1, and fit the nine additional sources."""
from pathlib import Path
import argparse, json, csv
import numpy as np
from mwm_core import OriginalSVGMWM, write_csv
from rebuild_svg import run as rebuild

def main(root:Path):
    inp=root/"inputs"; out=root/"replayed"; out.mkdir(exist_ok=True)
    rebuild(inp)
    m=OriginalSVGMWM(inp)
    labels=m.cfg["case_labels"]
    with np.load(inp/"reference_and_proposed.npz",allow_pickle=False) as z:
        proposed=z["Proposed_ARP_dBm"]
    pred=np.empty((3,4,4,18));theta=np.empty((3,4,4));fits=[];logs=[]
    with np.load(inp/"archived_C1_predictions.npz",allow_pickle=False) as z:
        old=z["MWM_ARP_dBm"]
    for fi,f in enumerate(m.freqs):
        theta[fi,0]=m.theta_C1[fi]
        pred[fi,0]=m.predict(f,theta[fi,0])
        np.testing.assert_allclose(pred[fi,0],old[fi],rtol=0,atol=1e-10)
        for ci in (1,2,3):
            rec,att,p,th=m.fit(float(f),ci,m.targets[fi,ci])
            rec["calibration_case"]=labels[ci]
            for a in att:a["calibration_case"]=labels[ci]
            pred[fi,ci]=p;theta[fi,ci]=th;fits.append(rec);logs.extend(att)
            np.testing.assert_allclose(p,m.direct_predict(f,th),rtol=0,atol=1e-10)
    ae=np.abs(pred-m.targets[:,None,:,:]);matrix=ae.mean(axis=-1)
    np.savez_compressed(out/"results.npz",frequency_GHz=m.freqs,parameters=theta,
        WI_ARP_dBm=m.targets,Proposed_ARP_dBm=proposed,
        MWM_ARP_dBm=pred,MWM_AE_dB=ae,MWM_MAE_dB=matrix)
    (out/"fits.json").write_text(json.dumps(fits,indent=2))
    (out/"start_log.json").write_text(json.dumps(logs,indent=2))
    rows=[]
    for fi,f in enumerate(m.freqs):
        for ci in range(4):
            for ej in range(4):
                for r in range(18):
                    rows.append(dict(frequency_GHz=float(f),calibration=labels[ci],
                        evaluation=labels[ej],room=r+1,WI_ARP_dBm=float(m.targets[fi,ej,r]),
                        predicted_ARP_dBm=float(pred[fi,ci,ej,r]),
                        AE_dB=float(ae[fi,ci,ej,r])))
    write_csv(out/"room_predictions.csv",rows)
    with np.load(root/"results/results.npz",allow_pickle=False) as z:
        diff=float(np.max(np.abs(z["MWM_ARP_dBm"]-pred)))
        np.testing.assert_allclose(z["MWM_ARP_dBm"],pred,rtol=0,atol=1e-8)
        np.testing.assert_array_equal(np.round(z["MWM_MAE_dB"],2),np.round(matrix,2))
    print(json.dumps({"replay_prediction_max_difference_dB":diff,"new_fits":len(fits),
        "converged_starts":sum(x["success"] for x in logs),"matrix":matrix.tolist()},indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent.parent)
    main(parser.parse_args().root)
