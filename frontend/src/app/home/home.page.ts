import { Component, ViewChild, ElementRef, OnDestroy, ChangeDetectorRef } from '@angular/core';

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: false
})
export class HomePage implements OnDestroy {
  @ViewChild('videoElement') videoElement!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasElement') canvasElement!: ElementRef<HTMLCanvasElement>;

  scanResult: any = null;
  uploadMessage: string = '';
  lastScannedCode: string = '';

  // Camera State
  isCameraActive: boolean = false;
  mediaStream: MediaStream | null = null;
  capturedPhotoUrl: string | null = null;
  
  // Camera Tracking
  videoDevices: MediaDeviceInfo[] = [];
  currentDeviceIndex: number = 0;

  // Analysis State
  isProcessingImage: boolean = false;
  boardAnalysisResult: any = null;

  constructor(private cdr: ChangeDetectorRef) {}

  ngOnDestroy() {
    this.stopCamera();
  }

  // --- CAMERA LENS METHODS ---
  async toggleCamera() {
    if (this.isCameraActive) {
      this.stopCamera();
    } else {
      await this.startCamera();
    }
  }

  async startCamera() {
    try {
      // 1. Find all connected cameras on the computer
      if (this.videoDevices.length === 0) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        this.videoDevices = devices.filter(device => device.kind === 'videoinput');
      }

      // 2. Default to rear camera, or use the specific selected USB camera
      let videoConstraints: any = { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } };
      
      if (this.videoDevices.length > 0) {
        const currentDevice = this.videoDevices[this.currentDeviceIndex];
        videoConstraints = { 
          deviceId: { exact: currentDevice.deviceId },
          width: { ideal: 1280 }, 
          height: { ideal: 720 }
        };
      }

      // 3. Start the stream
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints });
      this.isCameraActive = true;
      this.cdr.detectChanges(); 

      setTimeout(() => {
        if (this.videoElement && this.mediaStream) {
          this.videoElement.nativeElement.srcObject = this.mediaStream;
        }
      }, 150);
    } catch (error) {
      console.error('Camera Access Error:', error);
      alert('Unable to access camera. Check browser permissions.');
      this.isCameraActive = false;
      this.cdr.detectChanges();
    }
  }

  async switchCamera() {
    if (this.videoDevices.length > 1) {
      this.currentDeviceIndex = (this.currentDeviceIndex + 1) % this.videoDevices.length;
      this.stopCamera();
      await this.startCamera();
    }
  }

  stopCamera() {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    this.isCameraActive = false;
    this.cdr.detectChanges();
  }

  captureSnapshot() {
    if (!this.videoElement || !this.canvasElement) return;

    const video = this.videoElement.nativeElement;
    const canvas = this.canvasElement.nativeElement;
    
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;

    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      this.capturedPhotoUrl = canvas.toDataURL('image/jpeg', 0.85);
      this.cdr.detectChanges();
    }
  }

  clearSnapshot() {
    this.capturedPhotoUrl = null;
    this.boardAnalysisResult = null;
    this.cdr.detectChanges();
  }

  async analyzeBoard() {
    if (!this.capturedPhotoUrl) return;

    this.isProcessingImage = true;
    this.boardAnalysisResult = null;
    this.cdr.detectChanges();

    try {
      const response = await fetch('http://127.0.0.1:8001/api/identify-board', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_data: this.capturedPhotoUrl })
      });
      
      this.boardAnalysisResult = await response.json();
    } catch (error) {
      console.error('Analysis Error:', error);
      this.boardAnalysisResult = { status: 'error', message: 'Failed to connect to vision backend.' };
    } finally {
      this.isProcessingImage = false;
      this.cdr.detectChanges();
    }
  }

  // --- MANUAL BARCODE SCANNER ---
  async onScan(code: string) {
    const trimmedCode = code.trim();
    if (!trimmedCode) return;

    this.lastScannedCode = trimmedCode;

    try {
      const response = await fetch(`http://127.0.0.1:8001/api/scan?scanned_code=${encodeURIComponent(trimmedCode)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      this.scanResult = await response.json();
      this.cdr.detectChanges();
    } catch (error) {
      console.error('API Error:', error);
      this.scanResult = { error: 'Failed to connect to backend.', match_found: false, scanned_item: trimmedCode };
      this.cdr.detectChanges();
    }
  }

  clearResult() {
    this.scanResult = null;
    this.lastScannedCode = '';
    this.cdr.detectChanges();
  }

  // --- CSV UPLOAD ---
  async onFileSelected(event: any) {
    const file: File = event.target.files[0];
    if (!file) return;

    this.uploadMessage = 'Uploading...';
    this.cdr.detectChanges();
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://127.0.0.1:8001/api/upload-csv', {
        method: 'POST',
        body: formData 
      });
      
      const result = await response.json();
      if (result.status === 'success') {
        this.uploadMessage = `✅ Upload Complete! Added: ${result.added} | Updated: ${result.updated}`;
      } else {
        this.uploadMessage = `❌ Upload Failed: ${result.message}`;
      }
    } catch (error) {
      this.uploadMessage = '❌ Failed to connect to the server.';
    } finally {
      event.target.value = null;
      this.cdr.detectChanges();
    }
  }
}