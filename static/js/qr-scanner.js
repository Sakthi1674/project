/**
 * QRScanner - Local Webcam QR Code Scanning Engine
 * Uses pure HTML5 Canvas and jsQR (100% local, zero-cloud)
 */
class QRScanner {
    constructor(videoElement, canvasElement, options = {}) {
        this.video = videoElement;
        this.canvas = canvasElement || document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
        this.stream = null;
        this.scanning = false;
        this.onScan = options.onScan || (() => {});
        this.onError = options.onError || (() => {});
        this.animFrameId = null;
        this.facingMode = options.facingMode || 'environment';
    }

    async start() {
        if (this.scanning) return;
        try {
            const constraints = {
                video: {
                    facingMode: this.facingMode,
                    width: { ideal: 640 },
                    height: { ideal: 480 }
                },
                audio: false
            };

            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            this.video.srcObject = this.stream;
            this.video.setAttribute('playsinline', true);
            await this.video.play();
            
            this.scanning = true;
            this.scanFrame();
        } catch (err) {
            console.error('Camera access error:', err);
            let msg = 'Could not access camera. Please allow camera permissions.';
            if (err.name === 'NotAllowedError') {
                msg = 'Camera access was denied. Please allow camera permissions in your browser settings.';
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                msg = 'No camera found on this device.';
            }
            this.onError(msg, err);
        }
    }

    scanFrame() {
        if (!this.scanning) return;

        if (this.video.readyState === this.video.HAVE_ENOUGH_DATA) {
            this.canvas.width = this.video.videoWidth;
            this.canvas.height = this.video.videoHeight;
            this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);

            const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
            if (typeof jsQR !== 'undefined') {
                const code = jsQR(imageData.data, imageData.width, imageData.height, {
                    inversionAttempts: 'dontInvert'
                });

                if (code && code.data && code.data.trim() !== '') {
                    this.onScan(code.data.trim(), code.location);
                }
            }
        }

        this.animFrameId = requestAnimationFrame(() => this.scanFrame());
    }

    stop() {
        this.scanning = false;
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.video) {
            this.video.srcObject = null;
        }
    }
}

window.QRScanner = QRScanner;
