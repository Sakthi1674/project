/**
 * Main Application JavaScript
 * Attendance System - Face Recognition & QR Validation
 */

// --- Toast Notification System ---
function showToast(message, type = 'info', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-item toast-${type}`;
    
    // Icon based on type
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'danger' || type === 'error') icon = '⚠️';
    if (type === 'warning') icon = '🔔';

    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-content">${message}</div>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);

    // Auto remove
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

// --- Global Camera Utilities ---
class CameraManager {
    static async startCamera(videoElement, facingMode = 'user') {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: facingMode,
                    width: { ideal: 640 },
                    height: { ideal: 480 }
                },
                audio: false
            });
            videoElement.srcObject = stream;
            videoElement.setAttribute('playsinline', true);
            await videoElement.play();
            return stream;
        } catch (err) {
            console.error('CameraManager Error:', err);
            let msg = 'Could not access webcam. Please ensure camera permissions are granted.';
            if (err.name === 'NotAllowedError') {
                msg = 'Webcam permission was denied. Please allow camera access.';
            } else if (err.name === 'NotFoundError') {
                msg = 'No camera found on this computer.';
            }
            showToast(msg, 'danger');
            throw err;
        }
    }

    static stopCamera(videoElement, stream) {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        if (videoElement) {
            videoElement.srcObject = null;
        }
    }

    static captureBase64(videoElement, quality = 0.9) {
        const canvas = document.createElement('canvas');
        canvas.width = videoElement.videoWidth || 640;
        canvas.height = videoElement.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL('image/jpeg', quality);
    }
}

// --- Face Model Training Action ---
async function triggerModelTraining(btnElement) {
    const btn = btnElement || document.getElementById('btn-train-model');
    const originalHtml = btn ? btn.innerHTML : '';
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner"></span> Training Model...`;
    }
    
    showToast('Starting LBPH face recognition model training...', 'info', 3000);

    try {
        const response = await fetch('/train-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.success) {
            showToast(`Success! ${data.message}`, 'success', 5000);
            const badge = document.getElementById('model-status-badge');
            if (badge) {
                badge.className = 'badge badge-success';
                badge.innerText = 'Model Ready';
            }
        } else {
            showToast(`Training Warning: ${data.message}`, 'warning', 5000);
        }
    } catch (err) {
        console.error('Training error:', err);
        showToast('Server connection error during training.', 'danger');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

// --- Export HTML Table to CSV ---
function exportTableToCSV(filename = 'attendance_report.csv') {
    const table = document.querySelector('.data-table');
    if (!table) {
        showToast('No table found to export.', 'warning');
        return;
    }

    let csv = [];
    const rows = table.querySelectorAll('tr');

    for (let i = 0; i < rows.length; i++) {
        const row = [];
        const cols = rows[i].querySelectorAll('th, td');
        for (let j = 0; j < cols.length; j++) {
            // Clean text
            let text = cols[j].innerText.replace(/"/g, '""').trim();
            row.push(`"${text}"`);
        }
        csv.push(row.join(','));
    }

    const csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
    const downloadLink = document.createElement('a');
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    downloadLink.remove();
    showToast('Attendance report exported to CSV.', 'success');
}

window.CameraManager = CameraManager;
window.showToast = showToast;
window.triggerModelTraining = triggerModelTraining;
window.exportTableToCSV = exportTableToCSV;
