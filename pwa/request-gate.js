export class RequestGate {
  constructor() {
    this.busy = false;
  }

  async run(task) {
    if (this.busy) return { skipped: true };
    this.busy = true;
    try {
      return { skipped: false, value: await task() };
    } finally {
      this.busy = false;
    }
  }
}
