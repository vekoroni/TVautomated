"""
AVSHUNTER — EV Engine v2 (Patched v2.1.0)
==========================================
PATCH-01: Win rate double-division fix — column-name-based normalisation
PATCH-02: expected_move fallback chain (median_gain_if_up variants)
PATCH-03: Horizon from DTE fixed mapping (was always 10)
PATCH-04: option_mid fallback extended (mark, contract_premium)
All 4-layer engine logic unchanged from v2.0.0.
"""
from __future__ import annotations
import warnings
from dataclasses import dataclass, asdict
from typing import Optional

def _clamp(x,lo,hi): return max(lo,min(hi,x))
def _safe(v,default=0.0):
    try:
        if v is None: return default
        f=float(v); return default if f!=f else f
    except: return default

class DataQualityWarning(UserWarning): pass

@dataclass
class EVInputs:
    ticker:str="UNKNOWN"; direction:str="CALL"; horizon_days:int=10
    hit_rate_5d:float=0.0; hit_rate_10d:float=0.0; hit_rate_20d:float=0.0
    expected_move_5d:float=0.0; expected_move_10d:float=0.0; expected_move_20d:float=0.0
    predictability_score:float=50.0; bmps:float=50.0
    calibration_confidence:float=50.0; flow_score:float=2.5
    survival_prob:float=0.50; gamma_obstruction:float=0.20; path_cleanliness:float=0.60
    entry_price:float=100.0; target_price:float=110.0; stop_price:float=95.0
    option_mid:float=0.0; option_bid:float=0.0; option_ask:float=0.0
    delta:float=0.40; gamma:float=0.02; theta_per_day:float=0.01
    vega:float=0.10; iv_rank:float=0.50; iv_tailwind_score:float=0.0; dte:float=30.0
    spread_pct:float=0.05; drift_pct:float=0.02; iv_distortion:float=0.0; slippage_est:float=0.01
    regime_state:str="TRANSITIONAL"; regime_drift_status:str="Stable"
    convexity_score:float=0.0; phase_transition:bool=False; gamma_squeeze:bool=False
    data_quality_score:float=100.0; breakeven_pass_live:bool=True; runway_pct:float=2.0
    prob_breakout:float=0.35; prob_rejection:float=0.35; prob_drift:float=0.30
    premium:float=0.0; breakeven_pct:float=5.0

@dataclass
class EVResult:
    ev_structural:float=0.0; ev_path_adj:float=0.0; ev_contract:float=0.0; ev_execution_adj:float=0.0
    ev_5d:float=0.0; ev_10d:float=0.0; ev_20d:float=0.0; ev_selected:float=0.0
    ev_final:float=0.0; ev_conf_adj:float=0.0
    cost_spread:float=0.0; cost_theta:float=0.0; cost_slippage:float=0.0
    iv_adjustment:float=0.0; runway_penalty:float=0.0
    p_win_blended:float=0.0; path_multiplier:float=1.0; contract_efficiency:float=1.0
    execution_multiplier:float=1.0; regime_multiplier:float=1.0
    confidence_multiplier:float=1.0; convexity_boost:float=1.0
    ev_status:str="FAIL"; monetisation_readiness:str="NO"
    recommended_size_mult:float=0.0; primary_reason:str="UNINITIALISED"
    contract_efficiency_flag:bool=False; data_quality_flag:bool=False
    quality_score:float=0.0; risk_score:float=0.0; decision_hint:str="AVOID"
    def to_row_dict(self): return {f"ev2_{k}":v for k,v in asdict(self).items()}


