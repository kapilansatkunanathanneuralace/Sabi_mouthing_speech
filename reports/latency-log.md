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
