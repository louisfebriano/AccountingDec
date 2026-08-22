import test from "node:test";
import assert from "node:assert/strict";

import { RecorderSession, selectRecordingMimeType } from "../../pwa/recorder.js";

class FakeRecorder extends EventTarget {
  static isTypeSupported(type) { return type.startsWith("audio/webm"); }

  constructor(stream, options = {}) {
    super();
    this.stream = stream;
    this.mimeType = options.mimeType || "audio/webm";
    this.state = "inactive";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.dispatchEvent(new MessageEvent("dataavailable", { data: new Blob(["voice"]) }));
    this.state = "inactive";
    this.dispatchEvent(new Event("stop"));
  }
}

test("format MediaRecorder dipilih sesuai urutan kompatibilitas", () => {
  assert.equal(selectRecordingMimeType(FakeRecorder), "audio/webm;codecs=opus");
});

test("perekaman dihentikan dan seluruh track mikrofon dilepaskan", async () => {
  const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
  const stream = { getTracks: () => tracks };
  const session = new RecorderSession({
    MediaRecorderCtor: FakeRecorder,
    mediaDevices: { getUserMedia: async () => stream },
  });

  await session.start();
  const blob = await session.stop();

  assert.equal(blob.size > 0, true);
  assert.equal(tracks[0].stopped, true);
  assert.equal(session.stream, null);
  assert.equal(session.chunks.length, 0);
});
