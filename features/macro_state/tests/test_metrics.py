from features.macro_state.metrics import episodes,false_contractions,stability,choose_threshold


def test_warning_one_gap_and_preparation_events():
    points=[('2000-02','contraction_warning'),('2000-03','none'),('2000-04','contraction_warning'),
            ('2000-05','none'),('2000-06','unknown'),('2000-07','none'),('2000-08','contraction_warning'),('2000-09','recovery_signal')]
    events=episodes(points,{'contraction_warning'},{'none','unknown'})
    assert len(events)==2 and events[0]['leftCensored']
    assert events[0]['end']=='2000-04' and not events[1]['immature']


def test_false_contraction_count_includes_tails_but_not_bridging_month():
    points=[('2019-09','contraction'),('2019-10','moderate'),('2019-11','contraction'),
            ('2019-12','contraction'),('2020-01','contraction'),('2020-08','contraction')]
    # 2019-11 through 2020-07 is allowed. The before/after portions remain separate.
    result=false_contractions(points)
    assert result['months']==2 and result['events']==2


def test_common_denominator_excludes_unknown_and_immature_only_in_comparison():
    base={m:{'level':'normal'} for m in ('proposal','B0','B1','proposalRevised','B0Revised','B1Revised')}
    rows=[base,{**base,'B1':{'level':'unknown'}},{**base,'immatureReference':True}]
    r=stability(rows,'level')
    assert r['scheduled']==3 and r['commonCount']==1 and r['individual']['B1']['unknown']==1


def test_theta_ties_and_empty_set_use_predeclared_order():
    def candidate(t):return {'theta':t,'timeliness':[{'eventStart':'2001-01','delayMonths':0},{'eventStart':'2007-11','delayMonths':0}],'falseEvents':1}
    assert choose_threshold([candidate(15),candidate(25)],20)==(25,False)
    assert choose_threshold([],20)==(20,True)


def test_open_cycle_false_confirmation_is_separate_from_event_count():
    result=false_contractions([('2030-01','none'),('2030-02','contraction_confirmed')],confirmed='contraction_confirmed')
    assert result['months']==1 and result['events']==0 and result['immatureEvents']==1
