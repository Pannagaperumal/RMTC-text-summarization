import os
import re
import sys
import io

# Ensure UTF-8 output encoding for Windows terminals handling non-ASCII translations
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


# Optional heavy ML libs: import where available, otherwise set flags for fallback behavior
try:
    import torch
    _TORCH_AVAILABLE = True
except Exception:
    torch = None
    _TORCH_AVAILABLE = False

_HF_AVAILABLE = True
try:
    from transformers import BartForConditionalGeneration, BartTokenizer
    from transformers import MarianMTModel, MarianTokenizer
    from transformers import MBartForConditionalGeneration, MBart50TokenizerFast
except Exception:
    BartForConditionalGeneration = None
    BartTokenizer = None
    MarianMTModel = None
    MarianTokenizer = None
    MBartForConditionalGeneration = None
    MBart50TokenizerFast = None
    _HF_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except Exception:
    SentenceTransformer = None
    _SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:
    cosine_similarity = None

try:
    from nltk.tokenize import sent_tokenize
except Exception:
    sent_tokenize = None

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx
    _DOCX_AVAILABLE = True
except Exception:
    docx = None
    _DOCX_AVAILABLE = False


# TensorFlow environment tweak preserved if present
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
# Optional lightweight translator fallback: defer imports to runtime to allow
# installing packages later and to avoid import-time failures.
_GT_AVAILABLE = False
try:
    from langdetect import detect
    _LANGDETECT_AVAILABLE = True
except Exception:
    _LANGDETECT_AVAILABLE = False
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Environment tweaks
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

# Device (only if torch available)
if _TORCH_AVAILABLE:
    DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
else:
    DEVICE = None

# Caches
_EMBED_MODEL = None
_ABSTR_MODEL = None
_ABSTR_TOKENIZER = None
_MT_MODELS = {}
_MBART_MODEL = None
_MBART_TOKENIZER = None

# Map short codes to mBART language tags (mbart-large-50)
_MBART_LANG_MAP = {
    'en': 'en_XX',
    'hi': 'hi_IN',
    'bn': 'bn_IN',
    'gu': 'gu_IN',
    'kn': 'kn_IN',
    'ml': 'ml_IN',
    'mr': 'mr_IN',
    'or': 'or_IN',
    'pa': 'pa_IN',
    'ta': 'ta_IN',
    'te': 'te_IN',
    'ur': 'ur_IN',
    'ne': 'ne_NP',
    'sd': 'sd_IN',
    'sa': 'sa_IN',
}

# Default offline mode set to False to enable BART and multi-language translation.
# If heavy models are missing or network fails, it falls back cleanly to extractive + googletrans.
OFFLINE_ONLY = False



def _load_embedding_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        # multilingual miniLM - compact and fast (only if sentence-transformers available)
        if _SENTENCE_TRANSFORMERS_AVAILABLE:
            _EMBED_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        else:
            _EMBED_MODEL = None


def _load_abstractive_model():
    global _ABSTR_MODEL, _ABSTR_TOKENIZER
    # Load abstractive model only when transformers and torch are available
    if not _HF_AVAILABLE or not _TORCH_AVAILABLE:
        _ABSTR_MODEL = None
        _ABSTR_TOKENIZER = None
        return
    if _ABSTR_MODEL is None or _ABSTR_TOKENIZER is None:
        _ABSTR_TOKENIZER = BartTokenizer.from_pretrained('facebook/bart-large-cnn')
        _ABSTR_MODEL = BartForConditionalGeneration.from_pretrained('facebook/bart-large-cnn')
        if DEVICE is not None:
            _ABSTR_MODEL.to(DEVICE)


