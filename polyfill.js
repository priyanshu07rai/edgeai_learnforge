// Polyfill CustomEvent for Node.js versions older than v19 (such as Node v18 on Jetson)
if (typeof globalThis.CustomEvent === 'undefined') {
  globalThis.CustomEvent = class CustomEvent extends Event {
    constructor(type, dict = {}) {
      super(type, dict);
      this.detail = dict.detail || null;
    }
  };
}
