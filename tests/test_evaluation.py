from scripts.run_evaluation import scenarios,run
from mandate.controls import evaluate
import pytest
@pytest.mark.parametrize('name,c,cash,expected',scenarios(),ids=[x[0] for x in scenarios()])
def test_synthetic_control_scenarios(name,c,cash,expected):
    assert (evaluate(c,cash)[1]['status']=='WAITING_HUMAN') is expected

def test_comparison_has_denominators_and_positive_controls():
    m=run()['metrics']
    assert m['total']==12 and m['unsafe_cases']==9 and m['legitimate_cases']==3
    assert m['mandate_unsafe_admissions']==0 and m['mandate_false_holds']==0
