# Seated Forward Reach: support and adaptation in Testing

Direct local route: `/testing/seated-forward-reach` (add `?affected_side=left` for the left arm). This opens the existing authenticated Testing runner directly. Testing does not change assessment history, exercise plans or credits. Local attempts now save review videos and angle evidence as described below.

## Patient flow

1. Ask whether a carer or family member is present **before requesting the camera or calibrating**. Presence does not imply hands-on assistance.
2. Run the existing seated camera/lap calibration. Keep the lap anchor locked and show only the selected arm and its diagnostic angle arcs.
3. Start the first target immediately after calibration, without a preliminary small-movement check. The initial raised target is at calibrated shoulder height, never overhead. The initiation target stays to the screen-right of the lap at lap height. These are practical task benchmarks, not validated population norms or an instruction to force the range.
4. After 8 seconds of tracked unsuccessful effort, speak a comfortable, non-coercive encouragement. Allow another 6 tracked seconds at the same target. Only after that retry can the agent choose a reduction, announce it, then move the circle over 0.7 seconds. Contact during motion does not count. At the minimum level, another unsuccessful encouraged retry pauses for support instead of repeatedly challenging the patient.
5. Pause/stop and recording hands-on help are available throughout. Assistance applies conservatively to that step and subsequent steps. A helper should only use support techniques already shown by the patient's therapist, without pulling or forcing the arm. Assistance is explicitly confirmed because monocular pose tracking cannot reliably identify who supplied the movement.

The local Testing flow uses the browser's **device voice** and matching captions; it does not request nova or the cloned voice. If device speech fails, the instruction remains visible for the caption interval and the task continues with captions. Other assessment tasks retain their existing voice provider.

## Policy gradient

This integrated policy differs from the separate port-4197 experiment. It always starts each new reach at full difficulty. A tabular categorical REINFORCE policy chooses **one or two downward levels** after the encouraged retry, rather than sampling a starting height. Difficulty levels are `[1, .85, .70, .55, .40]`. There is no upward action. A final descent with only one available level is forced and does not receive a fictitious policy gradient.

State separates the task step, current level, near/far target evidence, and confirmed assistance. For raised steps, height is the difficulty fraction of the calibrated lap-to-shoulder span; X is fixed. The lap-height initiation step instead reduces its lateral distance by the conservative factor `0.65 + 0.35 × difficulty`. The stable-hold step inherits the previous reach's adapted position and difficulty. The return-to-lap anchor never changes.

Terminal reward is `2 × remaining difficulty × assistance factor` for success and **−1** for an unsuccessful terminal attempt. Assistance factor is 1 independently or 0.5 when help was confirmed. Each executed reduction costs 0.04. Reward-to-go is accumulated backward as `G = −0.04 + 0.95 × G`. Thus a completed easier attempt remains positively rewarded and an unfinished attempt is penalised more. Voluntary stopping and tracking loss do not create failure rewards; a fully observed exhausted attempt does.

For sampled action `a`, probabilities `p`, state baseline `b` and entropy `H`:

`θ_i += .08 × [(G − b)(1[i=a] − p_i) − .01 p_i(log p_i + H)]`

Then `b += .05 × (G − b)`. The baseline is taken before updating. Only executed sampled reductions receive gradients. Parameters persist in session storage for the same account, arm and browser tab, including Test again; closing the tab clears that session. No landmarks or video are stored with the policy. The report includes sampled probabilities, return and advantage so the update can be inspected.

