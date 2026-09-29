from features.macro_state.evaluation_report import summarize_growth, detections


def record(month, signal, level='moderate'):
    return {'month': month, **{m: {'level': level, 'direction': 'flat', 'cycleSignal': signal} for m in ('proposal', 'B0', 'B1')}}


def test_event_started_before_test_is_not_counted_as_new_test_event():
    before = [record('2019-11', 'none'), record('2019-12', 'contraction_warning')]
    rows = [record('2020-01', 'contraction_warning'), record('2020-02', 'contraction_confirmed', 'contraction'),
            record('2020-03', 'none')]
    report = summarize_growth(rows, prefix=before)['proposal']
    assert report['events']['warnings'] == []
    assert report['cycleDetection'][0]['delayMonths'] == 0


def test_nber_allowed_early_detection_and_outside_not_detection():
    assert detections([('2019-09', 'contraction'), ('2020-02', 'moderate')])[0]['detected'] is None
    value = detections([('2019-11', 'contraction'), ('2020-02', 'moderate')])[0]
    assert value['earlyMonths'] == 3 and value['delayMonths'] == 0
