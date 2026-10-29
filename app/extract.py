"""Text extraction for uploaded documents, with content checks (never trusts the filename alone)."""
import io
import re
import zipfile

from .core import ApiError

ALLOWED = {".txt", ".md", ".csv", ".json", ".pdf", ".docx"}
MAX_TEXT_CHARS = 200_000
MAX_DOCX_UNCOMPRESSED = 30 * 1024 * 1024


def extract_text(filename: str, raw: bytes) -> str:
    name = filename.lower()
    ext = name[name.rfind("."):] if "." in name else ""
    if ext not in ALLOWED:
        raise ApiError(400, "Unsupported file type. Upload a PDF, Word (.docx), .txt, .md, .csv or .json file.")
    if not raw:
        raise ApiError(400, "That file is empty.")
    if ext == ".pdf":
        if not raw.startswith(b"%PDF-"):
            raise ApiError(400, "That file is not a valid PDF.")
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise ApiError(400, "Encrypted PDFs are not supported.")
            parts, total = [], 0
            for page in reader.pages[:300]:
                t = page.extract_text() or ""
                parts.append(t)
                total += len(t)
                if total > MAX_TEXT_CHARS:
                    break
            text = "\n\n".join(parts)
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, "Could not read that PDF.")
    elif ext == ".docx":
        if not raw.startswith(b"PK"):
            raise ApiError(400, "That file is not a valid Word document.")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                info = z.getinfo("word/document.xml")
                if info.file_size > MAX_DOCX_UNCOMPRESSED:
                    raise ApiError(400, "That document is too large to process.")
                xml = z.read("word/document.xml").decode("utf-8", "replace")
        except ApiError:
            raise
        except Exception:
            raise ApiError(400, "Could not read that Word document.")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
    else:
        if b"\x00" in raw[:8192]:
            raise ApiError(400, "That file looks like binary data, not text.")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ApiError(400, "Text files must be UTF-8 encoded.")
    text = text.strip()
    if not text:
        raise ApiError(400, "No readable text was found in that file. Scanned images are not supported.")
    return text[:MAX_TEXT_CHARS]
