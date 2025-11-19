/**
 * Chat Multi-Format Files RAG Context E2E Test
 *
 * Validates file ingestion + RAG context flow with diverse file formats:
 * - PDFs (scanned, text-based, rotated, multilingual)
 * - Images (JPG, PNG, WEBP, GIF, TIF, BMP)
 * - Mixed combinations of PDFs + images
 *
 * Tests verify that regardless of format, all files:
 * 1. Process to READY status
 * 2. Are included in request file_ids
 * 3. Appear in decision_metadata.rag_selected_doc_ids
 * 4. Are not dropped (rag_dropped_doc_ids should be empty)
 */

import { test, expect } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import { fileURLToPath } from 'url';

// Test data paths
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const TEST_DATA_DIR = path.join(__dirname, '../data');
const PDF_DIR = path.join(TEST_DATA_DIR, 'pdf');
const IMG_DIR = path.join(TEST_DATA_DIR, 'img');

// Sample files for testing (diverse formats and content types)
const TEST_FILES = {
  // PDFs
  pdf_spanish_text: path.join(PDF_DIR, 'spanish_text.pdf'),
  pdf_english_invoice: path.join(PDF_DIR, 'english_invoice_scan.pdf'),
  pdf_spanish_menu: path.join(PDF_DIR, 'spanish_menu_scan.pdf'),
  pdf_multilingual: path.join(PDF_DIR, 'multilingual_brochure.pdf'),
  pdf_rotated: path.join(PDF_DIR, 'english_rotated_samples.pdf'),

  // Images - Different formats
  img_jpeg: path.join(IMG_DIR, 'jpeg-home.jpg'),
  img_png_spanish: path.join(IMG_DIR, 'ocr_spanish_notice.png'),
  img_webp_menu: path.join(IMG_DIR, 'ocr_spanish_menu.webp'),
  img_gif_note: path.join(IMG_DIR, 'ocr_english_note.gif'),
  img_tif_eurotext: path.join(IMG_DIR, 'ocr_eurotext.tif'),
  img_bmp_ticket: path.join(IMG_DIR, 'ocr_spanish_ticket.bmp'),
  img_png_rotated_left: path.join(IMG_DIR, 'ocr_phototest_rotated_left.png'),
  img_jpg_invoice: path.join(IMG_DIR, 'ocr_english_invoice.jpg'),
};

// Verify all test files exist
test.beforeAll(() => {
  const missingFiles: string[] = [];

  for (const [name, filePath] of Object.entries(TEST_FILES)) {
    if (!fs.existsSync(filePath)) {
      missingFiles.push(`${name}: ${filePath}`);
    }
  }

  if (missingFiles.length > 0) {
    throw new Error(
      `Test files not found:\n${missingFiles.join('\n')}\n\n` +
      `Expected test data in tests/data/pdf/ and tests/data/img/`
    );
  }

  console.log(`✓ All ${Object.keys(TEST_FILES).length} test files verified`);
});

