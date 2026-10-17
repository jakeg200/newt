"""Build small Word and PDF files in memory so tests cover every upload format."""

import io
import textwrap

from app.config import REPO_DIR

SAMPLES_DIR = REPO_DIR / "samples" / "accounts_payable"


def make_docx(paragraphs: list[str]) -> bytes:
    import docx

    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def make_pdf(paragraphs: list[str]) -> bytes:
    """A one-page PDF with Helvetica text, one wrapped paragraph after another."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines: list[str] = []
    for p in paragraphs:
        lines += textwrap.wrap(p, 90) + [""]
    ops = ["BT /F1 10 Tf 50 800 Td 12 TL"] + [f"({esc(line)}) Tj T*" for line in lines] + ["ET"]
    stream = "\n".join(ops).encode("cp1252")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def sample_paragraphs(name: str) -> list[str]:
    text = (SAMPLES_DIR / name).read_text(encoding="utf-8")
    return [p.strip().lstrip("# ").strip() for p in text.split("\n\n") if p.strip()]


def five_policy_uploads() -> list[tuple[str, bytes]]:
    """The five sample policies in four formats: Markdown, plain text, Word and PDF."""
    return [
        ("01_invoice_matching_policy.md", (SAMPLES_DIR / "01_invoice_matching_policy.md").read_bytes()),
        ("02_supplier_communications.docx", make_docx(sample_paragraphs("02_supplier_communications.md"))),
        ("03_approval_limits.txt", (SAMPLES_DIR / "03_approval_limits.txt").read_bytes()),
        ("04_gl_coding_guide.md", (SAMPLES_DIR / "04_gl_coding_guide.md").read_bytes()),
        ("05_month_end_procedure.pdf", make_pdf(sample_paragraphs("05_month_end_procedure.md"))),
    ]