def ev_inputs_from_row(row:dict) -> EVInputs:
    """PATCHED: fixes win rate normalisation, expected_move fallback, horizon, option_mid."""
    def f(k,d=0.0): return _safe(row.get(k),d)
    def s(k,d=""): v=row.get(k,d); return str(v).strip() if v is not None else d
    def b(k,d=True):
        v=row.get(k,d)
        if isinstance(v,bool): return v
        if isinstance(v,str): return v.strip().upper() in("TRUE","1","YES")
        try: return bool(int(v))
        except: return d

    # PATCH-01: win rate by column family
    def _wr(col, pct_scale):
        v=f(col,0.0)
        return _clamp(v/100.0,0,1) if (pct_scale and v>0) else _clamp(v,0,1)

    hr5  = _wr('win_rate_5d',False)  or _wr('layer2__win_rate_5d',True)
    hr10 = _wr('win_rate_10d',False) or _wr('layer2__win_rate_10d',True)
    hr20 = _wr('win_rate_20d',False) or _wr('layer2__win_rate_20d',True)

    # PATCH-02: expected_move fallback chain
    def _move(n):
        return (f(f'expected_move_{n}d') or
                f(f'layer2__median_gain_if_up_{n}d') or
                f(f'median_gain_if_up_{n}d') or
                f('median_gain_if_up'))
    em5=_move('5'); em10=_move('10'); em20=_move('20')

    # PATCH-03: horizon from DTE
    dte_val=f('dte',30.0)
    if dte_val<15: horizon=5
    elif dte_val<25: horizon=10
    else: horizon=20

    # PATCH-04: option_mid fallback
    opt_mid=(f('option_mid') or f('premium') or f('mark') or f('contract_premium') or 1.0)

    entry=f('signal_price',100.0) or 100.0
    target=f('target_price') or entry*(1+f('target_pct',0.10))
    stop  =f('stop_price')   or entry*(1-f('stop_pct',0.05))

    return EVInputs(
        ticker=s('ticker','UNKNOWN'), direction=s('direction','CALL').upper(),
        horizon_days=horizon,
        hit_rate_5d=hr5, hit_rate_10d=hr10, hit_rate_20d=hr20,
        expected_move_5d=em5, expected_move_10d=em10, expected_move_20d=em20,
        predictability_score=f('predictability_score',f('predictability',f('composite',50.0))),
        bmps=f('bmps',50.0),
        calibration_confidence=f('calibration_confidence',f('composite',50.0)),
        flow_score=f('flow_score',2.5),
        survival_prob=f('survival_prob',0.50), gamma_obstruction=f('gamma_obstruction',0.20),
        path_cleanliness=f('path_cleanliness',0.60),
        entry_price=entry, target_price=target, stop_price=stop,
        option_mid=opt_mid,
        option_bid=f('options_bid',f('option_bid',0.0)),
        option_ask=f('options_ask',f('option_ask',0.0)),
        delta=abs(f('contract_delta',f('delta',0.40))),
        gamma=abs(f('contract_gamma',f('gamma',0.02))),
        theta_per_day=abs(f('contract_theta',f('theta',0.01))),
        vega=abs(f('contract_vega',f('vega',0.10))),
        iv_rank=f('iv_rank',f('ivp_252d',f('iv_percentile',0.50))),
        iv_tailwind_score=f('iv_tailwind_score',0.0),
        dte=dte_val,
        spread_pct=f('spread_pct_live',f('spread_pct',0.05)),
        drift_pct=f('entry_drift_pct',f('drift_pct',0.02)),
        iv_distortion=f('iv_distortion_score',f('iv_distortion',0.0)),
        slippage_est=f('slippage_est',f('slippage_cost',0.01)),
        regime_state=s('regime_state',s('macro_regime',s('regime','TRANSITIONAL'))).upper(),
        regime_drift_status=s('regime_drift_status','Stable'),
        convexity_score=f('convexity_score',f('sb_convexity_score',f('convexity',0.0))),
        phase_transition=b('phase_transition',False),
        gamma_squeeze=b('gamma_squeeze',False),
        data_quality_score=f('data_quality_score',100.0),
        breakeven_pass_live=b('breakeven_pass_live',True),
        runway_pct=f('runway_pct',2.0),
        prob_breakout=f('prob_breakout',0.35), prob_rejection=f('prob_rejection',0.35),
        prob_drift=f('prob_drift',0.30),
        premium=opt_mid, breakeven_pct=f('breakeven_pct',5.0),
    )


