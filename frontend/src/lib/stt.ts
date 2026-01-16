/**
 * Speech-to-text utility using Web Speech API
 * Adapted from reference implementation for behavioral interview
 */

export type STTCallback = (text: string, isFinal: boolean) => void;

export class STTClient {
    private recognition: any = null;
    private callback: STTCallback;
    private isSupported: boolean;
    private isRunning: boolean = false;

    constructor(callback: STTCallback) {
        this.callback = callback;

        // Check for Web Speech API support
        const SpeechRecognition =
            (window as any).SpeechRecognition ||
            (window as any).webkitSpeechRecognition;

        this.isSupported = !!SpeechRecognition;

        if (this.isSupported) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true;
            this.recognition.interimResults = true;
            this.recognition.lang = "en-US";

            this.recognition.onresult = (event: any) => {
                console.log("🎤 Speech result event:", event);

                // Get all results
                let interimTranscript = '';
                let finalTranscript = '';

                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;

                    if (event.results[i].isFinal) {
                        finalTranscript += transcript;
                        console.log("🎤 Final transcript:", transcript);
                    } else {
                        interimTranscript += transcript;
                        console.log("🎤 Interim transcript:", transcript);
                    }
                }

                // Send interim results
                if (interimTranscript) {
                    this.callback(interimTranscript, false);
                }

                // Send final results
                if (finalTranscript) {
                    this.callback(finalTranscript, true);
                }
            };

            this.recognition.onerror = (event: any) => {
                console.error("Speech recognition error:", event.error);

                // Handle specific errors
                if (event.error === 'no-speech') {
                    console.log('No speech detected, continuing...');
                } else if (event.error === 'aborted') {
                    console.log('Speech recognition aborted');
                    this.isRunning = false;
                } else if (event.error === 'not-allowed') {
                    console.error('Microphone permission denied');
                    this.isRunning = false;
                }
            };

            this.recognition.onstart = () => {
                console.log("🎤 Speech recognition started successfully");
                this.isRunning = true;
            };

            this.recognition.onend = () => {
                console.log("🎤 Speech recognition ended");

                // Auto-restart if it should still be running
                if (this.isRunning) {
                    console.log("🎤 Auto-restarting recognition...");
                    setTimeout(() => {
                        if (this.isRunning) {
                            try {
                                this.recognition.start();
                            } catch (error) {
                                console.error("Failed to restart recognition:", error);
                            }
                        }
                    }, 100);
                }
            };
        }
    }

    isAvailable(): boolean {
        return this.isSupported;
    }

    start() {
        if (!this.recognition) {
            console.error("Speech recognition not supported");
            return;
        }

        if (this.isRunning) {
            console.log("🎤 Recognition already running");
            return;
        }

        try {
            this.isRunning = true;
            this.recognition.start();
            console.log("🎤 Starting speech recognition...");
        } catch (error: any) {
            console.error("Failed to start speech recognition:", error);

            // If already started, that's okay
            if (error.message?.includes('already started')) {
                console.log("🎤 Recognition already active");
                this.isRunning = true;
            } else {
                this.isRunning = false;
            }
        }
    }

    stop() {
        if (this.recognition) {
            this.isRunning = false;
            this.recognition.stop();
            console.log("🎤 Speech recognition stopped");
        }
    }
}
