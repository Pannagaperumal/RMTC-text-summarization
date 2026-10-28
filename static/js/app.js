// State Management
let currentTab = 'text';
let selectedFiles = [];
let latestResult = null;
let currentUtterance = null;
let isSpeaking = false;

// BCP 47 Language Tag Mapping for Browser SpeechSynthesis API
const SPEECH_LANG_MAP = {
    'en': 'en-US',
    'kn': 'kn-IN',
    'hi': 'hi-IN',
    'bn': 'bn-IN',
    'ta': 'ta-IN',
    'te': 'te-IN',
    'ml': 'ml-IN',
    'mr': 'mr-IN',
    'gu': 'gu-IN',
    'pa': 'pa-IN',
    'ur': 'ur-PK',
    'ne': 'ne-NP',
    'es': 'es-ES',
    'fr': 'fr-FR',
    'de': 'de-DE',
    'zh-cn': 'zh-CN',
    'ar': 'ar-SA',
    'ru': 'ru-RU',
    'ja': 'ja-JP'
};

// Initialize event listeners
document.addEventListener('DOMContentLoaded', () => {
    updateWordCount();
});

// Tab Switcher
function switchTab(tabName) {
    currentTab = tabName;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    document.getElementById(`tab-${tabName}-btn`).classList.add('active');
    document.getElementById(`tab-${tabName}-content`).classList.add('active');
}

// Text word counter
function updateWordCount() {
    const text = document.getElementById('text-input').value.trim();
    const count = text ? text.split(/\s+/).length : 0;
    document.getElementById('word-count').innerText = `${count} words`;
}

function clearText() {
    document.getElementById('text-input').value = '';
    updateWordCount();
}

// File Drag & Drop Handlers
function triggerFileInput() {
    document.getElementById('file-input').click();
}

function handleDragOver(e) {
    e.preventDefault();
    document.getElementById('dropzone').classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    document.getElementById('dropzone').classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    document.getElementById('dropzone').classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        addFiles(Array.from(e.dataTransfer.files));
    }
}

function handleFileSelect(e) {
    if (e.target.files && e.target.files.length > 0) {
        addFiles(Array.from(e.target.files));
    }
}

function addFiles(files) {
    files.forEach(f => {
        if (!selectedFiles.some(existing => existing.name === f.name && existing.size === f.size)) {
            selectedFiles.push(f);
        }
    });
    renderFileList();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
}

function renderFileList() {
    const container = document.getElementById('file-list');
    container.innerHTML = '';
    selectedFiles.forEach((file, idx) => {
        const item = document.createElement('div');
        item.className = 'file-item';
        item.innerHTML = `
            <span><i class="fa-solid fa-file"></i> ${file.name} (${(file.size / 1024).toFixed(1)} KB)</span>
            <i class="fa-solid fa-trash file-remove" onclick="removeFile(${idx})"></i>
        `;
        container.appendChild(item);
    });
}

// Asynchronous Form Submit Handler
async function handleFormSubmit(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('btn-submit');
    const loadingOverlay = document.getElementById('loading-overlay');
    const emptyState = document.getElementById('empty-state');
    const resultContainer = document.getElementById('result-container');
    const statusPill = document.getElementById('status-pill');

    const formData = new FormData();
    const langSelect = document.getElementById('language-select').value;
    const modeSelect = document.getElementById('mode-select').value;
    const explainCheck = document.getElementById('explain-checkbox').checked;

    formData.append('language', langSelect);
    formData.append('summary_mode', modeSelect);
    formData.append('explain', explainCheck ? 'true' : 'false');

    if (currentTab === 'text') {
        const rawText = document.getElementById('text-input').value.trim();
        if (!rawText) {
            showToast('Please enter text or switch to document upload.', true);
            return;
        }
        formData.append('text', rawText);
    } else {
        if (selectedFiles.length === 0) {
            showToast('Please upload at least one document.', true);
            return;
        }
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });
    }

    // UI Loading State
    emptyState.classList.add('hidden');
    resultContainer.classList.add('hidden');
    loadingOverlay.classList.remove('hidden');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Summarizing & Translating...';
    statusPill.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing';

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok || data.status === 'error') {
            throw new Error(data.message || 'Error executing summarization backend.');
        }

        latestResult = data;
        renderResults(data);

        statusPill.innerHTML = '<i class="fa-solid fa-circle-check" style="color:#10b981;"></i> Complete';

    } catch (err) {
        showToast(err.message || 'Failed to process request.', true);
        emptyState.classList.remove('hidden');
        statusPill.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i> Failed';
    } finally {
        loadingOverlay.classList.add('hidden');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Generate Summary & Translate';
    }
}

// Render Results View
function renderResults(data) {
    document.getElementById('result-container').classList.remove('hidden');

    document.getElementById('output-lang-badge').innerText = data.language_name || 'Translated';
    const words = data.summary ? data.summary.split(/\s+/).length : 0;
    document.getElementById('output-word-count').innerText = `${words} words`;
    document.getElementById('output-summary').innerText = data.summary;

    // Render Keywords
    const kwSection = document.getElementById('keywords-section');
    const kwList = document.getElementById('keywords-list');
    kwList.innerHTML = '';

    if (data.keywords && data.keywords.length > 0) {
        kwSection.classList.remove('hidden');
        data.keywords.forEach(kw => {
            const pill = document.createElement('span');
            pill.className = 'keyword-pill';
            pill.innerText = kw;
            kwList.appendChild(pill);
        });
    } else {
        kwSection.classList.add('hidden');
    }

    // Render Explanation
    const explSection = document.getElementById('explanation-section');
    const explContent = document.getElementById('explanation-content');

    if (data.explanation) {
        explSection.classList.remove('hidden');
        explContent.innerText = data.explanation;
    } else {
        explSection.classList.add('hidden');
    }
}