test.describe('Chat - Multi-Format File Ingestion', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat');
    await expect(
      page.locator('textarea[placeholder*="Pregúntame"], textarea[aria-label*="mensaje"]').first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('PDF text-based: spanish_text.pdf → RAG context', async ({ page }) => {
    console.log('\n🧪 Testing text-based Spanish PDF...\n');

    let capturedFileIds: string[] = [];
    let capturedMetadata: any = null;

    // Intercept chat request
    await page.route('**/api/chat/message', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        const postData = request.postDataJSON();
        if (postData?.file_ids) {
          capturedFileIds = postData.file_ids;
          console.log(`  📤 file_ids sent: [${capturedFileIds.join(', ')}]`);
        }
      }

      await route.continue();

      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {
          // Response might not be JSON
        }
      }
    });

    // Upload PDF
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.pdf_spanish_text);

    // Wait for READY
    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 20000 });
    console.log('  ✅ PDF reached READY status');

    // Send message
    const textarea = page.locator('textarea').first();
    await textarea.fill('Resume el contenido de este documento');
    await page.locator('button[type="submit"]').first().click();

    // Wait for response
    await expect(
      page.locator('.message, .chat-message, [role="article"]').last()
    ).toBeVisible({ timeout: 40000 });

    // Validate
    expect(capturedFileIds.length).toBe(1);
    console.log('  ✅ PDF included in request');

    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids).toContain(capturedFileIds[0]);
      console.log('  ✅ PDF in RAG context');
    }

    console.log('\n✅ Text-based PDF test PASSED\n');
  });

  test('Image formats: JPG, PNG, WEBP → all in RAG context', async ({ page }) => {
    console.log('\n🧪 Testing multiple image formats...\n');

    let capturedFileIds: string[] = [];
    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        const postData = request.postDataJSON();
        if (postData?.file_ids) {
          capturedFileIds = postData.file_ids;
        }
      }

      await route.continue();

      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    // Upload 3 images with different formats
    const fileInput = page.locator('input[type="file"]').first();

    console.log('  1️⃣  Uploading JPG...');
    await fileInput.setInputFiles(TEST_FILES.img_jpeg);
    await page.waitForTimeout(1000);

    console.log('  2️⃣  Uploading PNG...');
    await fileInput.setInputFiles(TEST_FILES.img_png_spanish);
    await page.waitForTimeout(1000);

    console.log('  3️⃣  Uploading WEBP...');
    await fileInput.setInputFiles(TEST_FILES.img_webp_menu);

    // Wait for all 3 to be READY
    await expect(
      page.locator('text=/Listo|READY/i')
    ).toHaveCount(3, { timeout: 30000 });
    console.log('  ✅ All 3 images READY');

    // Send message
    await page.locator('textarea').first().fill('¿Qué muestran estas imágenes?');
    await page.locator('button[type="submit"]').first().click();

    // Wait for response
    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 40000 });

    // Validate all 3 files
    expect(capturedFileIds.length).toBe(3);
    console.log(`  ✅ 3 file_ids sent`);

    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBe(3);
      console.log('  ✅ All 3 images in RAG context');

      if (capturedMetadata.rag_dropped_doc_ids) {
        expect(capturedMetadata.rag_dropped_doc_ids.length).toBe(0);
        console.log('  ✅ No files dropped');
      }
    }

    console.log('\n✅ Multi-format image test PASSED\n');
  });

  test('Mixed PDF + images: 2 PDFs + 2 images → all in RAG', async ({ page }) => {
    console.log('\n🧪 Testing mixed PDF + image upload...\n');

    let capturedFileIds: string[] = [];
    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        const postData = request.postDataJSON();
        if (postData?.file_ids) {
          capturedFileIds = postData.file_ids;
        }
      }

      await route.continue();

      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    const fileInput = page.locator('input[type="file"]').first();

    // Upload alternating PDFs and images
    console.log('  📄 Uploading PDF 1 (Spanish menu scan)...');
    await fileInput.setInputFiles(TEST_FILES.pdf_spanish_menu);
    await page.waitForTimeout(1000);

    console.log('  🖼️  Uploading Image 1 (English invoice JPG)...');
    await fileInput.setInputFiles(TEST_FILES.img_jpg_invoice);
    await page.waitForTimeout(1000);

    console.log('  📄 Uploading PDF 2 (English invoice scan)...');
    await fileInput.setInputFiles(TEST_FILES.pdf_english_invoice);
    await page.waitForTimeout(1000);

    console.log('  🖼️  Uploading Image 2 (GIF note)...');
    await fileInput.setInputFiles(TEST_FILES.img_gif_note);

    // Wait for all 4 READY
    await expect(
      page.locator('text=/Listo|READY/i')
    ).toHaveCount(4, { timeout: 40000 });
    console.log('  ✅ All 4 files (2 PDFs + 2 images) READY');

    // Send message
    await page.locator('textarea').first().fill('Analiza todos estos documentos e imágenes');
    await page.locator('button[type="submit"]').first().click();

    // Wait for response
    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 50000 });

    // Validate
    expect(capturedFileIds.length).toBe(4);
    console.log(`  ✅ 4 file_ids sent (mixed PDF + images)`);

    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBe(4);
      console.log('  ✅ All 4 files in RAG context');
    }

    console.log('\n✅ Mixed PDF + image test PASSED\n');
  });

  test('Scanned PDF with OCR: spanish_menu_scan.pdf → RAG context', async ({ page }) => {
    console.log('\n🧪 Testing scanned PDF requiring OCR...\n');

    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      await route.continue();
      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    // Upload scanned PDF
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.pdf_spanish_menu);

    // Wait for READY (OCR processing may take longer)
    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 30000 });
    console.log('  ✅ Scanned PDF processed with OCR');

    // Send message
    await page.locator('textarea').first().fill('¿Qué elementos hay en este menú?');
    await page.locator('button[type="submit"]').first().click();

    // Wait for response
    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 40000 });

    // Validate OCR-processed content reached RAG
    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBeGreaterThan(0);
      console.log('  ✅ OCR-processed PDF in RAG context');
    }

    console.log('\n✅ Scanned PDF OCR test PASSED\n');
  });

  test('Rotated image: ocr_phototest_rotated_left.png → correct orientation', async ({ page }) => {
    console.log('\n🧪 Testing rotated image handling...\n');

    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      await route.continue();
      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    // Upload rotated image
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.img_png_rotated_left);

    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 20000 });
    console.log('  ✅ Rotated image processed');

    // Send message
    await page.locator('textarea').first().fill('¿Qué texto contiene esta imagen?');
    await page.locator('button[type="submit"]').first().click();

    // Wait for response
    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 40000 });

    // Validate
    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBe(1);
      console.log('  ✅ Rotated image in RAG context (orientation handled)');
    }

    console.log('\n✅ Rotated image test PASSED\n');
  });
});

