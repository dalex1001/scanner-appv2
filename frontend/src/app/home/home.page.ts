import { Component, ViewChild, ElementRef, OnInit, OnDestroy, ChangeDetectorRef, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: true,
  imports: [CommonModule], 
  schemas: [CUSTOM_ELEMENTS_SCHEMA]
})
export class HomePage implements OnInit, OnDestroy {
  @ViewChild('videoElement', { static: false }) videoElement?: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasElement', { static: false }) canvasElement?: ElementRef<HTMLCanvasElement>;

  isAnalyzing = false;
  capturedImage: string | null = null;
  boardAnalysisResult: any = null;
  mediaStream: MediaStream | null = null;

  videoDevices: MediaDeviceInfo[] = [];
  selectedDeviceId: string = '';

  backendUrl = 'http://127.0.0.1:8001/api/identify-board';

  constructor(private cdr: ChangeDetectorRef) {}

  async ngOnInit() {
    await this.loadVideoDevices();
    setTimeout(() => this.startCamera(), 100);
  }

  ngOnDestroy() {
    this.stopCamera();
  }

  async loadVideoDevices() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      this.videoDevices = devices.filter(device => device.kind === 'videoinput');
      if (this.videoDevices.length > 0) {
        this.selectedDeviceId = this.videoDevices[0].deviceId;
      }
    } catch (err) {
      console.error('Error listing devices', err);
    }
  }

  onCameraChange(event: any) {
    this.selectedDeviceId = event.detail.value;
    this.stopCamera();
    this.startCamera();
  }

  async startCamera() {
    try {
      const constraints: MediaStreamConstraints = {
        video: this.selectedDeviceId 
          ? { deviceId: { exact: this.selectedDeviceId } } 
          : { facingMode: 'environment' }
      };

      this.mediaStream = await navigator.mediaDevices.getUserMedia(constraints);
      if (this.videoElement && this.videoElement.nativeElement) {
        this.videoElement.nativeElement.srcObject = this.mediaStream;
      }
    } catch (err) {
      console.error('Error accessing the camera', err);
    }
  }

  stopCamera() {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
  }

  capturePhoto() {
    const video = this.videoElement?.nativeElement;
    const canvas = this.canvasElement?.nativeElement;

    if (video && canvas) {
      const context = canvas.getContext('2d');
      if (context) {
        const MAX_WIDTH = 1024;
        let width = video.videoWidth || 1280;
        let height = video.videoHeight || 720;

        if (width > MAX_WIDTH) {
          height = Math.floor(height * (MAX_WIDTH / width));
          width = MAX_WIDTH;
        }

        canvas.width = width;
        canvas.height = height;
        context.drawImage(video, 0, 0, width, height);
        
        this.capturedImage = canvas.toDataURL('image/jpeg', 0.8);
      }
    }
  }

  // Swapped to native fetch() to bypass Angular module crashes entirely
  async identifyBoard() {
    if (!this.capturedImage) return;

    this.isAnalyzing = true;
    this.boardAnalysisResult = null;
    this.cdr.detectChanges();

    try {
      // AbortController acts as our custom timeout (120 seconds)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);

      const response = await fetch(this.backendUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_data: this.capturedImage }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      this.isAnalyzing = false;
      this.boardAnalysisResult = data;
      this.cdr.detectChanges();

    } catch (err: any) {
      this.isAnalyzing = false;
      this.boardAnalysisResult = {
        status: 'error',
        message: err.name === 'AbortError' 
          ? 'Google API is experiencing extreme delays. Please try scanning again.' 
          : 'Failed to analyze circuit board. Is the Python backend running?'
      };
      this.cdr.detectChanges();
      console.error('Analysis API Error:', err);
    }
  }

  resetScanner() {
    this.capturedImage = null;
    this.boardAnalysisResult = null;
    this.isAnalyzing = false;
    this.cdr.detectChanges();
  }
}