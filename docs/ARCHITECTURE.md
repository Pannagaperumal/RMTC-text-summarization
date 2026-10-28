# Architecture

## System overview

```mermaid
flowchart TB
    subgraph Clients
        U["Browser<br/>index.html → summary.html"]
        API["API client<br/>(curl, scripts)"]
    end

    subgraph App["Flask app (app.py)"]
        R1["/index, /analyze"]
        R2["/api/summarize"]
        R3["/api/download/pdf<br/>/api/download/docx"]
        R4["/api/tts"]
        AUTH["login_required<br/>(when AUTH_ENABLED)"]
    end

    CFG["config.py<br/>.env → settings"]
    BE["backend.py<br/>extraction · summarization · translation"]
    EX["exporter.py<br/>PDF (ReportLab + HarfBuzz) · DOCX"]

    subgraph External["External / optional"]
        HF[("Hugging Face Hub<br/>model downloads, cached")]
        GT["Google Translate<br/>(deep-translator)"]
        GTTS["Google TTS<br/>(gTTS)"]
        FONTS[("System fonts<br/>Noto / Nirmala")]
    end

    U --> R1
    U --> R3
    U --> R4
    API --> R2
    API --> R3
    R1 & R2 & R3 & R4 -.-> AUTH
    R1 --> BE
    R2 --> BE
    R3 --> EX
    R4 --> GTTS
    BE -->|first use| HF
    BE -->|fallback| GT
    EX --> FONTS
    CFG -.-> App
    CFG -.-> BE
    CFG -.-> EX
```

| Module | Responsibility |
|---|---|
| `config.py` | Loads `.env` and exposes typed settings. Imported first by `app.py`. |
| `app.py` | Flask routes, optional authentication, upload handling, error responses. |
| `backend.py` | Text extraction, language detection, sentence selection, abstractive rewriting, translation. |
| `exporter.py` | PDF (ReportLab) and Word (python-docx) generation. |
| `templates/` | Server-rendered pages (Jinja2, Bootstrap 4). |

---

## Request lifecycle

How a form submission with two uploaded files becomes a results page:

```mermaid
sequenceDiagram
    actor User
    participant Page as index.html
    participant App as app.py /analyze
    participant BE as backend.py
    participant Res as summary.html
    participant EX as exporter.py

    User->>Page: paste text / choose files, language, style
    Page->>App: POST multipart form
    loop each uploaded file
        App->>BE: extract_text(file)
        alt readable
            BE-->>App: text
        else empty / scanned / unsupported
            BE-->>App: ExtractionError → added to errors
        end
    end
    loop each document (files, then pasted text)
        App->>BE: summarize(text, language, mode)
        BE-->>App: SummaryResult (summary, keywords, explanation, warnings)
    end
    App->>Res: render(doc_results, errors)
    Res-->>User: one card per document

    opt Export as PDF / Word
        User->>Res: click export
        Res->>EX: POST /api/download/pdf (JSON)
        EX-->>User: summary.pdf
    end
    opt Play
        Res->>App: POST /api/tts
        alt gTTS available
            App-->>Res: audio/mpeg
        else 501 / 502
            Res->>Res: browser speechSynthesis fallback
        end
    end
```

`/api/summarize` follows the same path but returns JSON (see [API.md](API.md)).

---

## Summarization pipeline (`backend.summarize`)

```mermaid
flowchart TD
    IN["Document text"] --> DET["Detect language<br/>langdetect, fixed seed"]
    DET --> ISEN{"source = en?"}
    ISEN -- yes --> SPLIT
    ISEN -- no --> T1["Translate to English<br/>(chunked)"]
    T1 -->|ok| SPLIT
    T1 -->|failed| W1["⚠ warning: summarize<br/>original text"] --> SPLIT

    SPLIT["Split sentences<br/>NLTK punkt / regex incl. । danda"] --> EMB{"Embeddings<br/>available?"}
    EMB -- "MiniLM (ml extra)" --> MMR
    EMB -- "TF-IDF (scikit-learn)" --> MMR
    EMB -- none --> FREQ["Word-frequency scoring"]
    MMR["MMR selection<br/>relevance − λ·redundancy"] --> EXT
    FREQ --> EXT["Extractive summary<br/>(selected sentences, original order)"]

    EXT --> BART{"BART available<br/>and input ≥ 40 tokens?"}
    BART -- yes --> REW["Abstractive rewrite<br/>lengths capped by input size"]
    BART -- no --> KEEP["Keep extractive text"]
    REW -->|error| KEEP
    REW --> KW
    KEEP --> KW["Keywords + explanation<br/>(relevance scores)"]

    KW --> ISTGT{"target = working<br/>language?"}
    ISTGT -- yes --> OUT
    ISTGT -- no --> T2["Translate summary, explanation, keywords"]
    T2 -->|ok| OUT
    T2 -->|failed| W2["⚠ warning: shown in English"] --> OUT
    OUT["SummaryResult"]
```

