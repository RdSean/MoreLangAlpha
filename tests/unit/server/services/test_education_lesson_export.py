from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookTransitionError,
)


def request(**changes):
    from src.server.app.education.book_models import BookLessonPdfRequest

    return BookLessonPdfRequest.model_validate({
        "sections": [{"role": "material", "markdown": "# Lesson", "html": "<h1>Lesson</h1>"}],
        **changes,
    })


def setup(monkeypatch):
    from src.server.services import education_lesson_export as service

    lesson = AsyncMock(return_value=({"title": "力与运动"}, {"markdown": "# Lesson"}))
    history = AsyncMock(return_value=[{"role": "user", "content": "Why?"}, {"role": "assistant", "content": "Because."}])
    render = AsyncMock(return_value=b"%PDF-test")
    monkeypatch.setattr(service, "_lesson", lesson)
    monkeypatch.setattr(service, "get_book_study_history", history)
    monkeypatch.setattr(service, "render_static_pdf", render)
    return service, lesson, history, render


@pytest.mark.asyncio
@pytest.mark.parametrize("user", ["parent", "student"])
async def test_exports_only_authorized_material_by_default(monkeypatch, user):
    service, lesson, history, render = setup(monkeypatch)
    result = await service.export_lesson_pdf(user_id=user, textbook_id="book", knowledge_point_id="kp", request=request())
    assert result.content == b"%PDF-test"
    assert result.filename == "力与运动.pdf"
    lesson.assert_awaited_once_with(user_id=user, textbook_id="book", knowledge_point_id="kp")
    history.assert_not_awaited()
    html = render.call_args.args[0]
    assert "力与运动" in html and "Lesson" in html
    assert "A4" in html and "color-scheme: light" in html
    assert "我的问答" not in html


@pytest.mark.asyncio
async def test_includes_only_matching_own_public_question_text(monkeypatch):
    service, _, history, render = setup(monkeypatch)
    payload = request(include_questions=True, assignment_id="ae495b2e-f96d-4935-9713-a4b907c553ec", sections=[
        {"role": "material", "markdown": "# Lesson", "html": "<h1>Lesson</h1>"},
        {"role": "user", "markdown": "Why?", "html": "<p>Why?</p>"},
        {"role": "assistant", "markdown": "Because.", "html": "<p>Because.</p>"},
    ])
    await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=payload)
    assert history.call_args.kwargs == {"user_id": "student", "textbook_id": "book", "knowledge_point_id": "kp", "assignment_id": str(payload.assignment_id)}
    html = render.call_args.args[0]
    assert "我的问答" in html and "Why?" in html and "Because." in html


@pytest.mark.asyncio
async def test_rejects_changed_material_without_rendering(monkeypatch):
    service, lesson, _, render = setup(monkeypatch)
    lesson.return_value = ({"title": "New"}, {"markdown": "Updated material"})
    with pytest.raises(TextbookTransitionError):
        await service.export_lesson_pdf(user_id="parent", textbook_id="book", knowledge_point_id="kp", request=request())
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_unauthorized_book_before_rendering(monkeypatch):
    service, lesson, _, render = setup(monkeypatch)
    lesson.side_effect = TextbookNotFoundError("unavailable")
    with pytest.raises(TextbookNotFoundError):
        await service.export_lesson_pdf(user_id="other", textbook_id="book", knowledge_point_id="kp", request=request())
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_failure_does_not_silently_export_material_only(monkeypatch):
    service, _, history, render = setup(monkeypatch)
    history.side_effect = RuntimeError("history unavailable")
    with pytest.raises(RuntimeError):
        await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=request(include_questions=True))
    render.assert_not_awaited()


@pytest.mark.parametrize("section", [
    {"role": "tool", "markdown": "secret", "html": "secret"},
    {"role": "assistant", "markdown": "text", "html": "text", "reasoning": "secret"},
])
def test_strict_sections_reject_process_fields(section):
    with pytest.raises(ValidationError):
        request(sections=[section])