class EVEngineV2:
    def __init__(self): pass

    def _blend_win_probability(self,x):
        am={5:x.hit_rate_5d,10:x.hit_rate_10d,20:x.hit_rate_20d}
        a=am.get(x.horizon_days,x.hit_rate_10d)
        if x.hit_rate_5d==0 and x.hit_rate_10d==0 and x.hit_rate_20d==0:
            warnings.warn(f"[{x.ticker}] All hit rates zero",DataQualityWarning); a=0.40
        ms=(0.40*_clamp(x.predictability_score/100,0,1)+0.25*_clamp(x.bmps/100,0,1)+
            0.20*_clamp(x.calibration_confidence/100,0,1)+0.15*_clamp(x.flow_score/5,0,1))
        return _clamp(0.55*a+0.45*ms,0.05,0.95)

    def _struct_ev(self,x,p,h):
        mm={5:x.expected_move_5d,10:x.expected_move_10d,20:x.expected_move_20d}
        em=mm.get(h,x.expected_move_10d)
        if em==0.0 and x.entry_price>0:
            up=(x.target_price-x.entry_price)/x.entry_price
            dn=(x.entry_price-x.stop_price)/x.entry_price
            return p*up-(1-p)*dn
        rr=(x.target_price-x.entry_price)/max(x.entry_price-x.stop_price,0.001)
        lm=-(em/max(rr,0.5))
        return p*em+(1-p)*lm

    def _path_mult(self,x):
        sc=_clamp(x.survival_prob*1.2,0.40,1.20)
        pc=0.80+x.path_cleanliness*0.40
        return _clamp((sc+pc)/2.0-x.gamma_obstruction*0.40,0.40,1.50)

    def _gross_opt(self,x,move,win):
        prem=max(x.option_mid,x.premium,0.01)
        if win:
            lin=abs(move)*x.delta*x.entry_price
            gb=0.5*x.gamma*(move*x.entry_price)**2
            return (lin+gb)/prem
        return -1.0*_clamp(1.0-x.delta*0.20,0.60,1.00)

    def _theta_cost(self,x,h):
        prem=max(x.option_mid,x.premium,0.01)
        acc=1.15 if x.dte<21 else 1.0
        return _clamp(x.theta_per_day*h*acc/prem,0.0,0.80)

    def _vega_adj(self,x): return _clamp(x.iv_tailwind_score/100.0*0.30,-0.30,0.30)

    def _contract_ev(self,x,p,h):
        mm={5:x.expected_move_5d,10:x.expected_move_10d,20:x.expected_move_20d}
        em=mm.get(h,x.expected_move_10d) or (x.target_price-x.entry_price)/x.entry_price
        gev=p*self._gross_opt(x,em,True)+(1-p)*self._gross_opt(x,em,False)
        return gev-self._theta_cost(x,h)+self._vega_adj(x)

    def _exec_mult(self,x):
        b=1.0
        if x.spread_pct>0.20: b-=0.30
        elif x.spread_pct>0.10: b-=0.15
        elif x.spread_pct>0.05: b-=0.07
        b-=_clamp(x.drift_pct*2,0,0.15)
        if x.iv_distortion>0.10: b-=0.10
        elif x.iv_distortion>0.05: b-=0.05
        b-=_clamp(x.slippage_est*3,0,0.10)
        return _clamp(b,0.50,1.00)

    def _runway_pen(self,x):
        if x.runway_pct<=0: return 0.50
        if x.runway_pct<0.5: return 0.25
        if x.runway_pct<1.0: return 0.12
        if x.runway_pct<2.0: return 0.05
        return 0.0

    def _regime_mult(self,x):
        b={"RISK_ON":1.08,"BULLISH":1.08,"TRANSITIONAL":1.00,"NEUTRAL":1.00,
           "RISK_OFF":0.88,"BEARISH":0.88,"FLIPPED":0.72}.get(
            x.regime_state.upper().replace(" ","_"),1.00)
        d={"Stable":1.00,"Drifting":0.88,"Flipped":0.72}.get(x.regime_drift_status,0.88)
        return _clamp(b*d,0.50,1.20)

    def _conf_mult(self,x):
        return _clamp(0.50*(x.data_quality_score/100)+0.50*(x.calibration_confidence/100),0.25,1.00)

    def _conv_boost(self,x):
        b=1.0
        if x.phase_transition: b+=0.25
        if x.gamma_squeeze: b+=0.20
        if x.iv_rank<0.30 and x.iv_tailwind_score>20: b+=0.15
        if x.convexity_score>0.70: b+=_clamp(x.convexity_score*0.20,0,0.20)
        return _clamp(b,1.0,1.60)

    def _contract_eff(self,x,cev,sev):
        if abs(sev)<0.001: return 1.0
        return _clamp(cev/abs(sev),0.30,1.30)

    def _hard_gates(self,x):
        if not x.breakeven_pass_live: return True,"BREAKEVEN_FAIL"
        if x.runway_pct<=0: return True,"ZERO_RUNWAY"
        if x.spread_pct>0.30: return True,"SPREAD_UNUSABLE"
        if x.option_mid<=0 and x.premium<=0: return True,"NO_CONTRACT_PRICE"
        return False,""

    def _classify(self,ev_ca,x,rp):
        if x.data_quality_score<40: return "DATA_WEAK","NO",0.0,"LOW_DATA_QUALITY","AVOID"
        if ev_ca>=0.25: return "PASS_HIGH","YES_AGGRESSIVE",1.25,"HIGH_EV","STRONG"
        if ev_ca>=0.10: return "PASS","YES",1.00,"GOOD_EV","MODERATE"
        if ev_ca>=0.00: return "PASS_SMALL","YES_SMALL",0.50,"LOW_POS_EV","WEAK"
        if ev_ca>=-0.10: return "WEAK_PASS","WAIT",0.25,"NEAR_ZERO_EV","AVOID"
        return "FAIL","NO",0.0,"NEGATIVE_EV","AVOID"

    def evaluate(self,inputs:EVInputs)->EVResult:
        x=inputs
        blocked,block_reason=self._hard_gates(x)
        p=self._blend_win_probability(x)
        s5=self._struct_ev(x,p,5); s10=self._struct_ev(x,p,10); s20=self._struct_ev(x,p,20)
        sev={5:s5,10:s10,20:s20}.get(x.horizon_days,s10)
        pm=self._path_mult(x); epa=sev*pm
        c5=self._contract_ev(x,p,5); c10=self._contract_ev(x,p,10); c20=self._contract_ev(x,p,20)
        csel={5:c5,10:c10,20:c20}.get(x.horizon_days,c10)
        ce=self._contract_eff(x,csel,sev); cef=ce<0.50
        em=self._exec_mult(x); rp=self._runway_pen(x)
        rm=self._regime_mult(x); cm=self._conf_mult(x)
        cb=self._conv_boost(x) if sev>0 else 1.0
        if blocked:
            evf=evc=-1.0
            st,rd,sz,rs,ht="FAIL","NO",0.0,block_reason,"AVOID"
        else:
            evf=(epa*ce*em*rm*cb)-rp; evc=evf*cm
            st,rd,sz,rs,ht=self._classify(evc,x,rp)
        qs=_clamp(x.predictability_score*0.25+x.bmps*0.20+(p*100)*0.20+
                  (pm*100/1.5)*0.20+x.data_quality_score*0.15,0,100)
        rsk=_clamp((1-em)*40+x.gamma_obstruction*30+(1-x.survival_prob)*20+
                   _clamp(x.spread_pct*100,0,10),0,100)
        return EVResult(
            ev_structural=round(sev,6),ev_path_adj=round(epa,6),
            ev_contract=round(csel,6),ev_execution_adj=round(epa*ce*em,6),
            ev_5d=round(c5,6),ev_10d=round(c10,6),ev_20d=round(c20,6),
            ev_selected=round(csel,6),ev_final=round(evf,6),ev_conf_adj=round(evc,6),
            cost_spread=round(x.spread_pct,6),cost_theta=round(self._theta_cost(x,x.horizon_days),6),
            cost_slippage=round(x.slippage_est,6),iv_adjustment=round(self._vega_adj(x),6),
            runway_penalty=round(rp,6),p_win_blended=round(p,6),path_multiplier=round(pm,6),
            contract_efficiency=round(ce,6),execution_multiplier=round(em,6),
            regime_multiplier=round(rm,6),confidence_multiplier=round(cm,6),
            convexity_boost=round(cb,6),ev_status=st,monetisation_readiness=rd,
            recommended_size_mult=sz,primary_reason=rs,contract_efficiency_flag=cef,
            data_quality_flag=x.data_quality_score<60,
            quality_score=round(qs,2),risk_score=round(rsk,2),decision_hint=ht,
        )


