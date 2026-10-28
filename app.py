import os
import sys
import io
import json
import logging
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import backend
import exporter

# Ensure UTF-8 console output for Windows terminal safety
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

logging.basicConfig(level=logging.INFO)

LANGUAGE_NAMES = {
    'en': 'English',
    'kn': 'Kannada (ಕನ್ನಡ)',
    'hi': 'Hindi (हिंदी)',
    'bn': 'Bengali (বাংলা)',
    'ta': 'Tamil (தமிழ்)',
    'te': 'Telugu (తెలుగు)',
    'ml': 'Malayalam (മലയാളം)',
    'mr': 'Marathi (मराठी)',
    'gu': 'Gujarati (ગુજરાતી)',
    'pa': 'Punjabi (ਪੰਜਾਬੀ)',
    'ur': 'Urdu (اردو)',
    'es': 'Spanish (Español)',
    'fr': 'French (Français)',
    'de': 'German (Deutsch)',
}

@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == 'admin' and password == 'password':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            error = 'Invalid Credentials. Please try again.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('home'))

@app.route('/index')
def index():
    # Direct access allowed for convenience
    return render_template('index.html', languages=LANGUAGE_NAMES)

@app.route('/analyze', methods=['GET', 'POST'])
def analyze():
    if request.method == 'POST':
        rawtext = request.form.get('rawtext', '').strip()
        language = request.form.get('language', 'kn')
        summary_mode = request.form.get('summary_mode', 'detailed')
        uploaded_files = request.files.getlist('pdf_file')
        
        extracted_docs = []
        if uploaded_files:
            valid_files = [f for f in uploaded_files if f and f.filename.strip() != '']
            for f in valid_files:
                parsed_list = backend._extract_texts_from_files([f])
                t = parsed_list[0] if parsed_list else ""
                if t.strip():
                    extracted_docs.append((f.filename, t))

        if rawtext:
            extracted_docs.append(("Raw Text Input", rawtext))

        if not extracted_docs:
            return render_template('summary.html', error="Please enter valid text or upload document(s).")

        lang_name = LANGUAGE_NAMES.get(language, language)
        doc_results = []

        for doc_name, doc_text in extracted_docs:
            try:
                summary, original_text, explanation, keywords = backend.funforfrontend(
                    doc_text,
                    language=language,
                    explain=True,
                    summary_mode=summary_mode
                )
                doc_results.append({
                    'doc_name': doc_name,
                    'original_text': original_text,
                    'summary': summary,
                    'explanation': explanation,
                    'keywords': keywords
                })
            except Exception as e:
                logging.error("Error processing document %s: %s", doc_name, e)
                doc_results.append({
                    'doc_name': doc_name,
                    'original_text': doc_text,
                    'summary': f"Error summarizing {doc_name}: {str(e)}",
                    'explanation': "",
                    'keywords': []
                })

        first_res = doc_results[0] if doc_results else {}

        return render_template(
            'summary.html',
            doc_results=doc_results,
            summary=first_res.get('summary', ''),
            original_text=first_res.get('original_text', ''),
            language=language,
            language_name=lang_name,
            keywords=first_res.get('keywords', []),
            explanation=first_res.get('explanation', ''),
            summary_mode=summary_mode
        )

    return redirect(url_for('index'))

@app.route('/api/summarize', methods=['POST'])
def handle_summarize():
    try:
        language = request.form.get('language', 'kn')
        summary_mode = request.form.get('summary_mode', 'balanced')
        explain_flag = request.form.get('explain', 'true').lower() in ('true', '1', 'yes')
        raw_text = request.form.get('text', '').strip()

        uploaded_files = request.files.getlist('files') or request.files.getlist('pdf_file')
        
        extracted_docs = []
        if uploaded_files:
            valid_files = [f for f in uploaded_files if f and f.filename.strip() != '']
            for f in valid_files:
                parsed_list = backend._extract_texts_from_files([f])
                t = parsed_list[0] if parsed_list else ""
                if t.strip():
                    extracted_docs.append((f.filename, t))

        if raw_text:
            extracted_docs.append(("Raw Text Input", raw_text))

        if not extracted_docs:
            return jsonify({
                'status': 'error',
                'message': 'No text input or files provided.'
            }), 400

        lang_display_name = LANGUAGE_NAMES.get(language, language)
        doc_results = []

        for doc_name, doc_text in extracted_docs:
            summary, original_text, explanation, keywords = backend.funforfrontend(
                doc_text,
                language=language,
                explain=explain_flag,
                summary_mode=summary_mode
            )
            doc_results.append({
                'doc_name': doc_name,
                'summary': summary or "Unable to generate summary.",
                'original_text': original_text,
                'explanation': explanation or "",
                'keywords': keywords or []
            })

        first_res = doc_results[0]

        return jsonify({
            'status': 'success',
            'doc_results': doc_results,
            'summary': first_res['summary'],
            'original_text': first_res['original_text'],
            'explanation': first_res['explanation'],
            'keywords': first_res['keywords'],
            'language': language,
            'language_name': lang_display_name
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/download/pdf', methods=['POST'])
def download_pdf():
    try:
        data = request.get_json(force=True) or {}
        pdf_bytes = exporter.generate_pdf_bytes(
            summary=data.get('summary', ''),
            original_text=data.get('original_text', ''),
            language_name=data.get('language_name', 'Output'),
            keywords=data.get('keywords', []),
            explanation=data.get('explanation', '')
        )
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name='summary.pdf'
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/download/docx', methods=['POST'])
def download_docx():
    try:
        data = request.get_json(force=True) or {}
        docx_bytes = exporter.generate_docx_bytes(
            summary=data.get('summary', ''),
            original_text=data.get('original_text', ''),
            language_name=data.get('language_name', 'Output'),
            keywords=data.get('keywords', []),
            explanation=data.get('explanation', '')
        )
        return send_file(
            io.BytesIO(docx_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name='summary.docx'
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    import webbrowser
    from threading import Timer
    print("Starting Text Summarization App on http://127.0.0.1:5000/index")
    Timer(1.2, lambda: webbrowser.open('http://127.0.0.1:5000/index')).start()
    app.run(host='127.0.0.1', port=5000, debug=False)

