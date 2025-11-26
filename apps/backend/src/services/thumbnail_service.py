"""
Thumbnail Service - Generate preview images for files

V2: Caches thumbnails in MinIO for persistence and lazy generation.

Generates portrait thumbnails for:
- PDFs: Rasterizes first page to 256x384px JPEG (vertical/portrait)
- Images: Resizes to max 256x384px JPEG with quality=85

Architecture:
1. Check MinIO thumbnails bucket for cached thumbnail
2. If not found, generate from source file and cache in MinIO
3. Return cached or freshly generated thumbnail

Used by /api/documents/{doc_id}/thumbnail endpoint
"""

import io
import tempfile
from pathlib import Path
from typing import Optional

import structlog
from PIL import Image
from minio.error import S3Error

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .minio_service import minio_service

logger = structlog.get_logger(__name__)

# Thumbnail configuration - Portrait/Vertical format (2:3 aspect ratio)
THUMBNAIL_WIDTH = 256  # Fixed width
THUMBNAIL_HEIGHT = 384  # Fixed height (1.5x width for vertical)
THUMBNAIL_QUALITY = 85  # JPEG quality (0-100) - Higher quality for PDFs
PDF_DPI_SCALE = 2.0  # Render PDFs at 2x resolution for better quality
THUMBNAIL_FORMAT = "JPEG"


