---
name: teams-realtime-translator
description: Use for planning, implementing, debugging, benchmarking, or reviewing the local Windows Python MS Teams realtime Turkish-English translation project. Prioritize end-to-end latency, full-duplex streaming, WhisperLiveKit UI integration, voice cloning, bounded queues, native Windows execution, and the canonical root Plan.md architecture. Do not use for unrelated repositories.
---

# Teams Realtime Translator

Apply this workflow whenever the skill matches:

1. Read root Plan.md completely before architectural work.
2. Treat DEC-Uxxx user decisions in that Plan as authoritative.
3. Preserve the native Windows and Python-only architecture.
4. Never introduce Docker, containers, or Compose unless the user explicitly
   reverses DEC-U002.
5. Never silently introduce WSL; report Linux-only dependencies as
   excluded/experimental.
6. Reuse and extend WhisperLiveKit's existing web UI as the primary interface.
7. Do not introduce Piper as a selected, default, or planned TTS.
8. Keep ASR, MT, and TTS behind narrow, testable adapters.
9. Keep audio callbacks non-blocking and free of inference, disk, database, and
   network work.
10. Use bounded queues/ring buffers only; never add an unbounded asyncio.Queue.
11. Preserve replaceable Partial versus append-only Committed semantics.
12. Never send unstable or Partial text to TTS.
13. Measure actual speech-to-output end-to-end latency, not only model inference.
14. Treat the RTX 5060 Ti 16 GB VRAM budget as a hard shared constraint.
15. Share model weights across sessions when supported; avoid duplicate GPU loads.
16. Keep SQLite writes and reads outside latency-critical audio callbacks.
17. Never silently download model weights at startup, tests, or runtime.
18. Respect the deterministic models/ layout and pinned model manifest in the Plan.
19. Reuse approved externally stored models via configurable absolute paths;
    never copy them merely to fit the repository layout.
20. Add task-relevant unit, integration, hardware, and benchmark coverage when
    implementation begins.
21. Update root Plan.md when an architectural decision or proven runtime finding changes.
22. Add or update DEC/REF traceability when modifying architectural decisions.
23. Never silently contradict a DEC-Uxxx decision, even if historical research
    recommends otherwise.
24. Stop implementation and report the exact conflict when work would require
    violating a hard architecture decision.
25. Prefer WASAPI for Windows audio endpoints, especially speaker loopback and
    render. Permit another native Windows host API for a specific physical mic
    only after recorded format/signal evidence shows its WASAPI path is unusable;
    persist the measured endpoint fingerprint and retain WASAPI loopback.
26. Diagnose capture with saved WAV evidence plus frame-level RMS/peak, active
    duration, callback counts, discontinuities, and errors. An opened stream or
    endpoint name alone is not proof of signal.
27. For isolated speaker-loopback verification, render a known tone to the
    matching physical output while capturing its WASAPI loopback, then verify
    duration and dominant frequency. Keep this distinct from the Teams routing
    and full-duplex acceptance gates.
28. A full-window ASR backend must not decode on every audio frame. Coalesce
    replaceable partial inference to a measured bounded cadence, then run one
    final decode over the complete buffered utterance at the VAD endpoint.
29. Never erase current utterance audio merely because one replaceable partial
    fails confidence or hallucination checks. Record the rejection and allow a
    later hypothesis to repair it; reset only on final rejection or overload.
30. Never claim cloned/routed speech in UI history at MT completion. Append the
    durable outgoing history item only after first TTS PCM has entered the
    bounded render path; this still does not claim Teams remote receipt.
31. Normalize Turkish capital dotted-I before matching hallucination patterns.
    Add a regression using the exact correctly-cased phrase whenever a Turkish
    denylist item is introduced.

Before editing, inspect the current implementation and dirty worktree. During
review, reject growing backlog, committed reordering/loss, false Ready states,
non-localhost exposure, or unmeasured claims labeled as measured. Do not begin a
later phase unless the current user task authorizes it.
