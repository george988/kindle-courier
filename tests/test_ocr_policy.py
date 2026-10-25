"""OCR policy regression tests. Real Pandoc builds; EPUBCheck is mocked here.
Run with: python -m unittest discover -s tests -p test_ocr_policy.py -v
Live release verification must additionally use the pinned real EPUBCheck.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import article2epub as A
from PIL import Image, ImageDraw


@unittest.skipUnless(shutil.which('pandoc'), 'Pandoc required')
class OcrPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        image = Image.new('RGB', (800, 600), 'white')
        ImageDraw.Draw(image).text((60, 60), 'Original diagram: A -> B', fill='black')
        image.save(self.root / 'diagram.png')
        self.html = '<html><body><h2>Source section</h2><p>' + ('Source prose is preserved exactly. ' * 12) + '</p><figure><img src="diagram.png"/><figcaption>Original source caption.</figcaption></figure></body></html>'
        self.job = dict(html=str(self.root / 'source.html'), trusted_html=True,
                        title='OCR policy fixture', author='Fixture Author', date='2026-10-25',
                        source_url='https://example.com/article', lang='en', out=str(self.root / 'book.epub'),
                        no_cover=True, expect_images=1, images_reviewed=True)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(A, 'BASE', str(self.root)))
        self.stack.enter_context(patch.object(A.C, 'BASE', str(self.root)))
        self.stack.enter_context(patch.object(A.C, 'pandoc_bin', return_value=shutil.which('pandoc')))
        self.stack.enter_context(patch.object(A.C, 'run_epubcheck', return_value=({'fatal': 0, 'error': 0, 'warning': 0}, [])))
        self.ocr = self.stack.enter_context(patch.object(A.C, 'ocr_image', return_value=('text', 'Supplementary machine text with a deliberate misread.')))
        self.available = self.stack.enter_context(patch.object(A.C, 'ocr_available', return_value=True))

    def build(self, changes=None, cli=()):
        job = dict(self.job, **(changes or {}))
        (self.root / 'source.html').write_text(self.html)
        # Simulate the two-pass inspection workflow; live tests must actually inspect the pixels.
        if job.get('images_reviewed') is True and 'image_review_sha256' not in job:
            inspection = dict(job, images_reviewed=False, out=str(self.root / 'inspect.epub'), force=True)
            (self.root / 'inspect.json').write_text(json.dumps(inspection))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                A.main(['--job', str(self.root / 'inspect.json'), *cli])
            mf = self.root / 'inspect.needs-review.epub.manifest.json'
            if not mf.exists(): mf = self.root / 'inspect.epub.manifest.json'
            if mf.exists():
                job['image_review_sha256'] = [i['sha256'] for i in json.loads(mf.read_text())['images']['items'] if i['status'] == 'embedded']
        (self.root / 'job.json').write_text(json.dumps(job))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = A.main(['--job', str(self.root / 'job.json'), *cli])
        output = Path(job['out'])
        if not output.exists(): output = Path(A.review_name(str(output)))
        manifest = json.loads(Path(str(output) + '.manifest.json').read_text()) if output.exists() else None
        return code, output, manifest

    def test_default_preserves_image_caption_without_ocr_or_hold(self):
        code, book, m = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(m['status'], 'complete')
        self.assertEqual(m['images']['embedded'], 1)
        self.assertTrue(m['images']['readability_reviewed'])
        text = A.C.epub_text(str(book))
        self.assertIn('Original source caption.', text)
        self.assertNotIn('Supplementary machine', text)
        with zipfile.ZipFile(book) as z:
            images = [n for n in z.namelist() if n.endswith(('.png', '.jpg', '.jpeg'))]
            self.assertEqual(len(images), 1)
            Image.open(io.BytesIO(z.read(images[0]))).load()
        self.ocr.assert_not_called()
        self.available.assert_not_called()
        self.assertFalse(A.C.check_binding(str(book), json.loads(Path(str(book)+'.job.json').read_text()), str(book)+'.manifest.json'))

    def test_default_works_without_tesseract(self):
        self.available.return_value = False
        self.assertEqual(self.build()[0], 0)
        self.available.assert_not_called()

    def test_explicit_off_in_job_is_honored(self):
        self.assertEqual(self.build({'ocr': 'off'})[0], 0)
        self.ocr.assert_not_called()

    def test_opt_in_ocr_stays_labelled_and_held(self):
        code, book, m = self.build({'ocr': 'auto'})
        self.assertEqual(code, 5)
        self.assertIn('machine-transcribed (OCR) text was added; it may contain errors', m['review_reasons'])
        self.assertIn('Supplementary machine', A.C.epub_text(str(book)))
        self.assertIn('OCR; may contain errors', A.C.epub_text(str(book)))

    def test_requested_ocr_unavailable_stays_held(self):
        self.available.return_value = False
        code, _, m = self.build({'ocr': 'auto'})
        self.assertEqual(code, 5)
        self.assertEqual(m['ocr'], 'unavailable')

    def test_requested_ocr_failure_stays_held(self):
        self.ocr.return_value = ('error', 'test failure')
        self.assertEqual(self.build({'ocr': 'auto'})[0], 5)

    def test_unreviewed_image_stays_held_without_prompting_for_ocr(self):
        self.job.pop('images_reviewed')
        code, _, m = self.build()
        self.assertEqual(code, 5)
        self.assertTrue(any('readability' in x for x in m['review_reasons']))
        self.assertFalse(any('OCR' in x for x in m['review_reasons']))

    def test_missing_and_corrupt_images_cannot_be_approved_by_flag(self):
        for contents in (None, b'not an image'):
            with self.subTest(contents=contents):
                p = self.root / 'diagram.png'
                if contents is None: p.unlink(missing_ok=True)
                else: p.write_bytes(contents)
                code, _, m = self.build({'force': True})
                self.assertEqual(code, 5)
                self.assertEqual(m['status'], 'incomplete')
                self.assertTrue(m['failures'])

    def test_omitted_video_and_missing_posts_still_hold(self):
        self.html = self.html.replace('</body>', '<video src="https://example.com/video.mp4"></video></body>')
        code, _, m = self.build({'expect_posts': 2})
        self.assertEqual(code, 5)
        self.assertTrue(m['omissions'])
        self.assertTrue(m['failures'])

    def test_cli_ocr_choice_overrides_job(self):
        self.assertEqual(self.build({'ocr': 'auto'}, ('--ocr', 'off'))[0], 0)
        self.ocr.assert_not_called()

    def test_bad_job_options_fail_closed(self):
        for change in ({'ocr': 'garbage'}, {'images_reviewed': 'true'}):
            with self.subTest(change=change): self.assertEqual(self.build(change)[0], 2)

    def test_stale_or_missing_image_hashes_keep_hold(self):
        for hashes in ([], ['0' * 64]):
            with self.subTest(hashes=hashes):
                code, _, m = self.build({'image_review_sha256': hashes, 'force': True})
                self.assertEqual(code, 5)
                self.assertFalse(m['images']['readability_reviewed'])

    def test_blank_image_cannot_be_approved(self):
        Image.new('RGB', (800, 600), 'white').save(self.root / 'diagram.png')
        code, _, m = self.build()
        self.assertEqual(code, 5)
        self.assertTrue(any('blank' in x for x in m['failures']))

    def test_tall_diagram_keeps_native_resolution(self):
        im = Image.new('RGB', (1800, 4000), 'white')
        ImageDraw.Draw(im).line((100, 100, 1500, 3500), fill='black', width=6)
        im.save(self.root / 'diagram.png')
        code, _, m = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(m['images']['items'][0]['native_size'], [1800, 4000])
        self.assertEqual(m['images']['items'][0]['embedded_size'], [1800, 4000])

    def test_text_only_article_needs_no_image_attestation(self):
        self.html = self.html.split('<figure>')[0] + '</body></html>'
        self.job.pop('images_reviewed')
        self.assertEqual(self.build({'expect_images': 0})[0], 0)

if __name__ == '__main__': unittest.main()
