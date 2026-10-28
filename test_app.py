import os
import sys
import unittest
import io

# Ensure UTF-8 output encoding
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import werkzeug
if not hasattr(werkzeug, '__version__'):
    import importlib.metadata
    try:
        werkzeug.__version__ = importlib.metadata.version('werkzeug')
    except Exception:
        werkzeug.__version__ = '3.1.3'

import backend
import exporter
from app import app


class TestSummAIApp(unittest.TestCase):

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_exporter_pdf_docx(self):
        print("\n--- Testing PDF & DOCX Exporter ---")
        pdf_bytes = exporter.generate_pdf_bytes(
            summary="This is a test summary.",
            original_text="This is original text.",
            language_name="Kannada",
            keywords=["test", "summary"],
            explanation="Test explanation."
        )
        self.assertTrue(len(pdf_bytes) > 0)
        print(f"✓ PDF export generated successfully ({len(pdf_bytes)} bytes)")

        docx_bytes = exporter.generate_docx_bytes(
            summary="This is a test summary.",
            original_text="This is original text.",
            language_name="Kannada",
            keywords=["test", "summary"],
            explanation="Test explanation."
        )
        self.assertTrue(len(docx_bytes) > 0)
        print(f"✓ DOCX export generated successfully ({len(docx_bytes)} bytes)")

    def test_backend_summarize_and_translate(self):
        print("\n--- Testing Backend Summarize & Translation (Kannada) ---")
        sample_text = (
            "Artificial intelligence is transforming modern technology. "
            "It empowers machine learning algorithms to process complex data, "
            "enabling automated decision making across healthcare, finance, and education."
        )
        summary, original, explanation, keywords = backend.funforfrontend(
            sample_text,
            language='kn',
            explain=True,
            summary_mode='balanced'
        )
        print(f"Summary Output (Kannada): {summary[:100]}...")
        print(f"Keywords: {keywords}")
        self.assertTrue(len(summary) > 0)
        self.assertTrue(len(keywords) > 0)
        print("✓ Backend summarization & translation passed successfully.")

    def test_api_summarize_endpoint(self):
        print("\n--- Testing API /api/summarize Endpoint ---")
        response = self.app.post('/api/summarize', data={
            'text': 'Climate change affects weather patterns globally. It leads to rising sea levels and extreme temperatures.',
            'language': 'hi',
            'summary_mode': 'balanced',
            'explain': 'true'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['language'], 'hi')
        self.assertTrue(len(data['summary']) > 0)
        print(f"✓ API /api/summarize passed. Output: {data['summary'][:80]}...")

    def test_api_download_endpoints(self):
        print("\n--- Testing API Download PDF & DOCX Endpoints ---")
        payload = {
            'summary': 'Test summary',
            'original_text': 'Test original text',
            'language_name': 'Hindi',
            'keywords': ['test', 'hindi'],
            'explanation': 'Test explanation'
        }
        res_pdf = self.app.post('/api/download/pdf', json=payload)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(len(res_pdf.data) > 0)
        print("✓ Dedicated PDF download API passed.")

        res_docx = self.app.post('/api/download/docx', json=payload)
        self.assertEqual(res_docx.status_code, 200)
        self.assertTrue(len(res_docx.data) > 0)
        print("✓ Dedicated DOCX download API passed.")

if __name__ == '__main__':
    unittest.main()
