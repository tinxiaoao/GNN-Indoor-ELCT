#!/usr/bin/env python3
"""Numerical MWM core for the confirmed WI validation configurations.

C-1 parameters and all 216 C-1-source room predictions are retained from the
source workbook archive, after forward reproduction is verified.
Only nine new parameter fits are used in the main results.
Historical optimizer settings are unavailable. The numerical settings below
are explicit new settings, not claimed to be recovered historical settings.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, platform, time
from pathlib import Path
import numpy as np
import scipy
from scipy.optimize import least_squares

STARTS=np.array([[1,1,.1],[2,3,1],[3,5,2],[4,10,.1],
                 [1,10,5],[5,1,10],[2,20,10],[6,30,20]],dtype=float)
SETTINGS=dict(method="trf",ftol=1e-9,xtol=1e-9,gtol=1e-9,
              max_nfev=800,x_scale=np.array([2.,8.,4.]))
K=np.log(10.)/10.

def digest(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write_csv(p:Path, rows:list[dict])->None:
    if not rows:
        return
    with p.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

class OriginalSVGMWM:
    def __init__(self, folder:Path):
        self.folder=folder
        self.cfg=json.loads((folder/"recovery_config.json").read_text(encoding="utf-8"))
        if digest(folder/"source.svg")!=self.cfg["svg_sha256"]:
            raise ValueError("SVG checksum mismatch")
        with np.load(folder/"reference_and_proposed.npz",allow_pickle=False) as z:
            self.targets=z["WI_ARP_dBm"].copy()
            self.freqs=z["frequency_GHz"].copy()
        with np.load(folder/"link_features_confirmed.npz",allow_pickle=False) as z:
            self.room_features=[z[f"room{r}_features"].copy() for r in range(1,19)]
        self.theta_C1=np.asarray(self.cfg["C1_parameters"],float)
        if self.targets.shape!=(3,4,18) or not np.isfinite(self.targets).all():
            raise ValueError("Invalid reference layout")
        chunks=[]; lengths=[]
        for feat in self.room_features:
            if feat.shape[0]!=4 or feat.shape[-1]!=3:
                raise ValueError("Invalid link feature dimensions")
            if not np.isfinite(feat).all():
                raise ValueError("Nonfinite link features")
            for t in range(4):
                chunks.append(feat[t]); lengths.append(len(feat[t]))
        self.features=np.concatenate(chunks)
        self.lengths=np.array(lengths)
        self.offsets=np.r_[0,np.cumsum(self.lengths)[:-1]]
        self.groups=np.repeat(np.arange(72),self.lengths)
        self.logcounts=np.log(self.lengths)
        self.power=float(self.cfg["P_tx_dBm"])

    def shape_predictions(self,x:np.ndarray)->tuple[np.ndarray,np.ndarray]:
        # Use explicit per-column operations to avoid unnecessary BLAS overhead.
        attenuation=self.features[:,0]*x[0]+self.features[:,1]*x[1]+self.features[:,2]*x[2]
        logpower=-K*attenuation
        maxima=np.maximum.reduceat(logpower,self.offsets)
        weights=np.exp(logpower-maxima[self.groups])
        totals=np.add.reduceat(weights,self.offsets)
        logmeans=(maxima+np.log(totals)-self.logcounts).reshape(18,4)
        means=np.stack([np.add.reduceat(weights*self.features[:,j],self.offsets)/totals
                        for j in range(3)],axis=-1).reshape(18,4,3)
        accum=np.logaddexp.accumulate(logmeans,axis=1)
        jac=np.empty_like(means); jac[:,0]=means[:,0]
        for t in range(1,4):
            prev=np.exp(accum[:,t-1]-accum[:,t])
            curr=np.exp(logmeans[:,t]-accum[:,t])
            jac[:,t]=prev[:,None]*jac[:,t-1]+curr[:,None]*means[:,t]
        return (accum/K).T,(-jac).transpose(1,0,2)

    def predict(self,frequency:float,theta:np.ndarray)->np.ndarray:
        base,_=self.shape_predictions(np.asarray(theta[1:]))
        return self.power-32.4-20*np.log10(frequency)-theta[0]+base

    def direct_predict(self,frequency:float,theta:np.ndarray)->np.ndarray:
        """Independent pointwise forward calculation, matching recovered script."""
        p=np.empty((4,18))
        for r,features in enumerate(self.room_features):
            b0,n,lwall,lopen=theta
            pl=32.4+20*np.log10(frequency)+b0+n*features[:,:,0] \
               +lwall*features[:,:,1]+lopen*features[:,:,2]
            pt=10.**((self.power-pl)/10.)
            p[:,r]=10*np.log10(np.cumsum(pt.mean(axis=1)))
        return p

    def fit(self,frequency:float,source:int,target_train:np.ndarray):
        """Only the 18 ARP targets in target_train are accessible to this fit."""
        target_train=np.array(target_train,dtype=float,copy=True)
        if source not in range(4) or target_train.shape!=(18,) \
           or not np.isfinite(target_train).all():
            raise ValueError("Invalid source or calibration target array")
        constant=self.power-32.4-20*np.log10(frequency)
        cache_x=None; cache=None
        def evaluate(x):
            nonlocal cache_x,cache
            if cache_x is None or not np.array_equal(cache_x,x):
                base,jac=self.shape_predictions(x)
                raw=constant+base
                delta=raw[source]-target_train
                b0=float(delta.mean())  # exact profiled unconstrained intercept
                res=delta-b0
                j=jac[source]; jcenter=j-j.mean(axis=0)
                cache=(res,jcenter,raw-b0,b0,jac)
                cache_x=x.copy()
            return cache
        attempts=[]; begin=time.perf_counter()
        for sid,x0 in enumerate(STARTS):
            opt=least_squares(lambda x:evaluate(x)[0],x0.copy(),
                jac=lambda x:evaluate(x)[1],
                bounds=(np.zeros(3),np.full(3,np.inf)),**SETTINGS)
            residual,_,pred,b0,jac=evaluate(opt.x)
            attempts.append(dict(frequency_GHz=float(frequency),
                calibration_case=f"C-{source+1}",start=sid,
                b0=b0,n=float(opt.x[0]),L_wall=float(opt.x[1]),L_open=float(opt.x[2]),
                training_SSE=float(residual@residual),success=bool(opt.success),
                status=int(opt.status),nfev=int(opt.nfev),njev=int(opt.njev),
                optimality=float(opt.optimality),message=str(opt.message)))
        converged=[a for a in attempts if a["success"]]
        if not converged:
            raise RuntimeError("No start converged")
        selected=min(converged,key=lambda a:a["training_SSE"])
        x=np.array([selected[k] for k in ("n","L_wall","L_open")])
        residual,_,pred,b0,jac=evaluate(x)
        J=np.column_stack([-np.ones(18),jac[source]])
        sv=np.linalg.svd(J,compute_uv=False)
        theta=np.r_[b0,x]
        record=dict(frequency_GHz=float(frequency),calibration_case=f"C-{source+1}",
            origin="New fit",n_training_ARPs=18,b0=float(b0),
            n=float(x[0]),L_wall=float(x[1]),L_open=float(x[2]),
            training_SSE=float(residual@residual),
            training_RMSE=float(np.sqrt(np.mean(residual**2))),
            training_MAE=float(np.mean(np.abs(residual))),
            selected_start=int(selected["start"]),success=True,
            n_starts=len(attempts),
            training_jacobian_rank=int(np.linalg.matrix_rank(J)),
            training_jacobian_condition=float(sv[0]/sv[-1]),
            min_start_SSE=min(a["training_SSE"] for a in attempts),
            max_start_SSE=max(a["training_SSE"] for a in attempts),
            seconds=time.perf_counter()-begin,
            training_target_sha256=hashlib.sha256(target_train.tobytes()).hexdigest())
        return record,attempts,pred.copy(),theta

