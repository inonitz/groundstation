"""audio/ -- the voice I/O channels: ros2_asr.py (ROS2 transcript subscriber), phone_asr.py
(phone-as-mic REST+TCP inlet, deduped), tts_io.py (TTS outlet: phone /tts, piper/espeak local
fallback). ASR itself is EXTERNAL (asr_node + sttserv); this package starts at "transcript
arrives" and ends at "text spoken"."""
