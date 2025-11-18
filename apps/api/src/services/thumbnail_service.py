"""
Thumbnail Service - Generate preview images for files

Generates portrait thumbnails for:
- PDFs: Rasterizes first page to 256x384px JPEG (vertical/portrait)
- Images: Resizes to max 256x384px JPEG with quality=85

Used by /api/documents/{doc_id}/thumbnail endpoint
"""

import io
from pathlib import Path
from typing import Optional

import structlog
from PIL import Image

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

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
    async def generate_thumbnail(file_path: Path, mimetype: str) -> Optional[bytes]:
        """
        Generate thumbnail for any supported file type

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
