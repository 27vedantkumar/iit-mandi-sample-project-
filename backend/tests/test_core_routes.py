import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.future import select

from backend.app.main import app
from backend.app.database.connection import init_db, AsyncSessionLocal
from backend.app.models.entities import Course

async def get_or_create_test_course() -> Course:
    """Helper to ensure an active test course exists in the database."""
    await init_db()
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Course).filter(Course.code == "OS_101"))
        course = res.scalars().first()
        if not course:
            course = Course(
                code="OS_101",
                title="Operating Systems & Concurrency",
                description="Test Course for Automated QA Verification",
                domain="Computer Science",
                is_demo_course=True,
                status="READY"
            )
            db.add(course)
            await db.commit()
            await db.refresh(course)
        return course


# ==============================================================================
# 1. Integration Tests for Grounded AI Tutor (/api/tutor/chat and /api/tutor/ask)
# ==============================================================================

@pytest.mark.asyncio
async def test_tutor_chat_happy_path_grounded():
    """
    Happy Path:
    A valid, in-domain student question retrieves verified course chunks,
    passes the Grounding Gate, and returns a grounded answer with citations.
    """
    course = await get_or_create_test_course()

    mocked_retrieval = {
        "query": "What are the four Coffman conditions for deadlock?",
        "grounding_confidence": 0.94,
        "results": [
            {
                "knowledge_unit_id": "ku_001",
                "source_file": "Operating_Systems_Ch7_Deadlocks.pdf",
                "source_type": "pdf",
                "source": {"page": 42, "section": "7.2"},
                "content": "According to Coffman, four conditions must hold simultaneously for a deadlock to occur: Mutual Exclusion, Hold & Wait, No Preemption, Circular Wait.",
                "similarity_score": 0.94
            }
        ]
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("backend.app.ai.tutor.HybridRetriever.retrieve", new=AsyncMock(return_value=mocked_retrieval)):
            with patch("backend.app.ai.tutor.ai_provider.generate_response", new=AsyncMock(return_value="Deadlock requires four simultaneous Coffman conditions.")):
                
                payload = {
                    "course_id": course.id,
                    "message": "What are the four Coffman conditions for deadlock?",
                    "mode": "socratic",
                    "language": "en",
                    "scope": "course"
                }

                # Verify both /api/tutor/chat and /api/tutor/ask endpoints
                for endpoint in ["/api/tutor/chat", "/api/tutor/ask"]:
                    response = await client.post(endpoint, json=payload)
                    assert response.status_code == 200
                    
                    data = response.json()
                    assert data["grounded"] is True
                    assert data["confidence"] >= 0.75
                    assert len(data["citations"]) > 0
                    assert "Deadlock" in data["answer"]
                    assert data["citations"][0]["document"] == "Operating_Systems_Ch7_Deadlocks.pdf"


@pytest.mark.asyncio
async def test_tutor_chat_refusal_path_out_of_domain():
    """
    Refusal / Error Path:
    An out-of-domain or ungrounded question fails the Grounding Gate threshold
    and is safely rejected with a zero-hallucination refusal envelope.
    """
    course = await get_or_create_test_course()

    mocked_unsupported_retrieval = {
        "query": "What is the secret recipe for French chocolate soufflé?",
        "grounding_confidence": 0.12,
        "results": []
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("backend.app.ai.tutor.HybridRetriever.retrieve", new=AsyncMock(return_value=mocked_unsupported_retrieval)):
            
            payload = {
                "course_id": course.id,
                "message": "What is the secret recipe for French chocolate soufflé?",
                "mode": "beginner",
                "scope": "course"
            }

            response = await client.post("/api/tutor/chat", json=payload)
            assert response.status_code == 200

            data = response.json()
            assert data["grounded"] is False
            assert data["confidence"] < 0.68
            assert len(data["citations"]) == 0
            assert "evidence" in data["answer"].lower() or "cannot verify" in data["answer"].lower()
            assert data["recommended_action"]["action"] == "expand_scope_or_rephrase"


# ==============================================================================
# 2. Integration Tests for Course Material Ingestion (/api/courses/{id}/upload)
# ==============================================================================

@pytest.mark.asyncio
async def test_course_upload_happy_path():
    """
    Happy Path:
    Uploading a valid course document (PDF/TXT/PPTX) successfully parses,
    extracts knowledge units, and returns HTTP 200 with metadata.
    """
    course = await get_or_create_test_course()

    mocked_ingestion_result = {
        "document_id": "doc_test_123",
        "units_created": 5,
        "status": "PROCESSED",
        "filename": "Lecture8_Virtual_Memory.pdf"
    }

    file_content = b"%PDF-1.4 sample virtual memory textbook chapter bytes"
    files = {"file": ("Lecture8_Virtual_Memory.pdf", file_content, "application/pdf")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("backend.app.ingestion.multimodal_service.MultimodalIngestionService.process_document", new=AsyncMock(return_value=mocked_ingestion_result)):
            
            response = await client.post(f"/api/courses/{course.id}/upload", files=files)
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "success"
            assert "Lecture8_Virtual_Memory.pdf" in data["message"]
            assert data["ingestion_result"]["units_created"] == 5


@pytest.mark.asyncio
async def test_course_upload_error_path_nonexistent_course():
    """
    Error Path:
    Attempting to upload documents to a non-existent course ID returns HTTP 404.
    """
    await init_db()
    fake_course_id = "00000000-0000-0000-0000-000000000000"
    files = {"file": ("Test_Doc.pdf", b"sample content", "application/pdf")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/courses/{fake_course_id}/upload", files=files)
        assert response.status_code == 404
        assert response.json()["detail"] == "Course not found."


@pytest.mark.asyncio
async def test_course_upload_error_path_empty_file():
    """
    Error Path:
    Uploading an empty 0-byte file is rejected with HTTP 400.
    """
    course = await get_or_create_test_course()
    empty_files = {"file": ("Empty_Notes.pdf", b"", "application/pdf")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(f"/api/courses/{course.id}/upload", files=empty_files)
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_course_upload_error_path_processing_failure():
    """
    Error Path:
    Unhandled parser or extraction failure in ingestion returns HTTP 500.
    """
    course = await get_or_create_test_course()
    files = {"file": ("Corrupt.pdf", b"corrupted header bytes", "application/pdf")}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch("backend.app.ingestion.multimodal_service.MultimodalIngestionService.process_document", new=AsyncMock(side_effect=RuntimeError("Corrupt PDF streams"))):
            
            response = await client.post(f"/api/courses/{course.id}/upload", files=files)
            assert response.status_code == 500
            assert "Ingestion failed" in response.json()["detail"]
