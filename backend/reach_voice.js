(function(root) {
class VoiceGuide {
  constructor({ synth = globalThis.speechSynthesis, Utterance = globalThis.SpeechSynthesisUtterance, fetchAudio = null, audio = null, onChange = () => {}, timeoutMs = null, captionMs = 1800 } = {}) {
    this.synth = synth; this.Utterance = Utterance; this.onChange = onChange;
    this.fetchAudio = fetchAudio; this.audio = audio;
    this.timeoutMs = timeoutMs; this.captionMs = captionMs; this.enabled = true;
    this.busy = false; this.failed = false; this.caption = ''; this.status = fetchAudio ? 'Molly voice' : 'Device voice';
  }
  cancel() {
    this.finish?.(false); this.finish = null;
    if (this.audio) { this.audio.pause(); this.audio.onended = null; this.audio.onerror = null; }
    this.synth?.cancel(); this.busy = false; this.failed = false;
  }
  speak(text) {
    this.cancel(); this.caption = text; this.busy = true; this.failed = false;
    this.status = this.enabled ? (this.fetchAudio ? 'Preparing Molly voice' : 'Speaking with device voice') : 'Captions only'; this.onChange(this);
    return new Promise(resolve => {
      let timer, done = false, utterance;
      const finish = (ok, error = false) => {
        if (done) return; done = true; clearTimeout(timer);
        if (utterance) { utterance.onend = null; utterance.onerror = null; }
        if (this.audio) { this.audio.onended = null; this.audio.onerror = null; if (error) this.audio.pause(); }
        this.finish = null; this.busy = false; this.failed = error;
        this.status = error ? 'Voice unavailable. Retry voice or turn it off to continue with captions.'
          : this.enabled ? (this.fetchAudio ? 'Molly voice' : 'Device voice') : 'Captions only';
        this.onChange(this); resolve(ok);
      };
      this.finish = finish;
      if (!this.enabled) { timer = setTimeout(() => finish(true), this.captionMs); return; }
      if (this.fetchAudio) {
        if (!this.audio) { finish(false, true); return; }
        timer = setTimeout(() => finish(false, true), this.timeoutMs ?? 180000);
        Promise.resolve().then(() => this.fetchAudio(text)).then(source => {
          if (done) return;
          this.audio.src = source.startsWith('data:') || source.startsWith('blob:') ? source : 'data:audio/mpeg;base64,' + source;
          this.audio.muted = false; this.audio.volume = 1;
          this.audio.onended = () => finish(true);
          this.audio.onerror = () => finish(false, true);
          this.status = 'Speaking with Molly voice'; this.onChange(this);
          return this.audio.play();
        }).catch(() => finish(false, true));
        return;
      }
      if (!this.synth || !this.Utterance) { finish(false, true); return; }
      try {
        utterance = new this.Utterance(text);
        utterance.lang = 'en-GB'; utterance.rate = 0.92;
        const voices = this.synth.getVoices();
        utterance.voice = voices.find(v => v.lang === 'en-GB') || voices.find(v => /^en[-_]/i.test(v.lang)) || null;
        utterance.onend = () => finish(true);
        utterance.onerror = () => finish(false, true);
        timer = setTimeout(() => { finish(false, true); this.synth.cancel(); }, this.timeoutMs ?? Math.max(15000, text.length * 100 + 5000));
        this.synth.speak(utterance);
      } catch { finish(false, true); }
    });
  }
}

root.RehynVoiceGuide={VoiceGuide};
if(typeof module!=="undefined"&&module.exports)module.exports={VoiceGuide};
})(globalThis);