def _get_marian_model(target_lang):
    if target_lang in _MT_MODELS:
        return _MT_MODELS[target_lang]

    lang_map = {
        'hi': 'Helsinki-NLP/opus-mt-en-hi',
        'bn': 'Helsinki-NLP/opus-mt-en-bn',
        'gu': 'Helsinki-NLP/opus-mt-en-gu',
        'kn': 'Helsinki-NLP/opus-mt-en-kn',
        'ml': 'Helsinki-NLP/opus-mt-en-ml',
        'mr': 'Helsinki-NLP/opus-mt-en-mr',
        'or': 'Helsinki-NLP/opus-mt-en-or',
        'pa': 'Helsinki-NLP/opus-mt-en-pa',
        'ta': 'Helsinki-NLP/opus-mt-en-ta',
        'te': 'Helsinki-NLP/opus-mt-en-te',
        'ur': 'Helsinki-NLP/opus-mt-en-ur',
        'ne': 'Helsinki-NLP/opus-mt-en-ne',
    }
    model_name = lang_map.get(target_lang)
    if not model_name:
        _MT_MODELS[target_lang] = (None, None)
        return None, None
    if MarianTokenizer is None or MarianMTModel is None or not _HF_AVAILABLE:
        _MT_MODELS[target_lang] = (None, None)
        return None, None
    try:
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        if DEVICE is not None:
            model.to(DEVICE)
        _MT_MODELS[target_lang] = (model, tokenizer)
        return model, tokenizer
    except Exception as e:
        print(f"Translation model load error for {target_lang}: {e}")
        _MT_MODELS[target_lang] = (None, None)
        return None, None


def _load_mbart():
    global _MBART_MODEL, _MBART_TOKENIZER
    if _MBART_MODEL is None or _MBART_TOKENIZER is None:
        if MBart50TokenizerFast is None or MBartForConditionalGeneration is None or not _HF_AVAILABLE:
            _MBART_MODEL = None
            _MBART_TOKENIZER = None
            return
        try:
            _MBART_TOKENIZER = MBart50TokenizerFast.from_pretrained('facebook/mbart-large-50-many-to-many-mmt')
            _MBART_MODEL = MBartForConditionalGeneration.from_pretrained('facebook/mbart-large-50-many-to-many-mmt')
            if DEVICE is not None:
                _MBART_MODEL.to(DEVICE)
        except Exception as e:
            print(f"mBART load error: {e}")
            _MBART_MODEL = None
            _MBART_TOKENIZER = None


def _translate_with_mbart(text, target_lang):
    _load_mbart()
    if _MBART_MODEL is None or _MBART_TOKENIZER is None:
        return None
    tag = _MBART_LANG_MAP.get(target_lang)
    if not tag:
        return None
    try:
        tokenizer = _MBART_TOKENIZER
        model = _MBART_MODEL
        tokenizer.src_lang = 'en_XX'
        encoded = tokenizer(text, return_tensors='pt', truncation=True, padding=True)
        for k, v in encoded.items():
            encoded[k] = v.to(DEVICE)
        forced_token_id = tokenizer.lang_code_to_id[tag]
        generated = model.generate(**encoded, forced_bos_token_id=forced_token_id, max_length=512)
        out = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        return out
    except Exception as e:
        print(f"mBART translation error for {target_lang}: {e}")
        return None

def _translate_with_mbart_pair(text, src_lang, tgt_lang):
    _load_mbart()
    if _MBART_MODEL is None or _MBART_TOKENIZER is None:
        return None
    src_tag = _MBART_LANG_MAP.get(src_lang)
    tgt_tag = _MBART_LANG_MAP.get(tgt_lang)
    if not src_tag or not tgt_tag:
        return None
    try:
        tokenizer = _MBART_TOKENIZER
        model = _MBART_MODEL
        tokenizer.src_lang = src_tag
        encoded = tokenizer(text, return_tensors='pt', truncation=True, padding=True)
        for k, v in encoded.items():
            encoded[k] = v.to(DEVICE)
        forced_token_id = tokenizer.lang_code_to_id[tgt_tag]
        generated = model.generate(**encoded, forced_bos_token_id=forced_token_id, max_length=512)
        out = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        return out
    except Exception as e:
        print(f"mBART pairwise translation error {src_lang}->{tgt_lang}: {e}")
        return None


def _translate_text(text, src_lang, tgt_lang):
    if src_lang == 'en':
        mt_model, mt_tokenizer = _get_marian_model(tgt_lang)
        if mt_model and mt_tokenizer:
            try:
                trans_inputs = mt_tokenizer(text, return_tensors='pt', truncation=True, padding=True)
                for k, v in trans_inputs.items():
                    trans_inputs[k] = v.to(DEVICE)
                with torch.no_grad():
                    translated_ids = mt_model.generate(**trans_inputs, max_length=512)
                return mt_tokenizer.decode(translated_ids[0], skip_special_tokens=True)
            except Exception as e:
                print(f"Marian en->{tgt_lang} failed: {e}")

    mb = _translate_with_mbart_pair(text, src_lang, tgt_lang)
    if mb:
        return mb

    gt = _translate_with_googletrans(text, tgt_lang)
    return gt


