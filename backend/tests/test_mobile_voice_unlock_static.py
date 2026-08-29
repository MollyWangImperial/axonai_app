import os

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_mobile_voice_test")

from backend import server


def test_assessment_unlocks_audio_from_start_tap_and_prefetches_first_voice():
    source = server.POSE_RUNNER_HTML
    start = source.index("async function beginAssessmentSetup(){")
    unlock = source.index("const unlockPromise = unlockAudioPlayback();", start)
    camera = source.index("const camOk = await setupCamera();", start)
    assert unlock < camera
    assert "const firstVoicePromise = firstStep && firstStep.voice" in source
    assert "await Promise.allSettled([unlockPromise, firstVoicePromise]);" in source
    assert source.index("requestAnimationFrame(loop);", camera) < source.index("await startStep();", camera)
    assert "playback.catch(error => finish(() => reject(error)))" in source
    assert "audioEl.play().catch(()=>{})" not in source


def test_rehab_runner_uses_the_same_mobile_audio_unlock_contract():
    source = server.REHAB_RUNNER_HTML_TEMPLATE
    start = source.index('startBtn.addEventListener("click", async () => {')
    unlock = source.index("const unlockPromise = unlockAudioPlayback();", start)
    camera = source.index("const camOk = await setupCamera();", start)
    assert unlock < camera
    assert "const setupVoicePromise = prefetchVoice(CFG.setup_voice);" in source
    assert "CFG.cycle.forEach(step => prefetchVoice(step.voice));" in source
    assert "await Promise.allSettled([unlockPromise, setupVoicePromise]);" in source
    assert "voiceAudioCache" in source
    assert "audioEl.play().catch(()=>{})" not in source


def test_both_runners_build_a_silent_wav_for_ios_user_gesture_unlock():
    assert server.POSE_RUNNER_HTML.count("function unlockAudioPlayback()") == 1
    assert server.REHAB_RUNNER_HTML_TEMPLATE.count("function unlockAudioPlayback()") == 1
    assert "view.setUint32(24, sampleRate, true);" in server.POSE_RUNNER_HTML
    assert "view.setUint32(24, sampleRate, true);" in server.REHAB_RUNNER_HTML_TEMPLATE