Step by step:

1. **Language detection.** `langdetect` runs with a fixed seed so results are deterministic.
   Short Latin-script text (< 200 characters) is assumed to be English, because langdetect is
   unreliable on short snippets. Low-confidence results (< 0.85) also default to English.
2. **Translate to English** if needed. The summarizer and keyword extraction assume English.
   If translation fails, the pipeline continues on the original text and adds a warning.
3. **Sentence split.** NLTK `punkt`, or a regex fallback that also splits on the Devanagari danda (।).
4. **Embedding.** `paraphrase-multilingual-MiniLM-L12-v2`, falling back to TF-IDF. Vectors are L2-normalised.
5. **Selection** (see [MMR](#sentence-selection-mmr) below). The number of sentences picked (`top_k`)
   depends on the mode and the document length, and is about 50% higher for non-English output.
6. **Abstractive rewrite.** `facebook/bart-large-cnn`. The mode's min/max lengths are upper
   bounds, capped by the input size (`_generation_lengths`) so BART is never forced to write
   more than it was given, which would make it hallucinate.
7. **Keywords.** Most frequent non-stopword words. **Explanation:** the selected sentences with
   their position and relevance score.
8. **Translate to the target language.** Keywords stay English, and are labelled as such, when
   their translation can't be aligned one-to-one.

The result is a `SummaryResult` with `summary`, `explanation`, `keywords`, `keywords_language`,
`source_language`, `method` (`hybrid` or `extractive`) and `warnings`.

### Summary modes

| Mode | Sentences selected | BART min / max tokens (upper bounds) | Beams | Length penalty |
|---|---|---|---|---|
| simple | 2–6 | 20 / 120 | 2 | 2.0 |
| balanced | 3–8 | 60 / 300 | 4 | 1.0 |
| detailed | 6–12 | 120 / 400 | 6 | 0.8 |

### Sentence selection (MMR)

Maximal Marginal Relevance picks sentences that are close to the document's
overall meaning but not repetitive:

```mermaid
flowchart LR
    A["Sentence vectors E<br/>(normalised)"] --> B["centroid c = mean(E)"]
    B --> C["relevance_i = cos(E_i, c)"]
    C --> D["score_i = relevance_i − 0.6 · max_sim(i, selected)"]
    D --> F["pick argmax score,<br/>update max_sim"]
    F --> G{"top_k picked?"}
    G -- no --> D
    G -- yes --> H["sort picks by<br/>position in document"]
```

It is fully deterministic and vectorised with NumPy: one similarity matrix, then
O(k·n) work per document.

---

## Translation (`backend._translate_text`)

```mermaid
flowchart TD
    S["text, src → tgt"] --> SAME{"src = tgt?"}
    SAME -- yes --> RET["return text unchanged"]
    SAME -- no --> M{"Marian model<br/>for this pair?"}
    M -- yes --> MT["Marian<br/>en→X: opus-mt-en-{hi,ml,mr,ur,es,fr,de}<br/>en→kn/ta/te: opus-mt-en-dra + >>kan<< …<br/>en→bn/gu/pa: opus-mt-en-inc + >>ben<< …<br/>X→en: opus-mt-mul-en"]
    M -- no --> ML
    MT -->|all chunks ok| DONE["translation"]
    MT -->|failed| ML{"Multilingual model<br/>supports both?"}
    ML -- yes --> MB["mBART-50 (default)<br/>or NLLB-200"]
    ML -- no --> ON
    MB -->|ok| DONE
    MB -->|failed| ON{"ENABLE_ONLINE_<br/>TRANSLATION?"}
    ON -- yes --> G["Google Translate<br/>(deep-translator)"]
    ON -- no --> NONE["None → caller adds warning"]
    G -->|ok| DONE
    G -->|failed / rate-limited| NONE
```

Each backend translates the **whole text in chunks**: sentences are grouped up to
400 tokens for models, or 4,500 characters for Google. Line and paragraph breaks are
kept as separate chunks so layout survives. If any chunk fails, the next backend is
tried for the whole text.

| Language | English → language (Marian) | mBART-50 | NLLB-200 |
|---|---|---|---|
| Kannada `kn` | `opus-mt-en-dra` `>>kan<<` | ✗ | `kan_Knda` |
| Tamil `ta` / Telugu `te` | `opus-mt-en-dra` `>>tam<<` / `>>tel<<` | ✓ | ✓ |
| Malayalam `ml` | `opus-mt-en-ml` | ✓ | ✓ |
| Hindi `hi` / Marathi `mr` / Urdu `ur` | `opus-mt-en-{hi,mr,ur}` | ✓ | ✓ |
| Bengali `bn` / Gujarati `gu` | `opus-mt-en-inc` `>>ben<<` / `>>guj<<` | ✓ | ✓ |
| Punjabi `pa` | `opus-mt-en-inc` `>>pan_Guru<<` | ✗ | `pan_Guru` |
| Spanish / French / German | `opus-mt-en-{es,fr,de}` | ✓ | ✓ |
| any → English | `opus-mt-mul-en` | ✓ (listed languages) | ✓ |

---

## Model loading, caching and concurrency

```mermaid
stateDiagram-v2
    [*] --> NotLoaded
    NotLoaded --> Loading: first request needs model<br/>(acquire _LOAD_LOCK)
    Loading --> Ready: from_pretrained OK
    Loading --> Failed: error (missing package, download failure, OOM)
    Ready --> Ready: reused by every request
    Failed --> Failed: fallback used, no retry<br/>(restart the app after fixing)
```

- Models load lazily and are cached per process. With `LIGHTWEIGHT_MODE=true` they are never loaded.
- `_LOAD_LOCK` stops concurrent first requests from loading the same multi-GB model twice.
- The multilingual tokenizer's `src_lang` is shared state, so setting it and encoding happen under `_MULTI_LOCK`.
- Each WSGI worker process holds its own copy of the models. Size the worker count to your RAM or GPU.

---

## PDF export and Indic scripts

ReportLab's built-in fonts cover only Latin-1, so `exporter.py` picks fonts itself:

```mermaid
flowchart TD
    T["Text (summary, keywords, …)"] --> ESC["Split on whitespace into words"]
    ESC --> W{"word contains<br/>Indic / Arabic letters?"}
    W -- no --> BASE["base font<br/>Noto Sans / DejaVu / Arial / Helvetica"]
    W -- yes --> F{"font for that script<br/>installed?"}
    F -- no --> MISS["base font + warning logged<br/>(renders as boxes)"]
    F -- yes --> COV{"font has glyphs for<br/>every character?"}
    COV -- yes --> SCR["&lt;font name=RMTC-kannada&gt; word &lt;/font&gt;"]
    COV -- no --> BASE
    BASE & SCR & MISS --> XML["XML-escape every run"]
    XML --> P["Paragraph(shaping=1)<br/>HarfBuzz shapes conjuncts & vowel signs"]
```

- Fonts are found by indexing TTF files in `PDF_FONT_DIR`, `./fonts` and the OS font folders.
  Per script it looks for Noto Sans *Script*, then Nirmala UI, then the old Windows fonts (Tunga, Mangal, Latha …), then Lohit.
- Fonts are switched per **word**, not per character, because ReportLab can't shape a word
  whose characters span two fonts. A word like `(ಕನ್ನಡ)` is drawn entirely in the Kannada font,
  which includes the brackets.
- All user text is XML-escaped before ReportLab's markup parser sees it.
- Right-to-left (Urdu) text is right-aligned, but word order needs `rlbidi`, which isn't on PyPI.
  Word export handles Urdu correctly.

---

## Security model

```mermaid
flowchart LR
    REQ["Request"] --> SIZE{"≤ MAX_UPLOAD_MB?"}
    SIZE -- no --> E413["413"]
    SIZE -- yes --> A{"AUTH_ENABLED?"}
    A -- no --> V["View"]
    A -- yes --> S{"session<br/>logged_in?"}
    S -- yes --> V
    S -- "no (page)" --> L["302 → /login?next=…"]
    S -- "no (/api/*)" --> E401["401 JSON"]
```

- Passwords are checked against a Werkzeug hash (`APP_PASSWORD_HASH`), and the username is compared in
  constant time. After login, `next` only redirects to local paths, which blocks open redirects.
- `FLASK_SECRET_KEY` must be set for stable, unforgeable sessions. Without it a random key is generated per start.
- Templates rely on Jinja autoescaping. Per-document data reaches JavaScript only through a
  `tojson` JSON block, never through inline event-handler strings.
- CDN assets (Bootstrap, jQuery, Popper) are pinned with Subresource Integrity hashes.
- Online translation and TTS send text to Google. Disable them for confidential data.
