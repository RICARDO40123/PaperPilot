"""PDF extract routes."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from models.extract import ExtractResponse
from services.parser import extract_pdf_bytes

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