class ThumbnailService:
    """Service for generating file thumbnails"""

    @staticmethod
    async def generate_pdf_thumbnail(file_path: Path) -> Optional[bytes]:
        """
        Generate high-quality vertical thumbnail from PDF first page

        Args:
            file_path: Path to PDF file

        Returns:
            JPEG thumbnail bytes (256x384px portrait) or None if failed
        """
        if not fitz:
            logger.warning("PyMuPDF not available, cannot generate PDF thumbnail")
            return None

        try:
            # Open PDF
            doc = fitz.open(str(file_path))

            if doc.page_count == 0:
                logger.warning("PDF has no pages", path=str(file_path))
                return None

            # Get first page
            page = doc[0]

            # Render at higher resolution for better quality (2x scale = 144 DPI)
            # This produces a clearer image before downsampling
            zoom_matrix = fitz.Matrix(PDF_DPI_SCALE, PDF_DPI_SCALE)
            pix = page.get_pixmap(matrix=zoom_matrix)

            # Convert pixmap to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Calculate dimensions to fit in portrait thumbnail (256x384)
            # Maintain aspect ratio but fit within bounds
            aspect_ratio = img.width / img.height
            target_aspect = THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT

            if aspect_ratio > target_aspect:
                # Image is wider than target - fit by width
                new_width = THUMBNAIL_WIDTH
                new_height = int(THUMBNAIL_WIDTH / aspect_ratio)
            else:
                # Image is taller than target - fit by height
                new_height = THUMBNAIL_HEIGHT
                new_width = int(THUMBNAIL_HEIGHT * aspect_ratio)

            # Resize with high-quality Lanczos resampling
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to JPEG with high quality
            output = io.BytesIO()
            img.convert("RGB").save(output, format=THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY, optimize=True)
            output.seek(0)

            doc.close()

            logger.info(
                "Generated PDF thumbnail",
                path=str(file_path),
                size=f"{img.width}x{img.height}",
                bytes=output.getbuffer().nbytes,
            )

            return output.getvalue()

        except Exception as e:
            logger.error("Failed to generate PDF thumbnail", error=str(e), path=str(file_path))
            return None

    @staticmethod
    async def generate_image_thumbnail(file_path: Path) -> Optional[bytes]:
        """
        Generate high-quality vertical thumbnail from image file

        Args:
            file_path: Path to image file (PNG, JPEG, HEIC, etc.)

        Returns:
            JPEG thumbnail bytes (256x384px portrait) or None if failed
        """
        try:
            # Open image
            img = Image.open(file_path)

            # Convert RGBA to RGB (for PNG with transparency)
            if img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background

            # Calculate dimensions to fit in portrait thumbnail (256x384)
            aspect_ratio = img.width / img.height
            target_aspect = THUMBNAIL_WIDTH / THUMBNAIL_HEIGHT

            if aspect_ratio > target_aspect:
                # Image is wider than target - fit by width
                new_width = THUMBNAIL_WIDTH
                new_height = int(THUMBNAIL_WIDTH / aspect_ratio)
            else:
                # Image is taller than target - fit by height
                new_height = THUMBNAIL_HEIGHT
                new_width = int(THUMBNAIL_HEIGHT * aspect_ratio)

            # Resize with high-quality Lanczos resampling
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to JPEG with high quality
            output = io.BytesIO()
            img.convert("RGB").save(output, format=THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY, optimize=True)
            output.seek(0)

            logger.info(
                "Generated image thumbnail",
                path=str(file_path),
                size=f"{img.width}x{img.height}",
                bytes=output.getbuffer().nbytes,
            )

            return output.getvalue()

        except Exception as e:
            logger.error("Failed to generate image thumbnail", error=str(e), path=str(file_path))
            return None

    @staticmethod
    async def get_or_generate_thumbnail(
        doc_id: str,
        minio_bucket: Optional[str],
        minio_key: Optional[str],
        mimetype: str
    ) -> Optional[bytes]:
        """
        Get cached thumbnail from MinIO or generate new one (V2)

        Args:
            doc_id: Document ID (used as thumbnail key)
            minio_bucket: Source file bucket (None for legacy)
            minio_key: Source file key (None for legacy)
            mimetype: MIME type of file

        Returns:
            JPEG thumbnail bytes or None if failed
        """
        thumbnail_key = f"{doc_id}.jpg"

        # Step 1: Try to get cached thumbnail from MinIO
        try:
            thumbnail_bytes = await minio_service.download_file(
                minio_service.thumbnails_bucket,
                thumbnail_key
            )
            logger.info(
                "Served cached thumbnail from MinIO",
                doc_id=doc_id,
                bytes=len(thumbnail_bytes)
            )
            return thumbnail_bytes
        except S3Error as e:
            if e.code != "NoSuchKey":
                logger.warning(
                    "MinIO error fetching thumbnail",
                    doc_id=doc_id,
                    error=str(e)
                )
            # Thumbnail not cached, need to generate

        # Step 2: Generate thumbnail from source file
        if not minio_bucket or not minio_key:
            logger.warning(
                "Cannot generate thumbnail - no source file in MinIO",
                doc_id=doc_id
            )
            return None

        try:
            # Download source file to temp path
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
                tmp_path = Path(tmp.name)

            try:
                await minio_service.download_to_path(minio_bucket, minio_key, str(tmp_path))

                # Generate thumbnail based on MIME type
                thumbnail_bytes = await ThumbnailService.generate_thumbnail(tmp_path, mimetype)

                if thumbnail_bytes:
                    # Cache thumbnail in MinIO for future requests
                    try:
                        await minio_service.upload_file(
                            minio_service.thumbnails_bucket,
                            thumbnail_key,
                            io.BytesIO(thumbnail_bytes),
                            len(thumbnail_bytes),
                            content_type="image/jpeg"
                        )
                        logger.info(
                            "Cached thumbnail in MinIO",
                            doc_id=doc_id,
                            bytes=len(thumbnail_bytes)
                        )
                    except Exception as cache_err:
                        logger.warning(
                            "Failed to cache thumbnail in MinIO",
                            doc_id=doc_id,
                            error=str(cache_err)
                        )

                return thumbnail_bytes

            finally:
                tmp_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(
                "Failed to generate thumbnail from source",
                doc_id=doc_id,
                error=str(e),
                exc_info=True
            )
            return None

    @staticmethod
    async def generate_thumbnail(file_path: Path, mimetype: str) -> Optional[bytes]:
        """
        Generate thumbnail for any supported file type (internal method)

        Args:
            file_path: Path to file
            mimetype: MIME type of file

        Returns:
            JPEG thumbnail bytes or None if not supported/failed
        """
        if mimetype == "application/pdf":
            return await ThumbnailService.generate_pdf_thumbnail(file_path)
        elif mimetype.startswith("image/"):
            return await ThumbnailService.generate_image_thumbnail(file_path)
        else:
            logger.debug("Thumbnail not supported for MIME type", mimetype=mimetype)
            return None


# Singleton instance
thumbnail_service = ThumbnailService()
