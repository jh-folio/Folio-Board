from features.macro_state.development import diagnostic_rows
from features.macro_state.inputs import Inputs
from .test_inputs import row


def test_revised_claims_diagnostic_uses_assumed_thursday_but_retains_actual_availability():
    fixed = [row('ICSA', '2000-01-01', '300000', availableAt='2026-09-25T04:59:59Z')]
    rows, basis = diagnostic_rows([], fixed, '2000-01-07T05:59:59.999999Z')
    assert basis == 'revised' and len(rows) == 1
    book = Inputs(rows, '2000-01-07T05:59:59.999999Z')
    assert book.value('ICSA', '2000-01-01') == 300000
    ref = book.refs()[0]
    assert ref['diagnosticAvailability'] is True
    assert ref['actualSourceAvailableAt'].startswith('2026-09-25')
    assert diagnostic_rows([], fixed, '2000-01-07T05:59:59Z')[0] == []