def test_markup_sanitizer_keeps_math_but_not_executable_chrome():
    from src.server.services.education_lesson_export import sanitize_print_html

    html = sanitize_print_html('<p onclick="steal()">正文</p><script>secret()</script><button>Copy</button><iframe src="http://localhost"></iframe><math><mi>x</mi></math><span class="katex" style="height: 1em">y</span><svg viewBox="0 0 10 10"><path d="M0 0L1 1" /></svg>')
    assert "正文" in html and "<math>" in html and "katex" in html and "viewBox" in html
    assert not any(token in html for token in ["onclick", "script", "secret", "button", "Copy", "iframe", "localhost"])


def test_markup_sanitizer_preserves_only_read_only_task_checkboxes():
    from src.server.services.education_lesson_export import sanitize_print_html

    html = sanitize_print_html('<ul><li><input type="checkbox" checked disabled onclick="private()">已完成</li><li><input type="checkbox" disabled>未完成</li></ul><input type="text" value="private"><input type="password" value="private">')
    assert html.count('type="checkbox"') == 2
    assert html.count('checked=""') == 1
    assert html.count('disabled=""') == 2
    assert not any(token in html for token in ['onclick', 'value=', 'password', 'private'])


@pytest.mark.asyncio
async def test_embeds_only_current_textbook_authorized_images(monkeypatch):
    service, _, _, render = setup(monkeypatch)
    asset = AsyncMock(return_value={"content": b"png", "media_type": "image/png"})
    monkeypatch.setattr(service, "open_managed_textbook_asset", asset)
    payload = request(sections=[{"role": "material", "markdown": "# Lesson", "html": '<img src="/api/v1/education/textbooks/book/assets/art-1" alt="图" />'}])
    await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=payload)
    asset.assert_awaited_once_with(user_id="student", textbook_id="book", asset_id="art-1")
    assert "data:image/png;base64,cG5n" in render.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["http://169.254.169.254/", "/api/v1/education/textbooks/other/assets/art-1", "file:///etc/passwd"])
async def test_rejects_external_or_cross_book_image_without_fetch(monkeypatch, source):
    service, _, _, render = setup(monkeypatch)
    asset = AsyncMock()
    monkeypatch.setattr(service, "open_managed_textbook_asset", asset)
    payload = request(sections=[{"role": "material", "markdown": "# Lesson", "html": f'<img src="{source}" />'}])
    with pytest.raises(ValueError, match="图片"):
        await service.export_lesson_pdf(user_id="parent", textbook_id="book", knowledge_point_id="kp", request=payload)
    asset.assert_not_awaited()
    render.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_questions", [False, True])
async def test_rejects_extra_or_stale_question_text(monkeypatch, include_questions):
    service, _, _, render = setup(monkeypatch)
    payload = request(include_questions=include_questions, sections=[
        {"role": "material", "markdown": "# Lesson", "html": "<h1>Lesson</h1>"},
        {"role": "user", "markdown": "Outdated question", "html": "<p>Outdated question</p>"},
    ])
    with pytest.raises(TextbookTransitionError):
        await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=payload)
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_style_tag_escape_before_rendering(monkeypatch):
    service, _, _, render = setup(monkeypatch)
    with pytest.raises(ValueError, match="字体"):
        await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=request(font_css="</style><script>private()</script>"))
    render.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_images_are_loaded_once(monkeypatch):
    service, _, _, render = setup(monkeypatch)
    asset = AsyncMock(return_value={"content": b"png", "media_type": "image/png"})
    monkeypatch.setattr(service, "open_managed_textbook_asset", asset)
    payload = request(sections=[{"role": "material", "markdown": "# Lesson", "html": '<img src="/api/v1/education/textbooks/book/assets/art-1" />' * 2}])
    await service.export_lesson_pdf(user_id="student", textbook_id="book", knowledge_point_id="kp", request=payload)
    asset.assert_awaited_once()
    assert render.call_args.args[0].count("data:image/png;base64,cG5n") == 2
