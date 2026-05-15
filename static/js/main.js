// Main JavaScript file for FixMyHyd

// Utility functions
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `flash-message flash-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        ${message}
        <button class="flash-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    // Create flash messages container if it doesn't exist
    let container = document.querySelector('.flash-messages');
    if (!container) {
        container = document.createElement('div');
        container.className = 'flash-messages';
        document.body.appendChild(container);
    }
    
    container.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// Form validation
function validateForm(form) {
    const requiredFields = form.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('error');
            isValid = false;
        } else {
            field.classList.remove('error');
        }
    });
    
    return isValid;
}

// Add error styling for invalid fields
function addFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
                showNotification('Please fill in all required fields', 'error');
            }
        });
        
        // Remove error styling on input
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('input', function() {
                this.classList.remove('error');
            });
        });
    });
}

// Image preview functionality
function initImagePreview() {
    const imageInputs = document.querySelectorAll('input[type="file"][accept*="image"]');
    
    imageInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const preview = document.getElementById('imagePreview');
                    const img = document.getElementById('previewImg');
                    if (preview && img) {
                        img.src = e.target.result;
                        preview.style.display = 'block';
                        const uploadContent = document.querySelector('.upload-content');
                        if (uploadContent) {
                            uploadContent.style.display = 'none';
                        }
                    }
                };
                reader.readAsDataURL(file);
            }
        });
    });
}

// Voice recording functionality
function initVoiceRecording() {
    const recordBtn = document.getElementById('recordBtn');
    const stopBtn = document.getElementById('stopBtn');
    const playBtn = document.getElementById('playBtn');
    const statusDiv = document.getElementById('recordingStatus');
    
    if (!recordBtn) return;
    
    let mediaRecorder;
    let audioChunks = [];
    let isRecording = false;
    
    recordBtn.addEventListener('click', startRecording);
    stopBtn.addEventListener('click', stopRecording);
    playBtn.addEventListener('click', playRecording);
    
    async function startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = function(event) {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = function() {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioFile = new File([audioBlob], 'recording.wav', { type: 'audio/wav' });
                
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(audioFile);
                const audioInput = document.getElementById('audioInput');
                if (audioInput) {
                    audioInput.files = dataTransfer.files;
                }
                
                recordBtn.style.display = 'none';
                stopBtn.style.display = 'none';
                playBtn.style.display = 'inline-block';
                if (statusDiv) {
                    statusDiv.textContent = 'Recording saved!';
                }
            };
            
            mediaRecorder.start();
            isRecording = true;
            
            recordBtn.style.display = 'none';
            stopBtn.style.display = 'inline-block';
            if (statusDiv) {
                statusDiv.textContent = 'Recording... Click stop when done.';
            }
        } catch (error) {
            console.error('Error accessing microphone:', error);
            showNotification('Could not access microphone. Please check permissions.', 'error');
        }
    }
    
    function stopRecording() {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
        }
    }
    
    function playRecording() {
        const audioFile = document.getElementById('audioInput').files[0];
        if (audioFile) {
            const audio = new Audio(URL.createObjectURL(audioFile));
            audio.play();
        }
    }
}

// Character counter
function initCharacterCounter() {
    const textareas = document.querySelectorAll('textarea[data-max-length]');
    
    textareas.forEach(textarea => {
        const maxLength = parseInt(textarea.dataset.maxLength) || 500;
        const counter = document.createElement('div');
        counter.className = 'char-count';
        counter.innerHTML = `<span>0</span>/${maxLength} characters`;
        
        textarea.parentNode.appendChild(counter);
        
        textarea.addEventListener('input', function() {
            const count = this.value.length;
            const span = counter.querySelector('span');
            span.textContent = count;
            
            if (count > maxLength) {
                this.value = this.value.substring(0, maxLength);
                span.textContent = maxLength;
            }
        });
    });
}

// Modal functionality
function initModals() {
    const modals = document.querySelectorAll('.modal');
    
    modals.forEach(modal => {
        const closeBtn = modal.querySelector('.modal-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                modal.style.display = 'none';
            });
        }
        
        // Close on outside click
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                this.style.display = 'none';
            }
        });
    });
    
    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            modals.forEach(modal => {
                modal.style.display = 'none';
            });
        }
    });
}

// Table filtering
function initTableFiltering() {
    const filterSelects = document.querySelectorAll('select[data-filter]');
    
    filterSelects.forEach(select => {
        select.addEventListener('change', function() {
            const filterType = this.dataset.filter;
            const filterValue = this.value;
            const table = this.closest('.complaints-section').querySelector('table');
            
            if (!table) return;
            
            const rows = table.querySelectorAll('tbody tr');
            
            rows.forEach(row => {
                const cell = row.querySelector(`[data-${filterType}]`);
                if (!cell) return;
                
                const cellValue = cell.dataset[filterType];
                const shouldShow = !filterValue || cellValue === filterValue;
                
                row.style.display = shouldShow ? '' : 'none';
            });
        });
    });
}

// Loading states
function showLoading(element) {
    const originalContent = element.innerHTML;
    element.dataset.originalContent = originalContent;
    element.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    element.disabled = true;
}

function hideLoading(element) {
    if (element.dataset.originalContent) {
        element.innerHTML = element.dataset.originalContent;
        element.disabled = false;
        delete element.dataset.originalContent;
    }
}

// AJAX form submission
function initAjaxForms() {
    const forms = document.querySelectorAll('form[data-ajax]');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const submitBtn = this.querySelector('button[type="submit"]');
            const formData = new FormData(this);
            const url = this.action;
            const method = this.method || 'POST';
            
            showLoading(submitBtn);
            
            fetch(url, {
                method: method,
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                hideLoading(submitBtn);
                
                if (data.status === 'success') {
                    showNotification(data.message || 'Operation completed successfully', 'success');
                    if (data.redirect) {
                        setTimeout(() => {
                            window.location.href = data.redirect;
                        }, 1000);
                    }
                } else {
                    showNotification(data.error || 'An error occurred', 'error');
                }
            })
            .catch(error => {
                hideLoading(submitBtn);
                console.error('Error:', error);
                showNotification('An error occurred. Please try again.', 'error');
            });
        });
    });
}

// Search functionality
function initSearch() {
    const searchInputs = document.querySelectorAll('input[data-search]');
    
    searchInputs.forEach(input => {
        input.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const targetSelector = this.dataset.search;
            const targetElements = document.querySelectorAll(targetSelector);
            
            targetElements.forEach(element => {
                const text = element.textContent.toLowerCase();
                const shouldShow = text.includes(searchTerm);
                element.style.display = shouldShow ? '' : 'none';
            });
        });
    });
}

// Smooth scrolling
function initSmoothScrolling() {
    const links = document.querySelectorAll('a[href^="#"]');
    
    links.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const targetElement = document.getElementById(targetId);
            
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// Auto-hide flash messages
function initFlashMessages() {
    const flashMessages = document.querySelectorAll('.flash-message');
    
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.animation = 'slideOut 0.3s ease forwards';
            setTimeout(() => {
                if (message.parentElement) {
                    message.remove();
                }
            }, 300);
        }, 5000);
    });
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
    
    .error {
        border-color: #dc2626 !important;
        box-shadow: 0 0 0 3px rgba(220, 38, 38, 0.1) !important;
    }
`;
document.head.appendChild(style);

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    addFormValidation();
    initImagePreview();
    initVoiceRecording();
    initCharacterCounter();
    initModals();
    initTableFiltering();
    initAjaxForms();
    initSearch();
    initSmoothScrolling();
    initFlashMessages();
    
    const forms = document.querySelectorAll('form:not([data-ajax])');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn && this.checkValidity()) {
                // Small delay to ensure form submission starts
                setTimeout(() => {
                    showLoading(submitBtn);
                }, 50);
            }
        });
    });
});