if __name__=="__main__":
    eng=EVEngineV2()
    print("\nPatch validation:")
    # PATCH-01: actuarial 0-1
    r1=ev_inputs_from_row({'ticker':'TERN','signal_price':25,'win_rate_10d':0.61,
        'median_gain_if_up':0.07,'delta':0.45,'theta':0.03,'option_mid':1.20,
        'dte':18,'spread_pct':0.06,'regime_state':'RISK_ON','runway_pct':3.5})
    assert 0<r1.hit_rate_10d<1, f"FAIL P01: {r1.hit_rate_10d}"
    print(f"P01 ✓ hit_rate_10d={r1.hit_rate_10d:.3f}")
    # PATCH-01b: L2 100-scale
    r2=ev_inputs_from_row({'ticker':'NVDA','signal_price':875,'layer2__win_rate_10d':61.0,
        'layer2__median_gain_if_up_10d':0.065,'delta':0.42,'option_mid':12.5,
        'dte':14,'spread_pct':0.07,'regime_state':'TRANSITIONAL','runway_pct':2.5})
    assert 0<r2.hit_rate_10d<1, f"FAIL P01b: {r2.hit_rate_10d}"
    print(f"P01b ✓ hit_rate_10d={r2.hit_rate_10d:.3f}")
    # PATCH-02: expected_move fallback
    assert r1.expected_move_20d>0, "FAIL P02"
    print(f"P02 ✓ expected_move_20d={r1.expected_move_20d:.4f}")
    # PATCH-03: horizon
    r3=ev_inputs_from_row({'signal_price':100,'dte':5})
    assert r3.horizon_days==5, f"FAIL P03: {r3.horizon_days}"
    print(f"P03 ✓ dte=5 → horizon={r3.horizon_days}")
    # PATCH-04: mark fallback
    r4=ev_inputs_from_row({'signal_price':100,'mark':2.5,'dte':30})
    assert r4.option_mid==2.5, f"FAIL P04: {r4.option_mid}"
    print(f"P04 ✓ option_mid={r4.option_mid:.2f}")
    # Full eval
    res=eng.evaluate(r1)
    print(f"\nFull eval TERN: ev_final={res.ev_final:+.4f} | status={res.ev_status} | hint={res.decision_hint}")
    print("All patches OK ✓")
