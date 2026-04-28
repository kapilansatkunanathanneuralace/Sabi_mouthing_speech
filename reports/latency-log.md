# Latency log

Append one row per pipeline run (see tickets/README.md).

| ticket | hardware | stage | p50_ms | p95_ms | samples | notes |
| --- | --- | --- | --- | --- | --- | --- |
| TICKET-005 | cpu | vsr-smoke | 1538.4 | - | 157 | video=hello_world.mp4 fps=29.7 |
| TICKET-005 | cpu | vsr-smoke | 1601.1 | - | 157 | video=hello_world.mp4 fps=29.7 |
| TICKET-005 | cuda | vsr-smoke | 1721.4 | - | 157 | video=hello_world.mp4 fps=29.7 |
| TICKET-005 | cuda | vsr-smoke | 1367.2 | - | 157 | video=hello_world.mp4 fps=29.7 |
| TICKET-007 | cuda | asr | 6506.4 | - | 79856 | wav=hello_world.wav lang=en cp=int8_float16 conf=0.57 |
| TICKET-008 | fallback | cleanup | 0.0 | - | 29 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=True reason=ollama_unavailable |
| TICKET-008 | fallback | cleanup | 812.7 | - | 29 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=True reason=http_error: ReadTimeout |
| TICKET-008 | ollama | cleanup | 306.8 | - | 29 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=False |
| TICKET-008 | ollama | cleanup | 416.3 | - | 52 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=False |
| TICKET-008 | ollama | cleanup | 297.5 | - | 51 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=False |
| TICKET-008 | ollama | cleanup | 284.6 | - | 48 | model=llama3.2:3b-instruct-q4_K_M source=asr fallback=False |
| TICKET-009 | windows | inject | 27.8 | - | 36 | dry_run=True paste_delay_ms=15 restore_delay_ms=400 |
| TICKET-009 | windows | inject | 265.9 | - | 11 | dry_run=False paste_delay_ms=15 restore_delay_ms=400 |
| TICKET-011 | windows | pipeline | 14180.5 | - | 1 | decision=dry_run frames=146 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1991 cap=4928 roi=1314 vsr=1830 clean=801 inject=0] |
| TICKET-011 | windows | pipeline | 5319.2 | - | 1 | decision=withheld_low_confidence frames=28 face_ratio=1.00 confidence=0.00 device=cuda:0 fallback=False [open=1680 cap=962 roi=285 vsr=803 clean=0 inject=0] |
| TICKET-011 | windows | pipeline | 3863.4 | - | 1 | decision=dry_run frames=12 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1668 cap=416 roi=110 vsr=645 clean=806 inject=0] |
| TICKET-011 | windows | pipeline | 4348.6 | - | 1 | decision=dry_run frames=26 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1654 cap=897 roi=236 vsr=648 clean=802 inject=0] |
| TICKET-011 | windows | pipeline | 6836.7 | - | 1 | decision=dry_run frames=93 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1698 cap=3137 roi=793 vsr=867 clean=805 inject=0] |
| TICKET-012 | windows | pipeline | 3938.0 | - | 1 | mode=push_to_talk decision=withheld_silence confidence=0.00 compute_type=int8_float16 device=cuda fallback=False [open=288 warm=309 cap=3960 asr=0 clean=0 inject=0] |
| TICKET-012 | windows | pipeline | 5823.4 | - | 1 | mode=push_to_talk decision=pasted confidence=0.53 compute_type=int8_float16 device=cuda fallback=True [open=0 warm=0 cap=4640 asr=151 clean=804 inject=215] |
| TICKET-012 | windows | pipeline | 7493.6 | - | 1 | mode=push_to_talk decision=pasted confidence=0.58 compute_type=int8_float16 device=cuda fallback=True [open=0 warm=0 cap=6400 asr=169 clean=802 inject=137] |
| TICKET-011 | windows | pipeline | 65203.5 | - | 1 | decision=dry_run frames=1 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1856 cap=0 roi=10 vsr=617 clean=802 inject=0] |
| TICKET-011 | windows | pipeline | 8889.9 | - | 1 | decision=dry_run frames=1 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=5100 cap=0 roi=11 vsr=560 clean=805 inject=0] |
| TICKET-011 | windows | pipeline | 8360.6 | - | 1 | decision=dry_run frames=60 face_ratio=1.00 confidence=1.00 device=cuda:0 fallback=True [open=1753 cap=2001 roi=519 vsr=1263 clean=813 inject=0] |
| TICKET-012 | windows | pipeline | 3226.6 | - | 1 | mode=push_to_talk decision=dry_run confidence=0.58 compute_type=int8_float16 device=cuda fallback=True [open=1052 warm=222 cap=2280 asr=102 clean=805 inject=0] |
| TICKET-012 | windows | pipeline | 4391.1 | - | 1 | mode=push_to_talk decision=dry_run confidence=0.72 compute_type=int8_float16 device=cuda fallback=True [open=0 warm=0 cap=3440 asr=115 clean=803 inject=0] |
| TICKET-012 | windows | pipeline | 2767.5 | - | 1 | mode=push_to_talk decision=dry_run confidence=0.71 compute_type=int8_float16 device=cuda fallback=True [open=262 warm=210 cap=1880 asr=99 clean=803 inject=0] |
| TICKET-008 | fallback | cleanup | 808.4 | - | 48 | model=llama3.2:3b-instruct-q4_K_M prompt_version=v2 source=asr fallback=True reason=http_error: ReadTimeout |
| TICKET-008 | fallback | cleanup | 805.9 | - | 48 | model=llama3.2:3b-instruct-q4_K_M prompt_version=v2 source=asr fallback=True reason=http_error: ReadTimeout |
| TICKET-008 | ollama | cleanup | 3089.9 | - | 48 | model=llama3.2:3b-instruct-q4_K_M prompt_version=v2 source=asr fallback=False |
| TICKET-008 | ollama | cleanup | 160.9 | - | 48 | model=llama3.2:3b-instruct-q4_K_M prompt_version=v2 source=asr fallback=False |
| TICKET-017 | windows | pipeline | 10166.1 | - | 1 | decision=dry_run confidence=0.96 fusion=auto -> audio_primary prompt=v1 fallback=False [cap=1035 roi=348 vsr=1725 asr=112 fusion=0.0 clean=233 inject=0] |
| TICKET-017 | windows | pipeline | 2874.9 | - | 1 | decision=error confidence=0.00 fusion=- prompt=v1 fallback=False [cap=210 roi=61 vsr=0 asr=0 fusion=0.0 clean=0 inject=0] error=neither modality captured input |
| TICKET-017 | windows | pipeline | 4179.6 | - | 1 | decision=dry_run confidence=0.96 fusion=auto -> audio_primary prompt=v1 fallback=False [cap=1137 roi=288 vsr=836 asr=194 fusion=0.0 clean=170 inject=0] |
| TICKET-017 | windows | pipeline | 5353.9 | - | 1 | decision=dry_run confidence=1.00 fusion=alignment_below_threshold prompt=v1 fallback=False [cap=2210 roi=559 vsr=1002 asr=255 fusion=0.0 clean=147 inject=0] |
| TICKET-017 | windows | pipeline | 5734.7 | - | 1 | decision=dry_run confidence=1.00 fusion=asr silent prompt=v1 fallback=False [cap=2580 roi=645 vsr=896 asr=0 fusion=0.0 clean=179 inject=0] |
| TICKET-017 | windows | pipeline | 5240.9 | - | 1 | decision=dry_run confidence=1.00 fusion=asr silent prompt=v1 fallback=False [cap=2273 roi=583 vsr=729 asr=0 fusion=0.0 clean=158 inject=0] |
| TICKET-014 | windows | fused:asr_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=asr_ms |
| TICKET-014 | windows | fused:capture_ms | 998.9 | 998.9 | 1 | pipeline=fused stage=capture_ms |
| TICKET-014 | windows | fused:capture_open_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=capture_open_ms |
| TICKET-014 | windows | fused:cleanup_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=cleanup_ms |
| TICKET-014 | windows | fused:fusion_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=fusion_ms |
| TICKET-014 | windows | fused:inject_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=inject_ms |
| TICKET-014 | windows | fused:mic_open_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=mic_open_ms |
| TICKET-014 | windows | fused:roi_ms | 91.3 | 91.3 | 1 | pipeline=fused stage=roi_ms |
| TICKET-014 | windows | fused:total_ms | 294.6 | 294.6 | 1 | pipeline=fused stage=total_ms |
| TICKET-014 | windows | fused:vsr_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=vsr_ms |
| TICKET-014 | windows | fused:warmup_ms | 0.0 | 0.0 | 1 | pipeline=fused stage=warmup_ms |
| TICKET-014 | windows | fused:asr_ms | 125.2 | 139.3 | 20 | pipeline=fused stage=asr_ms |
| TICKET-014 | windows | fused:capture_ms | 3999.4 | 3999.4 | 20 | pipeline=fused stage=capture_ms |
| TICKET-014 | windows | fused:capture_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=capture_open_ms |
| TICKET-014 | windows | fused:cleanup_ms | 809.0 | 815.4 | 20 | pipeline=fused stage=cleanup_ms |
| TICKET-014 | windows | fused:fusion_ms | 0.0 | 0.1 | 20 | pipeline=fused stage=fusion_ms |
| TICKET-014 | windows | fused:inject_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=inject_ms |
| TICKET-014 | windows | fused:mic_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=mic_open_ms |
| TICKET-014 | windows | fused:roi_ms | 1001.9 | 1049.5 | 20 | pipeline=fused stage=roi_ms |
| TICKET-014 | windows | fused:total_ms | 6001.4 | 6726.9 | 20 | pipeline=fused stage=total_ms |
| TICKET-014 | windows | fused:vsr_ms | 1245.1 | 1536.9 | 20 | pipeline=fused stage=vsr_ms |
| TICKET-014 | windows | fused:warmup_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=warmup_ms |
| TICKET-014 | windows | fused:asr_ms | 304.2 | 324.9 | 20 | pipeline=fused stage=asr_ms |
| TICKET-014 | windows | fused:capture_ms | 3999.4 | 3999.4 | 20 | pipeline=fused stage=capture_ms |
| TICKET-014 | windows | fused:capture_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=capture_open_ms |
| TICKET-014 | windows | fused:cleanup_ms | 804.6 | 814.4 | 20 | pipeline=fused stage=cleanup_ms |
| TICKET-014 | windows | fused:fusion_ms | 0.1 | 0.1 | 20 | pipeline=fused stage=fusion_ms |
| TICKET-014 | windows | fused:inject_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=inject_ms |
| TICKET-014 | windows | fused:mic_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=mic_open_ms |
| TICKET-014 | windows | fused:roi_ms | 2069.2 | 2197.6 | 20 | pipeline=fused stage=roi_ms |
| TICKET-014 | windows | fused:total_ms | 12018.0 | 14463.0 | 20 | pipeline=fused stage=total_ms |
| TICKET-014 | windows | fused:vsr_ms | 3843.7 | 4872.5 | 20 | pipeline=fused stage=vsr_ms |
| TICKET-014 | windows | fused:warmup_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=warmup_ms |
| TICKET-008 | ollama | cleanup | 5192.5 | - | 11 | model=llama3.2:3b-instruct-q4_K_M prompt_version=v1 source=asr fallback=False |
| TICKET-014 | windows | fused:asr_ms | 3730.7 | 3820.9 | 20 | pipeline=fused stage=asr_ms |
| TICKET-014 | windows | fused:capture_ms | 3999.4 | 3999.4 | 20 | pipeline=fused stage=capture_ms |
| TICKET-014 | windows | fused:capture_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=capture_open_ms |
| TICKET-014 | windows | fused:cleanup_ms | 552.8 | 650.7 | 20 | pipeline=fused stage=cleanup_ms |
| TICKET-014 | windows | fused:fusion_ms | 0.1 | 0.2 | 20 | pipeline=fused stage=fusion_ms |
| TICKET-014 | windows | fused:inject_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=inject_ms |
| TICKET-014 | windows | fused:mic_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=mic_open_ms |
| TICKET-014 | windows | fused:roi_ms | 3318.1 | 3377.8 | 20 | pipeline=fused stage=roi_ms |
| TICKET-014 | windows | fused:total_ms | 31381.9 | 35279.8 | 20 | pipeline=fused stage=total_ms |
| TICKET-014 | windows | fused:vsr_ms | 16016.9 | 19735.4 | 20 | pipeline=fused stage=vsr_ms |
| TICKET-014 | windows | fused:warmup_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=warmup_ms |
| TICKET-014 | windows | fused:asr_ms | 119.7 | 129.1 | 20 | pipeline=fused stage=asr_ms |
| TICKET-014 | windows | fused:capture_ms | 3999.4 | 3999.4 | 20 | pipeline=fused stage=capture_ms |
| TICKET-014 | windows | fused:capture_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=capture_open_ms |
| TICKET-014 | windows | fused:cleanup_ms | 197.1 | 231.4 | 20 | pipeline=fused stage=cleanup_ms |
| TICKET-014 | windows | fused:fusion_ms | 0.0 | 0.1 | 20 | pipeline=fused stage=fusion_ms |
| TICKET-014 | windows | fused:inject_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=inject_ms |
| TICKET-014 | windows | fused:mic_open_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=mic_open_ms |
| TICKET-014 | windows | fused:roi_ms | 994.2 | 1009.9 | 20 | pipeline=fused stage=roi_ms |
| TICKET-014 | windows | fused:total_ms | 5339.5 | 5614.9 | 20 | pipeline=fused stage=total_ms |
| TICKET-014 | windows | fused:vsr_ms | 1260.6 | 1446.5 | 20 | pipeline=fused stage=vsr_ms |
| TICKET-014 | windows | fused:warmup_ms | 0.0 | 0.0 | 20 | pipeline=fused stage=warmup_ms |
| TICKET-017 | windows | pipeline | 13888.0 | - | 1 | decision=dry_run confidence=0.56 fusion=alignment_below_threshold prompt=v1 fallback=True [cap=5134 roi=1516 vsr=2595 asr=165 fusion=0.1 clean=803 inject=0] |
| TICKET-017 | windows | pipeline | 7128.5 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=3025 roi=872 vsr=1105 asr=0 fusion=0.0 clean=807 inject=0] |
| TICKET-017 | windows | pipeline | 7941.7 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=3969 roi=1071 vsr=1141 asr=0 fusion=0.0 clean=807 inject=0] |
| TICKET-017 | windows | pipeline | 11029.3 | - | 1 | decision=dry_run confidence=0.80 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=5795 roi=1600 vsr=2309 asr=321 fusion=0.1 clean=816 inject=0] |
| TICKET-017 | windows | pipeline | 13265.3 | - | 1 | decision=dry_run confidence=0.59 fusion=alignment_below_threshold prompt=v1 fallback=True [cap=7794 roi=2196 vsr=2562 asr=337 fusion=0.1 clean=807 inject=0] |
| TICKET-017 | windows | pipeline | 6184.4 | - | 1 | decision=dry_run confidence=0.91 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=2224 roi=615 vsr=1131 asr=172 fusion=0.0 clean=813 inject=0] |
| TICKET-017 | windows | pipeline | 9414.8 | - | 1 | decision=dry_run confidence=0.93 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=5188 roi=1456 vsr=1383 asr=228 fusion=0.0 clean=808 inject=0] |
| TICKET-017 | windows | pipeline | 10105.7 | - | 1 | decision=dry_run confidence=0.81 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=5376 roi=1498 vsr=1907 asr=253 fusion=0.1 clean=819 inject=0] |
| TICKET-017 | windows | pipeline | 9574.3 | - | 1 | decision=dry_run confidence=0.88 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=5010 roi=1398 vsr=1751 asr=267 fusion=0.1 clean=810 inject=0] |
| TICKET-017 | windows | pipeline | 13125.8 | - | 1 | decision=dry_run confidence=0.59 fusion=alignment_below_threshold prompt=v1 fallback=True [cap=4218 roi=1310 vsr=2200 asr=163 fusion=0.1 clean=806 inject=0] |
| TICKET-017 | windows | pipeline | 8547.0 | - | 1 | decision=dry_run confidence=0.86 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=3905 roi=1189 vsr=1610 asr=275 fusion=0.1 clean=806 inject=0] |
| TICKET-017 | windows | pipeline | 7192.3 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=2941 roi=929 vsr=1297 asr=0 fusion=0.0 clean=805 inject=0] |
| TICKET-017 | windows | pipeline | 8021.0 | - | 1 | decision=dry_run confidence=1.00 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=3728 roi=1167 vsr=1300 asr=250 fusion=0.0 clean=814 inject=0] |
| TICKET-017 | windows | pipeline | 12440.9 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=3217 roi=952 vsr=2238 asr=0 fusion=0.0 clean=807 inject=0] |
| TICKET-017 | windows | pipeline | 10458.0 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=5901 roi=1766 vsr=1551 asr=0 fusion=0.0 clean=805 inject=0] |
| TICKET-017 | windows | pipeline | 7407.4 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=3362 roi=1067 vsr=1086 asr=0 fusion=0.0 clean=816 inject=0] |
| TICKET-017 | windows | pipeline | 7780.8 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=2976 roi=989 vsr=1700 asr=0 fusion=0.0 clean=818 inject=0] |
| TICKET-017 | windows | pipeline | 8126.4 | - | 1 | decision=dry_run confidence=0.86 fusion=auto -> audio_primary prompt=v1 fallback=True [cap=3699 roi=1093 vsr=1491 asr=217 fusion=0.1 clean=803 inject=0] |
| TICKET-017 | windows | pipeline | 6367.2 | - | 1 | decision=dry_run confidence=0.85 fusion=asr silent prompt=v1 fallback=True [cap=2338 roi=684 vsr=1134 asr=0 fusion=0.0 clean=802 inject=0] |
