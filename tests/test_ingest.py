from narrow.ingest import ingest_source


def test_ingests_local_markdown_with_source_metadata(tmp_path):
    source = tmp_path / "report.md"
    source.write_text("# Finding\n\nLeast privilege is required.", encoding="utf-8")

    destination = ingest_source(source, root=tmp_path / "kb")

    assert destination.suffix == ".md"
    assert "Source:" in destination.read_text(encoding="utf-8")
    assert "Least privilege" in destination.read_text(encoding="utf-8")


def test_ingests_html_without_scripts_or_styles(tmp_path):
    source = tmp_path / "article.html"
    source.write_text(
        "<html><style>hidden</style><body><h1>Article</h1>"
        "<p>Useful <b>content</b>.</p><script>alert(1)</script></body></html>",
        encoding="utf-8",
    )

    destination = ingest_source(source, root=tmp_path / "kb")
    text = destination.read_text(encoding="utf-8")

    assert "Article" in text
    assert "Useful content." in text
    assert "alert" not in text
    assert "hidden" not in text


def test_rejects_localhost_url(tmp_path):
    try:
        ingest_source("http://127.0.0.1/private", root=tmp_path / "kb")
    except ValueError as exc:
        assert "private" in str(exc)
    else:
        raise AssertionError("private URLs must be rejected")


def test_extracts_common_office_formats(tmp_path):
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation
    from pptx.util import Inches

    document = Document()
    document.add_paragraph("Word context")
    docx_path = tmp_path / "notes.docx"
    document.save(docx_path)

    workbook = Workbook()
    workbook.active.append(["Excel", "context"])
    xlsx_path = tmp_path / "data.xlsx"
    workbook.save(xlsx_path)

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1)).text = "PowerPoint context"
    pptx_path = tmp_path / "slides.pptx"
    presentation.save(pptx_path)

    outputs = [ingest_source(path, root=tmp_path / "kb").read_text(encoding="utf-8") for path in (docx_path, xlsx_path, pptx_path)]

    assert "Word context" in outputs[0]
    assert "Excel | context" in outputs[1]
    assert "PowerPoint context" in outputs[2]


def test_accepts_images_and_media_as_local_assets(tmp_path):
    from PIL import Image

    image_path = tmp_path / "diagram.png"
    Image.new("RGB", (32, 24), color="white").save(image_path)
    image_text = ingest_source(image_path, root=tmp_path / "kb").read_text(encoding="utf-8")

    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"not a real video")
    video_text = ingest_source(video_path, root=tmp_path / "kb").read_text(encoding="utf-8")

    assert "Image size: 32x24" in image_text
    assert "Media type: .mp4" in video_text