// Dedicated Action Button 1: Speak Output (Text-To-Speech)
function toggleSpeech() {
    if (!latestResult || !latestResult.summary) {
        showToast('No summary available to speak.', true);
        return;
    }

    if (isSpeaking) {
        stopSpeech();
        return;
    }

    const textToSpeak = latestResult.summary;
    const langCode = latestResult.language || 'en';
    const speechLang = SPEECH_LANG_MAP[langCode] || langCode;

    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); // Stop any previous playback

        currentUtterance = new SpeechSynthesisUtterance(textToSpeak);
        currentUtterance.lang = speechLang;
        currentUtterance.rate = 0.95;

        // Try selecting matching voice if available
        const voices = window.speechSynthesis.getVoices();
        const matchingVoice = voices.find(v => v.lang.toLowerCase() === speechLang.toLowerCase() || v.lang.startsWith(speechLang.split('-')[0]));
        if (matchingVoice) {
            currentUtterance.voice = matchingVoice;
        }

        currentUtterance.onstart = () => {
            isSpeaking = true;
            updateSpeechUI(true);
        };

        currentUtterance.onend = () => {
            isSpeaking = false;
            updateSpeechUI(false);
        };

        currentUtterance.onerror = (e) => {
            console.warn('Browser SpeechSynthesis failed, falling back to gTTS endpoint:', e);
            fallbackBackendTTS(textToSpeak, langCode);
        };

        window.speechSynthesis.speak(currentUtterance);
    } else {
        fallbackBackendTTS(textToSpeak, langCode);
    }
}

function stopSpeech() {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }
    const audioEl = document.getElementById('fallback-audio-player');
    if (audioEl) {
        audioEl.pause();
    }
    isSpeaking = false;
    updateSpeechUI(false);
}

function updateSpeechUI(speaking) {
    const speakLabel = document.getElementById('speak-label');
    const speakIcon = document.getElementById('speak-icon');
    const audioBar = document.getElementById('audio-bar');

    if (speaking) {
        speakLabel.innerText = 'Stop Speaking';
        speakIcon.className = 'fa-solid fa-circle-stop';
        audioBar.classList.remove('hidden');
    } else {
        speakLabel.innerText = 'Speak Output';
        speakIcon.className = 'fa-solid fa-volume-high';
        audioBar.classList.add('hidden');
    }
}

// Fallback backend TTS via gTTS audio stream
async function fallbackBackendTTS(text, language) {
    try {
        updateSpeechUI(true);
        document.getElementById('audio-status-text').innerText = 'Generating Backend Audio...';

        const res = await fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, language: language })
        });

        if (!res.ok) throw new Error('Audio generation failed.');

        const blob = await res.blob();
        const audioUrl = URL.createObjectURL(blob);
        
        let audioEl = document.getElementById('fallback-audio-player');
        if (!audioEl) {
            audioEl = document.createElement('audio');
            audioEl.id = 'fallback-audio-player';
            document.body.appendChild(audioEl);
        }
        audioEl.src = audioUrl;
        audioEl.onended = () => {
            isSpeaking = false;
            updateSpeechUI(false);
        };
        audioEl.play();
        isSpeaking = true;
        document.getElementById('audio-status-text').innerText = 'Playing Audio Speech...';

    } catch (err) {
        showToast('TTS audio playback failed: ' + err.message, true);
        isSpeaking = false;
        updateSpeechUI(false);
    }
}

// Dedicated Action Button 2: Copy to Clipboard
function copySummaryToClipboard() {
    if (!latestResult || !latestResult.summary) {
        showToast('No output to copy.', true);
        return;
    }

    navigator.clipboard.writeText(latestResult.summary).then(() => {
        showToast('Summary copied to clipboard!');
    }).catch(err => {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = latestResult.summary;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Summary copied to clipboard!');
    });
}

// Dedicated Action Button 3: Download PDF
async function downloadPDF() {
    if (!latestResult) {
        showToast('No output result to download.', true);
        return;
    }

    try {
        const response = await fetch('/api/download/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(latestResult)
        });

        if (!response.ok) throw new Error('PDF generation failed.');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Summary_${latestResult.language_name || 'Output'}.pdf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showToast('PDF summary report downloaded!');
    } catch (err) {
        showToast('Failed to download PDF: ' + err.message, true);
    }
}

// Dedicated Action Button 4: Download Word (.docx)
async function downloadDOCX() {
    if (!latestResult) {
        showToast('No output result to download.', true);
        return;
    }

    try {
        const response = await fetch('/api/download/docx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(latestResult)
        });

        if (!response.ok) throw new Error('DOCX generation failed.');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Summary_${latestResult.language_name || 'Output'}.docx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showToast('Word document (.docx) downloaded!');
    } catch (err) {
        showToast('Failed to download Word document: ' + err.message, true);
    }
}

// Helper Toast Notification
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    const toastMsg = document.getElementById('toast-message');
    const toastIcon = document.getElementById('toast-icon');

    toastMsg.innerText = message;

    if (isError) {
        toast.style.background = '#ef4444';
        toastIcon.className = 'fa-solid fa-circle-exclamation';
    } else {
        toast.style.background = '#10b981';
        toastIcon.className = 'fa-solid fa-circle-check';
    }

    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3500);
}