// Export functions for global use
window.FixMyHyd = {
    showNotification,
    validateForm,
    showLoading,
    hideLoading
};
function deleteComplaint(complaintId) {
    if (!confirm("Are you sure you want to delete this complaint? This action cannot be undone.")) {
        return;
    }

    fetch(`/api/admin/complaints/${complaintId}`, {
        method: 'DELETE',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            alert('Complaint deleted successfully');
            // Remove the row from table without reloading
            const row = document.querySelector(`#complaintsTableBody tr[data-id="${complaintId}"]`);
            if (row) row.remove();
            location.reload();
        } else {
            alert('Error deleting complaint: ' + data.message || data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error deleting complaint');
    });
    
}
// Terms of Service modal — only present on the registration page
const popModal = document.getElementById('pop-modal');
const popLink = document.getElementById('pop-terms-link');
const popClose = document.getElementById('pop-close');
const popAccept = document.getElementById('pop-accept');

if (popLink && popModal && popClose && popAccept) {
    popLink.addEventListener('click', (e) => {
        e.preventDefault();
        popModal.style.display = 'block';
    });

    popClose.addEventListener('click', () => {
        popModal.style.display = 'none';
    });

    window.addEventListener('click', (e) => {
        if (e.target === popModal) popModal.style.display = 'none';
    });

    popAccept.addEventListener('click', () => {
        popModal.style.display = 'none';
    });
}

