from benchmarks.olist_cases import cases
from benchmarks.run import same_rows, score_olist
from commercelens.application.contracts import Answer, Evidence, Query


def test_suite_boundaries():
    test_cases = cases()
    assert 40 <= len(test_cases) <= 60
    assert len({case.id for case in test_cases}) == len(test_cases)
    assert all(case.sql or case.family == "unsupported" or case.citations for case in test_cases)


def test_row_semantics():
    assert same_rows([["SP", "0.500000001"], ["RJ", 0.25]], [("RJ", .25), ("SP", .5)], False)
    assert not same_rows([["SP", "0.500000001"], ["RJ", 0.25]], [("RJ", .25), ("SP", .5)], True)
    assert not same_rows([[0.51]], [(0.5,)], True)
    assert not same_rows([[None]], [(0,)], False)


def test_truncation_cannot_pass_scoring():
    case = cases()[0]
    answer = Answer("ok", "sql", "", Evidence(result=Query(["count"], [[5]], truncated=True)))
    score = score_olist(case, answer, [(5,)])
    assert score["sql_executed"] and not score["success"]
