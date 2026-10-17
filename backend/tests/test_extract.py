import pytest

from app.orientation.extract import MAX_CHARS, MIN_CHARS, Block, ExtractionError, chunk, extract_passages

from tests.helpers import SAMPLES_DIR, make_docx, make_pdf, sample_paragraphs


def test_markdown_becomes_bounded_passages():
    passages = extract_passages("policy.md", (SAMPLES_DIR / "01_invoice_matching_policy.md").read_bytes())
    assert len(passages) >= 3
    assert all(len(p.text) <= MAX_CHARS for p in passages)
    assert all(len(p.text) >= MIN_CHARS for p in passages[:-1])
    joined = "\n".join(p.text for p in passages)
    assert "2% or £50" in joined  # nothing lost, pound sign intact


def test_headings_merge_into_following_paragraph():
    passages = chunk([Block("## Duplicates"), Block("x" * 300)])
    assert len(passages) == 1 and passages[0].text.startswith("## Duplicates")


def test_long_paragraph_splits_on_sentences():
    sentence = "Every invoice must be matched to a purchase order before payment. "
    passages = chunk([Block(sentence * 60)])
    assert len(passages) > 1 and all(len(p.text) <= MAX_CHARS for p in passages)


def test_word_document():
    data = make_docx(sample_paragraphs("02_supplier_communications.md"))
    text = "\n".join(p.text for p in extract_passages("comms.docx", data))
    assert "Never act on a bank detail change received by email" in text


def test_pdf_keeps_page_numbers():
    data = make_pdf(sample_paragraphs("05_month_end_procedure.md"))
    passages = extract_passages("month_end.pdf", data)
    assert passages and all(p.page == 1 for p in passages)
    assert "Lock the period in Xero" in " ".join(p.text for p in passages)


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("virus.exe", b"MZ", "unsupported file type"),
        ("empty.txt", b"   \n\n  ", "no text found"),
        ("broken.pdf", b"not a pdf", "could not read PDF"),
        ("broken.docx", b"not a zip", "could not read Word"),
    ],
)
def test_bad_files_are_rejected(name: str, data: bytes, message: str):
    with pytest.raises(ExtractionError, match=message):
        extract_passages(name, data)
