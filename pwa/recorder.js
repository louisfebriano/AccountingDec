const MIME_TYPE_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

export function selectRecordingMimeType(MediaRecorderCtor = globalThis.MediaRecorder) {
  if (!MediaRecorderCtor) return null;
  return MIME_TYPE_CANDIDATES.find(
    (type) => typeof MediaRecorderCtor.isTypeSupported !== "function" || MediaRecorderCtor.isTypeSupported(type),
  ) || "";
}

export class RecorderSession {
  constructor(options = {}) {
    this.mediaDevices = options.mediaDevices || globalThis.navigator?.mediaDevices;
    this.MediaRecorderCtor = options.MediaRecorderCtor || globalThis.MediaRecorder;
    this.stream = null;
    this.recorder = null;
    this.chunks = [];
  }

  get supported() {
    return Boolean(this.mediaDevices?.getUserMedia && this.MediaRecorderCtor);
  }

  async start() {
    if (!this.supported) throw new Error("Perekaman suara tidak didukung browser ini.");
    this.stream = await this.mediaDevices.getUserMedia({ audio: true });
    const mimeType = selectRecordingMimeType(this.MediaRecorderCtor);
    this.chunks = [];
    this.recorder = mimeType
      ? new this.MediaRecorderCtor(this.stream, { mimeType })
      : new this.MediaRecorderCtor(this.stream);
    this.recorder.addEventListener("dataavailable", (event) => {
      if (event.data?.size) this.chunks.push(event.data);
    });
    this.recorder.start();
  }

  async stop() {
    if (!this.recorder || this.recorder.state === "inactive") {
      this.releaseTracks();
      return null;
    }

    const recorder = this.recorder;
    const stopped = new Promise((resolve) => recorder.addEventListener("stop", resolve, { once: true }));
    recorder.stop();
    await stopped;
    const type = recorder.mimeType || "audio/webm";
    const blob = new Blob(this.chunks, { type });
    this.releaseTracks();
    this.recorder = null;
    this.chunks = [];
    return blob;
  }

  releaseTracks() {
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
    }
    this.stream = null;
  }
}