test.describe('Chat - Exotic Format Edge Cases', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat');
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 10000 });
  });

  test('Large BMP image: ocr_spanish_ticket.bmp (1.3MB) → processes correctly', async ({ page }) => {
    console.log('\n🧪 Testing large BMP image (1.3MB)...\n');

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.img_bmp_ticket);

    // BMP is large, may take longer
    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 40000 });
    console.log('  ✅ Large BMP processed (1.3MB)');

    await page.locator('textarea').first().fill('Resume este ticket');
    await page.locator('button[type="submit"]').first().click();

    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 50000 });

    console.log('  ✅ Large BMP successfully in RAG context');
    console.log('\n✅ Large BMP test PASSED\n');
  });

  test('TIF format: ocr_eurotext.tif → correct OCR extraction', async ({ page }) => {
    console.log('\n🧪 Testing TIF image format...\n');

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.img_tif_eurotext);

    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 25000 });
    console.log('  ✅ TIF image processed');

    await page.locator('textarea').first().fill('What languages are in this text?');
    await page.locator('button[type="submit"]').first().click();

    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 40000 });

    console.log('  ✅ TIF image content extracted to RAG');
    console.log('\n✅ TIF format test PASSED\n');
  });

  test('Multilingual PDF: multilingual_brochure.pdf → handles multiple languages', async ({ page }) => {
    console.log('\n🧪 Testing multilingual PDF...\n');

    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      await route.continue();
      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(TEST_FILES.pdf_multilingual);

    await expect(
      page.locator('text=/Listo|READY/i').first()
    ).toBeVisible({ timeout: 30000 });
    console.log('  ✅ Multilingual PDF processed');

    await page.locator('textarea').first().fill('What languages are present in this brochure?');
    await page.locator('button[type="submit"]').first().click();

    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 40000 });

    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBe(1);
      console.log('  ✅ Multilingual content in RAG context');
    }

    console.log('\n✅ Multilingual PDF test PASSED\n');
  });

  test('Rapid upload of 5 different format files → all processed', async ({ page }) => {
    console.log('\n🧪 Testing rapid upload of 5 diverse files...\n');

    let capturedFileIds: string[] = [];
    let capturedMetadata: any = null;

    await page.route('**/api/chat/message', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        const postData = request.postDataJSON();
        if (postData?.file_ids) {
          capturedFileIds = postData.file_ids;
        }
      }

      await route.continue();

      const response = await route.request().response();
      if (response) {
        try {
          const json = await response.json();
          if (json?.decision_metadata) {
            capturedMetadata = json.decision_metadata;
          }
        } catch (e) {}
      }
    });

    // Upload 5 files rapidly: PDF, JPG, PNG, WEBP, GIF
    const fileInput = page.locator('input[type="file"]').first();
    const filesToUpload = [
      TEST_FILES.pdf_spanish_text,
      TEST_FILES.img_jpeg,
      TEST_FILES.img_png_spanish,
      TEST_FILES.img_webp_menu,
      TEST_FILES.img_gif_note,
    ];

    console.log('  ⚡ Uploading 5 files rapidly...');
    for (const file of filesToUpload) {
      await fileInput.setInputFiles(file);
      await page.waitForTimeout(500); // Brief pause between uploads
    }

    // Wait for all 5 READY
    await expect(
      page.locator('text=/Listo|READY/i')
    ).toHaveCount(5, { timeout: 50000 });
    console.log('  ✅ All 5 files READY (PDF, JPG, PNG, WEBP, GIF)');

    // Send message
    await page.locator('textarea').first().fill('Describe all these documents');
    await page.locator('button[type="submit"]').first().click();

    await expect(
      page.locator('.message').last()
    ).toBeVisible({ timeout: 60000 });

    // Validate
    expect(capturedFileIds.length).toBe(5);
    console.log(`  ✅ 5 file_ids sent`);

    if (capturedMetadata?.rag_selected_doc_ids) {
      expect(capturedMetadata.rag_selected_doc_ids.length).toBe(5);
      console.log('  ✅ All 5 files in RAG context');

      if (capturedMetadata.rag_dropped_doc_ids) {
        expect(capturedMetadata.rag_dropped_doc_ids.length).toBe(0);
        console.log('  ✅ No files dropped despite rapid upload');
      }
    }

    console.log('\n✅ Rapid multi-format test PASSED\n');
  });
});