This is a constrained learning experiment, not a clinically validated adaptive treatment policy. Reference: [OpenAI Spinning Up, policy gradients](https://spinningup.openai.com/en/latest/spinningup/rl_intro3.html).

## Movement score

The scoring references for steps 1–3 are initiation elbow extension 120°, then reach and hold elbow extension 110° plus arm elevation 50°. These references do not change when the adaptive target is lowered. Step 4 is scored only by completion of the calibrated lap target: 100 points when completed, 0 when not completed, and unscored when no step was recorded. Angle, form, difficulty and assistance deductions do not apply to that return step. Arm elevation uses model world landmarks; elbow extension uses the aspect-corrected 2D shoulder–elbow–wrist angle. Diagnostic projected arcs remain labelled separately.

For steps 1–3: `step score = (20 × target completed + 80 × mean reference attainment × difficulty) × form factor × assistance factor`. For step 4: `step score = 100 × lap target completed`.

Reference attainment is capped at 1. For Testing T1, arm elevation and elbow extension now use the **maximum valid angle anywhere within that step**, including before target contact. Returning the arm afterward does not erase the peak. At least five valid samples are still required, but the maximum itself may be one accepted sample; low-visibility or invalid frames are excluded. A confidently misplaced keypoint can still cause an erroneous peak. Each angle is maximised independently; target completion and holding remain separate requirements. The maximum and its timestamp are retained even when buffers or charts are downsampled. Return control still uses the valid-sample proportion. Testing T1 trunk lean now uses the shared `testing/trunk-lean-comparison/trunk_lean_metrics.js` shoulder-or-face detector. It takes 45 clear calibration frames while the patient is instructed to sit upright, adjusts shoulder and face apparent size by hip size, and identifies a lean when the shoulder cue exceeds 12° **or** the face cue reaches 7° for at least 0.5 seconds of valid tracked effort. This replaces the prior 3D torso-vector criterion only in Testing T1. The cue estimates are not anatomical angles. Excess shoulder lift above 12° for at least 0.5 seconds is unchanged. Each confirmed compensation reduces the form factor by 0.2. Assistance is applied once per step. The task score averages all four step scores; missing evidence leaves the complete score unavailable.

## Local review video

On localhost, each camera-based assessment task is automatically recorded from camera startup (including initial calibration) until task completion or the app's Stop/Exit action. The full mirrored camera view, aligned pose/angle overlay, live angle values, references, accepted peaks and captions are captured; microphone audio is not recorded. The video is not a screen capture of the entire desktop.

Each attempt gets a unique dated `.webm` or `.mp4` and a companion JSON file in `backend/.local_state/assessment-recordings/`. The results show the absolute path and a playback link. JSON contains the raw step evidence, scoring references/results and video time offsets: `quality.video_start_ms + measurement.peak_elapsed_ms` locates a peak in the video. The recording endpoint is authenticated and restricted to loopback; it never uploads these review files to cloud storage. Existing standard assessment storage is otherwise unchanged.

Saving completes before the Testing results replace the camera runner. A save failure retains the video in the open runner and offers retry or an explicit browser download, without claiming a file was saved. Unsupported recording is reported. Abruptly closing the browser or computer before completion can lose an unfinished recording. Earlier attempts cannot be recorded retroactively.

For ideal measured criteria and form, full independent steps score 100; a 70%-difficulty step scores 76; the same assisted step scores 38. Lowering does not redefine the reference angles or award a full independent score for easier assisted completion. These weights are explicit experimental choices rather than a clinical severity grade.

The support wording follows the principle of involving carers appropriately and tailoring rehabilitation to the person's needs; see [NICE stroke rehabilitation recommendations](https://www.nice.org.uk/guidance/ng236/chapter/Recommendations). That guidance does not validate this reward or scoring formula.

## Verification

`node --test backend/tests/testing_reach_adaptation.test.cjs`

`python -m pytest backend/tests/test_testing_reach_adaptation.py -q`

Browser integration checks use synthetic, clearly labelled landmark trajectories to exercise support-before-camera, real runner calibration, movement detection, encouragement/retry timing, speech-failure recovery, assisted completion, inherited targets, all four step holds, and the actual score API/results UI. A separate recorded camera feed checks real MediaPipe loading and live arcs. These checks establish software behaviour, not clinical accuracy or patient outcomes.
