import numpy as np
import pandas as pd
from research.ranking_correlations import analyze_correlations, correlation_groups, correlation_map


def fixture():
    rng=np.random.default_rng(42);dates=pd.bdate_range(end=pd.Timestamp.now(tz='UTC').normalize(),periods=310)
    market=rng.normal(.0003,.015,len(dates));histories={}
    for symbol in ['AAA','BBB','CCC']:
        returns=market+rng.normal(0,.002,len(dates))
        histories[symbol]=pd.Series(100*np.cumprod(1+returns),index=dates)
    histories['OTHER']=pd.Series(100*np.cumprod(1+rng.normal(0,.012,len(dates))),index=dates)
    benchmark=pd.Series(100*np.cumprod(1+market),index=dates)
    rows=[{'ticker':t,'status':'ready','score':9-i*.1,'return_1y':float((h.iloc[-1]/h.iloc[-253]-1)*100),'price_basis':'adjusted'} for i,(t,h) in enumerate(histories.items())]
    return rows,histories,{'adjusted':benchmark}


def test_market_adjustment_separates_a_shared_market_cluster():
    rows,histories,benchmarks=fixture()
    raw=analyze_correlations(rows,histories,benchmarks)
    residual=analyze_correlations(rows,histories,benchmarks,market_adjusted=True)
    assert raw['available'] and residual['available']
    assert raw['sample_count']==252
    assert raw['matrix'][0][1]>.9
    assert abs(residual['matrix'][0][1])<.2
    assert raw['clusters'][0]['members']==['AAA','BBB','CCC']
    assert all(len(c['members'])==1 for c in residual['clusters'])
    assert np.isfinite(np.array(raw['matrix'])).all()
    assert len(raw['points'])==4


def test_groups_do_not_chain_together_weakly_correlated_members():
    matrix=np.array([[1,.9,.4],[.9,1,.8],[.4,.8,1]])
    groups=correlation_groups(matrix)
    assert sorted(map(len,groups))==[1,2]
    assert all(min(matrix[i,j] for i in g for j in g)>=.75 for g in groups)


def test_exact_embedding_for_a_small_valid_correlation_matrix():
    matrix=np.array([[1,.5,0],[.5,1,.5],[0,.5,1]])
    xy,coverage=correlation_map(matrix)
    distances=np.linalg.norm(xy[:,None]-xy[None,:],axis=2)
    assert np.allclose(distances,np.sqrt(2*(1-matrix)))
    assert coverage==1


def test_insufficient_common_data_and_incompatible_basis_are_explicit():
    rows,histories,benchmarks=fixture()
    histories['AAA']=histories['AAA'].iloc[-50:]
    assert not analyze_correlations(rows,histories,benchmarks)['available']
    rows,histories,benchmarks=fixture();rows[-1]['price_basis']='unadjusted'
    output=analyze_correlations(rows,histories,benchmarks)
    assert output['available'] and output['excluded']==['OTHER']
    assert len(output['tickers'])==3


def test_performance_windows_are_preserved_when_market_effect_is_removed():
    rows,histories,benchmarks=fixture()
    for row in rows:
        prices=histories[row['ticker']]
        row['return_100d']=round(float((prices.iloc[-1]/prices.iloc[-101]-1)*100),2)
        row['return_200d']=round(float((prices.iloc[-1]/prices.iloc[-201]-1)*100),2)
    raw=analyze_correlations(rows,histories,benchmarks)
    adjusted=analyze_correlations(rows,histories,benchmarks,market_adjusted=True)
    lookup={r['ticker']:r for r in rows}
    for output in (raw,adjusted):
        for point in output['points']:
            for key in ('return_100d','return_200d'):
                assert point[key]==lookup[point['ticker']][key]
