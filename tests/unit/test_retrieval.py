from guardrails.retrieval import Retriever, tokenize, with_notes

ROWS = [
    {"domain": "GST", "prompt": "Due date of CMP-08 for composition dealers?",
     "completion": "CMP-08 is due by the 18th of the month after the quarter."},
    {"domain": "GST", "prompt": "Which form for a refund of unutilised ITC on exports?",
     "completion": "File RFD-01 for the refund claim."},
    {"domain": "PAYROLL", "prompt": "Gratuity formula for 12 years of service?",
     "completion": "Last drawn wages x 15/26 x completed years of service."},
]


def test_tokenize_keeps_section_and_form_numbers_whole_and_in_pieces():
    t = tokenize("Section 17(2) and RFD-11 and cmp-08")
    assert "17(2)" in t and "rfd-11" in t and "cmp-08" in t
    assert "rfd" in t and "11" in t


def test_finds_the_note_for_a_form_name():
    hits = Retriever(ROWS).search("when is CMP-08 due", k=1)
    assert hits and "CMP-08" in hits[0]["prompt"]


def test_finds_the_note_by_topic_words():
    hits = Retriever(ROWS).search("gratuity after twelve years", k=1)
    assert hits and hits[0]["domain"] == "PAYROLL"


def test_nothing_found_returns_empty_and_question_is_unchanged():
    assert Retriever(ROWS).search("zzzz qqqq", k=3) == []
    assert with_notes("hello", []) == "hello"


def test_with_notes_puts_the_question_last():
    out = with_notes("What is the due date?", Retriever(ROWS).search("CMP-08 due", k=1))
    assert out.endswith("Question: What is the due date?") and "CMP-08" in out
