"""Daily-return correlations, SPY residuals, and a classical MDS display."""
from __future__ import annotations
import numpy as np
import pandas as pd


def correlation_groups(matrix, threshold=.75):
    """Complete-link groups: every pair in a group meets the threshold."""
    groups=[[i] for i in range(len(matrix))]
    while True:
        best=None
        for a in range(len(groups)):
            for b in range(a+1,len(groups)):
                strength=min(matrix[i,j] for i in groups[a] for j in groups[b])
                if strength>=threshold and (best is None or strength>best[0]):best=(strength,a,b)
        if best is None:break
        _,a,b=best;groups[a]+=groups.pop(b)
    return sorted(groups,key=lambda g:(-len(g),min(g)))


def correlation_map(matrix):
    """Embed sqrt(2*(1-r)) distances in two dimensions; keep error visible."""
    n=len(matrix); centering=np.eye(n)-np.ones((n,n))/n
    distance2=2*(1-matrix)
    gram=-.5*centering@distance2@centering
    values,vectors=np.linalg.eigh(gram);order=np.argsort(values)[::-1]
    positive=np.maximum(values[order],0)
    xy=np.zeros((n,2))
    for axis in range(min(2,n)):
        xy[:,axis]=vectors[:,order[axis]]*np.sqrt(positive[axis])
        # Stable orientation for repeated displays of identical inputs.
        if xy[np.argmax(np.abs(xy[:,axis])),axis]<0:xy[:,axis]*=-1
    represented=float(positive[:2].sum()/positive.sum()) if positive.sum()>1e-12 else 1.
    return xy,represented


def analyze_correlations(rows,histories,benchmarks,limit=20,market_adjusted=False):
    chosen=sorted((r for r in rows if r['status']=='ready'),key=lambda r:(-r['score'],r['ticker']))[:limit]
    if len(chosen)<2:return {'available':False,'reason':'At least two scored stocks are needed.'}
    bases=[r.get('price_basis','adjusted') for r in chosen]
    basis=max(sorted(set(bases)),key=bases.count)
    excluded=[r['ticker'] for r in chosen if r.get('price_basis','adjusted')!=basis]
    chosen=[r for r in chosen if r['ticker'] not in excluded and r['ticker'] in histories]
    benchmark=benchmarks.get(basis)
    if benchmark is None:return {'available':False,'reason':'A matching SPY price basis is unavailable.'}
    # Daily returns are calculated before alignment; never fill gaps with zero.
    series={r['ticker']:histories[r['ticker']].pct_change(fill_method=None) for r in chosen}
    series['__SPY']=benchmark.pct_change(fill_method=None)
    daily=pd.concat(series,axis=1).replace([np.inf,-np.inf],np.nan).dropna().iloc[-252:]
    if len(daily)<126:return {'available':False,'reason':'Fewer than 126 overlapping daily returns. Correlations are unavailable.'}
    names=[r['ticker'] for r in chosen];x=daily[names].to_numpy();spy=daily['__SPY'].to_numpy()
    if market_adjusted:
        if np.std(spy)<1e-10:return {'available':False,'reason':'SPY returns have no usable variation.'}
        design=np.column_stack([np.ones(len(spy)),spy])
        x=x-design@np.linalg.lstsq(design,x,rcond=None)[0]
    valid=np.std(x,axis=0)>1e-10
    excluded += [name for name,ok in zip(names,valid) if not ok]
    names=[name for name,ok in zip(names,valid) if ok];x=x[:,valid]
    if len(names)<2:return {'available':False,'reason':'Fewer than two stocks have usable return variation after this adjustment.'}
    corr=np.clip(np.corrcoef(x,rowvar=False),-1,1);np.fill_diagonal(corr,1)
    coordinates,represented=correlation_map(corr)
    groups=correlation_groups(corr)
    lookup={r['ticker']:r for r in chosen}
    clusters=[];membership={}
    for number,members in enumerate(groups):
        values=[corr[i,j] for offset,i in enumerate(members) for j in members[offset+1:]]
        cluster={'id':number,'members':[names[i] for i in members],'average_correlation':round(float(np.mean(values)),3) if values else None,'minimum_correlation':round(float(min(values)),3) if values else None}
        clusters.append(cluster)
        for index in members:membership[index]=number
    points=[{'ticker':name,'score':lookup[name]['score'],'return_1y':lookup[name].get('return_1y'),'x':round(float(coordinates[i,0]),5),'y':round(float(coordinates[i,1]),5),'cluster':membership[i]} for i,name in enumerate(names)]
    pairs=[corr[i,j] for i in range(len(names)) for j in range(i+1,len(names))]
    return {'available':True,'requested':limit,'tickers':names,'points':points,'matrix':np.round(corr,3).tolist(),'clusters':clusters,'threshold':.75,'sample_count':len(daily),'start':daily.index[0].date().isoformat(),'end':daily.index[-1].date().isoformat(),'market_adjusted':market_adjusted,'price_basis':basis,'excluded':excluded,'map_variance_explained':round(represented,3),'average_correlation':round(float(np.mean(pairs)),3)}
