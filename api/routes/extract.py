"""PDF extract routes."""

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from models.extract import ExtractResponse, PageTextResponse
from services.parser import extract_pdf_bytes, extract_pdf_page_text, render_pdf_page_image

router = APIRouter(tags=["extract"])


@router.post("/extract/file", response_model=ExtractResponse)
async def extract_file(file: UploadFile = File(...)) -> ExtractResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件（.pdf）。")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空。")
    try:
        text, pdf_quality, warning = extract_pdf_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return ExtractResponse(
        text=text,
        pdf_quality=pdf_quality,
        source="upload",
        warning=warning,
    )


@router.post("/extract/page-text", response_model=PageTextResponse)
async def extract_page_text(
    file: UploadFile = File(...),
    page: int = Form(...),
) -> PageTextResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件（.pdf）。")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空。")
    try:
        text, page_count = extract_pdf_page_text(data, page_index=page - 1)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return PageTextResponse(page=page, page_count=page_count, text=text)


@router.post("/extract/page-image")
async def extract_page_image(
    file: UploadFile = File(...),
    page: int = Form(...),
    dpi: int = Form(160),
) -> Response:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 PDF 文件（.pdf）。")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空。")
    try:
        image, _ = render_pdf_page_image(data, page_index=page - 1, dpi=dpi)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return Response(content=image, media_type="image/png")