def _translate_with_googletrans(text, target_lang):
    try:
        from googletrans import Translator as _GoogleTranslator
    except Exception:
        return None
    try:
        translator = _GoogleTranslator()
        res = translator.translate(text, dest=target_lang)
        return res.text
    except Exception as e:
        print(f"googletrans fallback failed for {target_lang}: {e}")
        return None


def _extract_texts_from_files(file_list):
    texts = []
    for f in file_list:
        if not f:
            continue
        try:
            if isinstance(f, str):
                fn_lower = f.lower()
                if fn_lower.endswith('.pdf'):
                    reader = PyPDF2.PdfReader(f)
                    text = ''.join([p.extract_text() or '' for p in reader.pages])
                    texts.append(text)
                elif fn_lower.endswith('.docx'):
                    if _DOCX_AVAILABLE:
                        doc = docx.Document(f)
                        text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                        texts.append(text)
                    else:
                        texts.append('[DOCX uploaded — python-docx library not installed]')
                else:
                    if os.path.exists(f):
                        with open(f, 'r', encoding='utf-8', errors='ignore') as file_obj:
                            texts.append(file_obj.read())
                    else:
                        texts.append('')
            else:
                fn = getattr(f, 'filename', '') or 'uploaded_file'
                fn_lower = fn.lower()
                
                content = b""
                if hasattr(f, 'read'):
                    content = f.read()
                    if hasattr(f, 'seek'):
                        f.seek(0)
                
                if not content:
                    texts.append('')
                    continue

                bio = io.BytesIO(content)

                if fn_lower.endswith('.pdf'):
                    reader = PyPDF2.PdfReader(bio)
                    text = ''
                    for page in reader.pages:
                        text += page.extract_text() or ''
                    texts.append(text)
                elif fn_lower.endswith('.docx'):
                    if _DOCX_AVAILABLE:
                        doc = docx.Document(bio)
                        text = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
                        texts.append(text)
                    else:
                        texts.append('[DOCX uploaded — python-docx library not installed]')
                elif fn_lower.endswith(('.jpg', '.jpeg', '.png')):
                    if OCR_AVAILABLE:
                        image = Image.open(bio)
                        text = pytesseract.image_to_string(image)
                        texts.append(text)
                    else:
                        texts.append('[Image uploaded — OCR not available on server]')
                else:
                    text = content.decode('utf-8', errors='ignore') if isinstance(content, bytes) else str(content)
                    texts.append(text)
        except Exception as e:
            fn_display = getattr(f, 'filename', '') or (f if isinstance(f, str) else 'file')
            texts.append(f'[Error extracting {fn_display}: {e}]')

    return texts




def _split_sentences(text):
    try:
        return sent_tokenize(text)
    except Exception:
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _compute_embeddings(sentences):
    _load_embedding_model()
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL.encode(sentences, convert_to_numpy=True)
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(max_features=512)
        X = vec.fit_transform(sentences).toarray()
        return X
    except Exception:
        import numpy as _np
        rng = _np.random.RandomState(0)
        return rng.rand(len(sentences), 256)


def _hybrid_selector(sentences, embeddings, top_k=6, diversity_lambda=0.6):
    if len(sentences) <= top_k:
        return list(range(len(sentences)))

    centroid = embeddings.mean(axis=0, keepdims=True)
    relevance = cosine_similarity(embeddings, centroid).squeeze()

    selected = []
    remaining = set(range(len(sentences)))

    for i in range(top_k):
        best_idx = None
        best_score = -1e9
        for idx in remaining:
            if not selected:
                div_pen = 0.0
            else:
                sims = cosine_similarity(embeddings[idx:idx+1], embeddings[selected]).max()
                div_pen = sims
            score = relevance[idx] - diversity_lambda * div_pen
            import random
            if random.random() < 0.08:
                score += random.uniform(-0.05, 0.05)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is None:
            break
        selected.append(best_idx)
        remaining.remove(best_idx)

    return sorted(selected)


