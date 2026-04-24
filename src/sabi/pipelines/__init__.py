"""Pipelines package (TICKET-011+).

End-to-end wiring that composes ``sabi.capture``, ``sabi.models``,
``sabi.cleanup``, ``sabi.output``, and ``sabi.input`` into user-facing
flows. TICKET-011 ships the silent-dictation PoC; TICKET-012 adds the
audio-dictation flow and TICKET-014 will unify their JSONL streams and
``UtteranceProcessed`` shapes.
"""

from sabi.pipelines.silent_dictate import (
    DEFAULT_CONFIG_PATH as SILENT_DICTATE_DEFAULT_CONFIG_PATH,
)
from sabi.pipelines.silent_dictate import (
    PasteDecision as SilentPasteDecision,
)
from sabi.pipelines.silent_dictate import (
    SilentDictateConfig,
    SilentDictatePipeline,
    load_silent_dictate_config,
    run_silent_dictate,
)
from sabi.pipelines.silent_dictate import (
    UtteranceProcessed as SilentUtteranceProcessed,
)

from sabi.pipelines.audio_dictate import (
    DEFAULT_CONFIG_PATH as AUDIO_DICTATE_DEFAULT_CONFIG_PATH,
)
from sabi.pipelines.audio_dictate import (
    AudioDictateConfig,
    AudioDictatePipeline,
    load_audio_dictate_config,
    run_audio_dictate,
)
from sabi.pipelines.audio_dictate import (
    PasteDecision as AudioPasteDecision,
)
from sabi.pipelines.audio_dictate import (
    TriggerMode,
)
from sabi.pipelines.audio_dictate import (
    UtteranceProcessed as AudioUtteranceProcessed,
)

DEFAULT_CONFIG_PATH = SILENT_DICTATE_DEFAULT_CONFIG_PATH
PasteDecision = SilentPasteDecision
UtteranceProcessed = SilentUtteranceProcessed

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "SILENT_DICTATE_DEFAULT_CONFIG_PATH",
    "AUDIO_DICTATE_DEFAULT_CONFIG_PATH",
    "PasteDecision",
    "SilentPasteDecision",
    "AudioPasteDecision",
    "SilentDictateConfig",
    "SilentDictatePipeline",
    "AudioDictateConfig",
    "AudioDictatePipeline",
    "TriggerMode",
    "UtteranceProcessed",
    "SilentUtteranceProcessed",
    "AudioUtteranceProcessed",
    "load_silent_dictate_config",
    "load_audio_dictate_config",
    "run_silent_dictate",
    "run_audio_dictate",
]
