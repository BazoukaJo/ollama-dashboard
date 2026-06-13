"""Tests for Ask? attachment preparation."""
from __future__ import annotations

import base64
import io

import pytest
from app.services.ask_attachments import AttachmentError, prepare_chat_from_attachments


def _png_b64() -> str:
    # Minimal valid 1x1 PNG
    raw = base64.b64decode(
        b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    )
    return base64.b64encode(raw).decode('ascii')


def test_code_snippet_appended_to_prompt():
    out = prepare_chat_from_attachments(
        'Explain this',
        [{'type': 'code', 'name': 'demo.py', 'content': 'print("hi")', 'language': 'python'}],
    )
    assert '```python' in out['prompt']
    assert 'print("hi")' in out['prompt']
    assert 'Explain this' in out['prompt']
    assert out.get('images') is None


def test_image_requires_vision_model():
    with pytest.raises(AttachmentError, match='does not support images'):
        prepare_chat_from_attachments(
            'What is this?',
            [{'type': 'image', 'name': 'x.png', 'content': _png_b64()}],
            model_has_vision=False,
        )


def test_image_passes_for_vision_model():
    out = prepare_chat_from_attachments(
        'Describe',
        [{'type': 'image', 'name': 'x.png', 'content': _png_b64()}],
        model_has_vision=True,
    )
    assert out['images'] and len(out['images']) == 1
    assert out['prompt'] == 'Describe'


def test_image_only_default_prompt():
    out = prepare_chat_from_attachments(
        '',
        [{'type': 'image', 'name': 'x.png', 'content': _png_b64()}],
        model_has_vision=True,
    )
    assert 'attached image' in out['prompt'].lower()


def test_pdf_text_extraction():
    pytest.importorskip('pypdf')
    from pypdf import PdfWriter

    buf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    # Blank page has no text — use a writer with text if needed
    writer.write(buf)
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')

    with pytest.raises(AttachmentError, match='No extractable text'):
        prepare_chat_from_attachments(
            'Summarize',
            [{'type': 'pdf', 'name': 'empty.pdf', 'content': b64}],
        )


def test_docx_text_extraction():
    pytest.importorskip('docx')
    from docx import Document

    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph('Hello from Word')
    doc.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')

    out = prepare_chat_from_attachments(
        'Summarize',
        [{'type': 'doc', 'name': 'note.docx', 'content': b64}],
    )
    assert 'Hello from Word' in out['prompt']
    assert '[Document: note.docx]' in out['prompt']


def test_empty_request_rejected():
    with pytest.raises(AttachmentError):
        prepare_chat_from_attachments('', [])