def _simple_extractive_summary(text, top_k=5):
    sents = _split_sentences(text)
    if not sents:
        return ""
    import collections
    words = re.findall(r"\w+", text.lower())
    freq = collections.Counter(words)
    scores = []
    for s in sents:
        w = re.findall(r"\w+", s.lower())
        if not w:
            scores.append(0)
            continue
        score = sum(freq.get(t, 0) for t in w) / len(w)
        score *= min(1.0, len(w) / 30)
        scores.append(score)
    idxs = sorted(range(len(sents)), key=lambda i: scores[i], reverse=True)[:top_k]
    idxs = sorted(idxs)
    chosen = [sents[i] for i in idxs]
    return ' '.join(chosen)


def _extract_keywords(text, top_n=8):
    import collections
    stopwords = set([
        'the','and','is','in','to','of','a','for','on','with','that','this','it','as','are','be','by','an','or','from','at','was','which','have','has'
    ])
    words = [w.lower() for w in re.findall(r"\b[a-zA-Z]{3,}\b", text)]
    filtered = [w for w in words if w not in stopwords]
    if not filtered:
        return []
    freq = collections.Counter(filtered)
    most = [w for w, _ in freq.most_common(top_n)]
    return most


def _build_explanation(original_text, extractive_sentences, summary, mode='balanced'):
    mode = (mode or 'balanced').lower()
    bullets = []
    for s in extractive_sentences:
        t = s.strip()
        if len(t) > 240:
            t = t[:237].rsplit(' ', 1)[0] + '...'
        bullets.append(t)

    if mode in ('simple','easy','simple (easy to understand)'):
        expl = 'This short explanation highlights the main points: ' + '; '.join(bullets[:3])
        expl += '\n\nSummary (short): ' + (summary if len(summary) < 400 else summary[:397] + '...')
        return expl

    if mode in ('detailed','technical','technical (in-depth)'):
        expl_lines = ['Detailed explanation of the summary:']
        for i, b in enumerate(bullets, 1):
            expl_lines.append(f"{i}. {b}")
            expl_lines.append(f"   Reason: This sentence was selected because it contains key concepts from the source.")
        expl_lines.append('\nFull summary:')
        expl_lines.append(summary)
        return '\n'.join(expl_lines)

    expl = 'Key points:\n'
    for i, b in enumerate(bullets[:5], 1):
        expl += f"{i}. {b}\n"
    expl += '\nConcise summary:\n' + summary
    return expl


