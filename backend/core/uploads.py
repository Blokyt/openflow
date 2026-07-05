"""Validation des fichiers téléversés : liste blanche par magic bytes.

Le Content-Type déclaré par le client et l'extension du nom de fichier ne
sont jamais fiables : seul le contenu binaire fait foi. Les deux endpoints
d'upload (justificatif de transaction, justificatif de soumission) passent
par require_allowed_upload, qui renvoie le type MIME détecté. C'est ce MIME
détecté qui est stocké dans attachments.mime_type et resservi au preview,
jamais celui déclaré par le client.
"""
from fastapi import HTTPException

UPLOAD_REJECT_MESSAGE = (
    "Type de fichier non autorisé : seuls les PDF et les images "
    "(PNG, JPEG, GIF, WebP) sont acceptés."
)

_SIGNATURES = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
]


def detect_allowed_type(content: bytes) -> str | None:
    """Renvoie le type MIME si le contenu correspond à un type autorisé, sinon None."""
    for magic, mime in _SIGNATURES:
        if content.startswith(magic):
            return mime
    # WebP : conteneur RIFF avec le tag WEBP à l'offset 8.
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def require_allowed_upload(content: bytes) -> str:
    """400 avec message français si le contenu n'est ni un PDF ni une image autorisée."""
    detected = detect_allowed_type(content)
    if detected is None:
        raise HTTPException(status_code=400, detail=UPLOAD_REJECT_MESSAGE)
    return detected
