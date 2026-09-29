from decimal import Decimal as D

import pytest

from features.macro_state.rules import (
    shift_months, direction, inflation_level, financial_level, financial_direction,
    stress_level, contraction, growth_level, growth_direction, confidence,
    kleene_and, kleene_exists, cycle_choice, corroboration,
)


@pytest.mark.parametrize('day,months,expected', [
    ('2026-05-31', -3, '2026-02-28'), ('2024-05-31', -3, '2024-02-29'),
    ('2026-09-15', -3, '2026-06-15'), ('2025-12-01', 3, '2026-03-01'),
])
def test_calendar_shift(day, months, expected):
    assert shift_months(day, months) == expected


@pytest.mark.parametrize('market,month,value,expected', [
    ('US', '2011-12-01', '2', 'unknown'), ('US', '2012-01-01', '1.5', 'near_reference'),
    ('US', '2012-01-01', '2.5', 'near_reference'), ('US', '2012-01-01', '2.5001', 'above_reference'),
    ('US', '2012-01-01', '4', 'above_reference'), ('US', '2012-01-01', '4.0001', 'high'),
    ('US', '2012-01-01', '1.4999', 'below_reference'), ('KR', '2006-12-01', '3', 'unknown'),
    ('KR', '2015-12-01', '2', 'below_reference'), ('KR', '2016-01-01', '2', 'near_reference'),
    ('KR', '2007-01-01', '2.5', 'near_reference'), ('KR', '2010-01-01', '2', 'near_reference'),
    ('KR', '2015-12-01', '5.5', 'above_reference'), ('KR', '2015-12-01', '5.5001', 'high'),
])
def test_inflation_uses_observation_month_and_exact_bounds(market, month, value, expected):
    assert inflation_level(market, month, D(value)) == expected


@pytest.mark.parametrize('delta,threshold,inclusive,expected', [
    ('0.25','0.25',True,'rising'), ('-0.25','0.25',True,'falling'),
    ('0.3','0.3',False,'flat'), ('0.30001','0.3',False,'rising'),
    ('-0.1','0.1',False,'flat'), (None,'0.1',False,'unknown'),
])
def test_direction_boundaries(delta, threshold, inclusive, expected):
    assert direction(None if delta is None else D(delta), D(threshold), inclusive=inclusive) == expected


@pytest.mark.parametrize('rate,nfci,expected', [('0.25','-0.11','mixed'), ('0.25','0.1','rising'),
    ('0','0.11','flat'), ('-0.25','0','falling'), ('0.25',None,'unknown')])
def test_us_financial_direction(rate,nfci,expected):
    assert financial_direction(D(rate), None if nfci is None else D(nfci)) == expected


@pytest.mark.parametrize('market,value,expected', [('US','0.25','neutral'), ('US','-0.2501','loose'),
    ('KR','1','neutral'), ('KR','1.01','tight')])
def test_financial_level(market,value,expected):
    assert financial_level(market,D(value)) == expected


@pytest.mark.parametrize('value,expected', [('0','normal'), ('0.1','elevated'), ('1','elevated'), ('1.01','high')])
def test_stress(value,expected):
    assert stress_level(D(value)) == expected


@pytest.mark.parametrize('gdp,ip,sahm,expected', [('-1','-1',None,True), (None,None,True,True),
    ('1','1',None,None), ('-1',None,False,None), ('1','1',False,False)])
def test_contraction_true_path_precedes_missing(gdp,ip,sahm,expected):
    assert contraction(None if gdp is None else D(gdp), None if ip is None else D(ip), sahm) is expected


def test_growth_trend_missing_is_not_moderate_or_cycle_unknown():
    assert growth_level(D(1),D(2),False,None,None) == 'unknown'
    assert contraction(D(1),D(2),False) is False
    assert growth_level(D('1.25'),D(3),False,D(1),D(2)) == 'strong'
    assert growth_level(D('.75'),D(1),False,D(1),D(2)) == 'moderate'
    assert growth_direction([D('.25'),D('.5'),D('.1')]) == 'flat'
    assert growth_direction([D(1),D(1),D('-1')]) == 'rising'
    assert growth_direction([None,D(1),None]) == 'unknown'


@pytest.mark.parametrize('level,direction_value,stale,total,missing,conflict,aux,expected', [
    ('unknown','rising',0,3,False,False,False,'low'),
    ('contraction','rising',0,3,True,False,False,'low'),
    ('strong','rising',2,3,False,False,False,'low'),
    ('strong','rising',1,3,False,False,False,'medium'),
    ('strong','rising',0,3,False,False,True,'medium'),
    ('strong','rising',0,3,False,True,False,'low'),
    ('strong','rising',0,3,False,False,False,'high'),
])
def test_confidence_priority(level,direction_value,stale,total,missing,conflict,aux,expected):
    assert confidence(level,direction_value,stale,total,missing,conflict,aux) == expected


@pytest.mark.parametrize('a,b,and_expected,exists_expected', [
    (True,True,True,True),(True,None,None,True),(False,None,False,None),
    (None,None,None,None),(False,False,False,False),(True,False,False,True),
])
def test_kleene(a,b,and_expected,exists_expected):
    assert kleene_and(a,b) is and_expected
    assert kleene_exists([a,b]) is exists_expected


@pytest.mark.parametrize('conditions,expected,quality', [
    ({'Q':True,'R':True,'K':True,'W':True},'recovery_confirmed','high'),
    ({'Q':None,'R':False,'K':True,'W':True},'contraction_confirmed','low'),
    ({'Q':False,'R':True,'K':True,'W':False},'recovery_signal','high'),
    ({'Q':False,'R':False,'K':False,'W':False},'none','high'),
    ({'Q':False,'R':False,'K':False,'W':None},'unknown','low'),
])
def test_memoryless_priority(conditions,expected,quality):
    assert cycle_choice(conditions)[0:2] == (expected,quality)


@pytest.mark.parametrize('signal,current,past,expected', [
    ('contraction_warning','-.7',[], 'agrees'), ('contraction_confirmed','-.69',[], 'disagrees'),
    ('recovery_signal','.21',['-.7'], 'strongly_agrees'), ('recovery_confirmed','.2',['-.7'], 'agrees'),
    ('recovery_signal','-.7',['-.7'], 'disagrees'), ('recovery_signal','1',['0'], 'disagrees'),
    ('none','1',['-.7'], 'not_available'), ('unknown','1',['-.7'], 'not_available'),
])
def test_cfnai_corroboration(signal,current,past,expected):
    assert corroboration(signal,D(current),list(map(D,past))) == expected
    assert corroboration(signal,D(current),list(map(D,past)),stale=True) == 'not_available'
