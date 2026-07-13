// API Configuration
const API_URL = 'http://localhost:8000';

// Tab switching
function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(`${tabName}-tab`).classList.add('active');
    
    // Update nav links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    document.querySelector(`.nav-link[onclick="showTab('${tabName}')"]`).classList.add('active');
    
    // Load documents if documents tab
    if (tabName === 'documents') {
        loadDocuments();
    }
    
    // Update stats if admin tab
    if (tabName === 'admin') {
        loadStats();
    }
}

// Chat functionality
async function sendQuestion() {
    const input = document.getElementById('questionInput');
    const question = input.value.trim();
    
    if (!question) return;
    
    const messagesContainer = document.getElementById('chatMessages');
    
    // Add user message
    messagesContainer.innerHTML += `
        <div class="user-message">
            ${question}
        </div>
    `;
    
    // Clear input
    input.value = '';
    
    // Show typing indicator
    const typingId = Date.now();
    messagesContainer.innerHTML += `
        <div class="assistant-message" id="typing-${typingId}">
            <span style="color: #8888aa;">🧠 Thinking...</span>
        </div>
    `;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    
    try {
        const response = await fetch(`${API_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                temperature: 0.2,
                top_k: 3
            })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        document.getElementById(`typing-${typingId}`).remove();
        
        // Add assistant response
        let sourcesHtml = '';
        if (data.sources && data.sources.length > 0) {
            sourcesHtml = '<div class="sources"><small>📄 Sources:</small>';
            data.sources.forEach((source, i) => {
                sourcesHtml += `<small>${i+1}. ${source.filename} (${source.file_type})</small>`;
            });
            sourcesHtml += '</div>';
        }
        
        messagesContainer.innerHTML += `
            <div class="assistant-message">
                ${data.answer}
                ${sourcesHtml}
            </div>
        `;
        
    } catch (error) {
        document.getElementById(`typing-${typingId}`).remove();
        messagesContainer.innerHTML += `
            <div class="assistant-message" style="border-color: #ff4444;">
                ❌ Error: ${error.message}
                <br><small>Make sure the backend is running: python backend.py</small>
            </div>
        `;
    }
    
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// File upload with drag and drop
document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    
    dropZone.addEventListener('click', function() {
        fileInput.click();
    });
    
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        this.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        this.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const input = document.createElement('input');
            input.type = 'file';
            input.files = files;
            handleFiles(input.files);
        }
    });
    
    fileInput.addEventListener('change', function() {
        handleFiles(this.files);
    });
});

let selectedFiles = [];

function handleFiles(files) {
    const fileList = document.getElementById('fileList');
    
    for (let file of files) {
        selectedFiles.push(file);
        fileList.innerHTML += `
            <div class="file-item">
                <span>📎 ${file.name}</span>
                <span style="color: #8888aa; font-size: 0.8rem;">${(file.size / 1024).toFixed(1)} KB</span>
            </div>
        `;
    }
}

async function uploadDocuments(event) {
    event.preventDefault();
    
    if (selectedFiles.length === 0) {
        document.getElementById('uploadStatus').innerHTML = `<div style="color: #ffaa00; padding: 1rem;">⚠️ Please select files to upload.</div>`;
        return;
    }
    
    const formData = new FormData();
    selectedFiles.forEach(file => {
        formData.append('files', file);
    });
    
    const statusDiv = document.getElementById('uploadStatus');
    statusDiv.innerHTML = `<div style="color: #00D4FF;">⏳ Uploading and processing ${selectedFiles.length} files...</div>`;
    
    const uploadBtn = document.querySelector('.upload-btn');
    uploadBtn.disabled = true;
    
    try {
        const response = await fetch(`${API_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.innerHTML = `<div style="color: #00FF88;">✅ ${data.message}</div>`;
            // Clear file list
            document.getElementById('fileList').innerHTML = '';
            selectedFiles = [];
            document.getElementById('fileInput').value = '';
            // Reload documents and stats
            loadDocuments();
            loadStats();
        } else {
            statusDiv.innerHTML = `<div style="color: #ff4444;">❌ ${data.message}</div>`;
        }
    } catch (error) {
        statusDiv.innerHTML = `<div style="color: #ff4444;">❌ Error: ${error.message}</div>`;
    }
    
    uploadBtn.disabled = false;
}

async function loadDocuments() {
    const container = document.getElementById('documentList');
    container.innerHTML = '<div class="loading-message">Loading documents...</div>';
    
    try {
        const response = await fetch(`${API_URL}/documents`);
        const data = await response.json();
        
        if (data.documents && data.documents.length > 0) {
            container.innerHTML = '';
            data.documents.forEach(doc => {
                const icon = getFileIcon(doc.category);
                container.innerHTML += `
                    <div class="document-card">
                        <div class="doc-icon">${icon}</div>
                        <div class="doc-name">${doc.name}</div>
                        <div class="doc-meta">${doc.category}</div>
                        <div class="doc-meta">${(doc.size / 1024).toFixed(1)} KB</div>
                        <button class="delete-btn" onclick="deleteDocument('${doc.name}')">🗑️ Delete</button>
                    </div>
                `;
            });
        } else {
            container.innerHTML = '<div class="loading-message">No documents found. Upload some using the Admin tab!</div>';
        }
    } catch (error) {
        container.innerHTML = `<div class="loading-message">❌ Error loading documents: ${error.message}</div>`;
    }
}

function getFileIcon(category) {
    const icons = {
        'Text': '📄',
        'PDF': '📕',
        'Word': '📘',
        'CSV': '📊',
        'Markdown': '📗'
    };
    return icons[category] || '📎';
}

async function deleteDocument(filename) {
    if (!confirm(`Are you sure you want to delete ${filename}?`)) return;
    
    try {
        const response = await fetch(`${API_URL}/delete/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            loadDocuments();
            loadStats();
            alert(`✅ ${data.message}`);
        } else {
            alert(`❌ ${data.message}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

async function reindexDocuments() {
    if (!confirm('This will re-index all documents. Continue?')) return;
    
    try {
        const response = await fetch(`${API_URL}/reindex`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            loadStats();
        } else {
            alert(`❌ ${data.message}`);
        }
    } catch (error) {
        alert(`❌ Error: ${error.message}`);
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API_URL}/status`);
        const data = await response.json();
        
        document.getElementById('statChunks').textContent = data.total_chunks || 0;
        
        // Count documents
        const docResponse = await fetch(`${API_URL}/documents`);
        const docData = await docResponse.json();
        document.getElementById('statDocs').textContent = docData.documents ? docData.documents.length : 0;
        
        // Count questions (from chat messages)
        const messages = document.querySelectorAll('.user-message');
        document.getElementById('statQuestions').textContent = messages.length || 0;
        
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Enter key for chat
document.addEventListener('DOMContentLoaded', function() {
    // Load initial data
    loadDocuments();
    loadStats();
    
    // Auto-refresh stats every 30 seconds
    setInterval(loadStats, 30000);
});