def funforfrontend(input_texts, language='en', explain=False, summary_mode='balanced'):
    if isinstance(input_texts, (list, tuple)):
        docs = [t for t in input_texts if t and isinstance(t, str)]
        original_text = '\n\n===DOCUMENT_SEPARATOR===\n\n'.join(docs)
    else:
        original_text = input_texts

    source_lang = 'en'
    try:
        if _LANGDETECT_AVAILABLE:
            detected = detect(original_text)
            if detected:
                source_lang = detected
    except Exception:
        source_lang = 'en'

    processing_text = original_text

    # If offline-only mode is enabled, use a lightweight extractive summarizer with translation
    if OFFLINE_ONLY:
        sentences = _split_sentences(processing_text)
        if not sentences:
            return "", original_text, None, []

        mode = (summary_mode or 'balanced').lower()
        if mode in ('easy', 'simple', 'easy_understand'):
            top_k = max(2, min(6, len(sentences) // 8))
        elif mode in ('detailed', 'long', 'verbose'):
            top_k = max(6, min(12, len(sentences) // 4))
        else:
            top_k = max(3, min(8, len(sentences) // 6))

        summary = _simple_extractive_summary(processing_text, top_k=top_k)
        keywords = _extract_keywords(processing_text, top_n=10)
        explanation_text = None
        if explain:
            extractive_sentences = _split_sentences(_simple_extractive_summary(processing_text, top_k=top_k))
            explanation_text = _build_explanation(original_text, extractive_sentences, summary, mode=summary_mode)

        if language and language != 'en':
            trans_sum = _translate_text(summary, source_lang, language)
            if trans_sum:
                summary = trans_sum
            if explanation_text:
                trans_expl = _translate_text(explanation_text, source_lang, language)
                if trans_expl:
                    explanation_text = trans_expl

        return summary, original_text, explanation_text, keywords

    translated_to_en = False
    if source_lang != 'en' and original_text.strip():
        try:
            trans = _translate_text(original_text, source_lang, 'en')
            if trans:
                processing_text = trans
                translated_to_en = True
        except Exception:
            processing_text = original_text

    sentences = _split_sentences(processing_text)
    if not sentences:
        return "", original_text, None, []

    embeddings = _compute_embeddings(sentences)

    mode = (summary_mode or 'balanced').lower()
    if mode in ('easy', 'simple', 'easy_understand'):
        top_k = max(2, min(6, len(sentences) // 8))
        gen_min_length = 20
        gen_max_length = 120
        gen_num_beams = 2
        gen_length_penalty = 2.0
    elif mode in ('detailed', 'long', 'verbose'):
        top_k = max(6, min(12, len(sentences) // 4))
        gen_min_length = 120
        gen_max_length = 400
        gen_num_beams = 6
        gen_length_penalty = 0.8
    else:
        top_k = max(3, min(8, len(sentences) // 6))
        gen_min_length = 60
        gen_max_length = 300
        gen_num_beams = 4
        gen_length_penalty = 1.0

    try:
        if language and language != 'en':
            top_k = min(len(sentences), max(top_k, int(top_k * 1.5) + 1))
            gen_max_length = int(gen_max_length * 1.5)
            gen_min_length = max(gen_min_length, int(gen_min_length * 1.2))
    except Exception:
        pass

    selected_indices = _hybrid_selector(sentences, embeddings, top_k=top_k)

    extractive_sentences = [sentences[i] for i in selected_indices]
    extractive_summary = ' '.join(extractive_sentences)

    try:
        _load_abstractive_model()
        if _ABSTR_MODEL is not None and _ABSTR_TOKENIZER is not None and _TORCH_AVAILABLE:
            inputs = _ABSTR_TOKENIZER([extractive_summary], max_length=1024, return_tensors='pt', truncation=True)
            input_ids = inputs['input_ids'].to(DEVICE) if DEVICE is not None else inputs['input_ids']
            with torch.no_grad():
                gen_ids = _ABSTR_MODEL.generate(
                    input_ids,
                    num_beams=gen_num_beams,
                    min_length=gen_min_length,
                    max_length=gen_max_length,
                    length_penalty=gen_length_penalty,
                    early_stopping=True
                )
            abstractive = _ABSTR_TOKENIZER.decode(gen_ids[0], skip_special_tokens=True, clean_up_tokenization_spaces=True)
            summary = abstractive
        else:
            summary = _simple_extractive_summary(extractive_summary, top_k=max(3, min(6, len(extractive_sentences))))
    except Exception as e:
        print(f"Abstractive rewriter failed: {e}")
        if not summary:
            summary = extractive_summary

    keywords = _extract_keywords(processing_text, top_n=10)
    explanation_text = None
    if explain:
        explanation_text = _build_explanation(original_text if not translated_to_en else processing_text, extractive_sentences, summary, mode=summary_mode)

    if language and language != 'en':
        src_for_summary = 'en' if translated_to_en else source_lang
        translated_summary = _translate_text(summary, src_for_summary, language)
        if translated_summary:
            summary = translated_summary
        else:
            summary = f"[Translation to {language} not available]\n" + summary

        if explanation_text:
            trans_expl = _translate_text(explanation_text, src_for_summary, language)
            if trans_expl:
                explanation_text = trans_expl
    else:
        if language == 'en' and source_lang != 'en' and translated_to_en:
            back_trans = _translate_text(summary, 'en', source_lang)
            if back_trans:
                summary = back_trans

    return summary, original_text, explanation_text, keywords



def funforfrontend_translated(input_texts, target_lang='en', explain=False, summary_mode='balanced'):
    """Compatibility wrapper: returns the same shape as funforfrontend but accepts
    the older parameter name `target_lang`. Keeps backward compatibility with
    callers that expect a translated summary helper.
    """
    return funforfrontend(input_texts, language=target_lang, explain=explain, summary_mode=summary_mode)
