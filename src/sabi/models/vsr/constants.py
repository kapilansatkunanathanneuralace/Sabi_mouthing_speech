"""Shared VSR constants (TICKET-005).

Single source of truth for TICKET-004 (lip ROI producer), TICKET-005 (this
wrapper), and TICKET-011 (pipeline). Changing these requires re-verifying the
Chaplin pre-processing pipeline in ``third_party/chaplin/pipelines/data/transforms.py``.
"""

from __future__ import annotations

# Auto-AVSR / LRS3 lip crop contract emitted by :class:`sabi.capture.lip_roi.LipROIDetector`.
LIP_H = 96
LIP_W = 96

# Chaplin applies a center crop of this side after rescaling to [0, 1]
# (see third_party/chaplin/pipelines/data/transforms.py::VideoTransform).
CENTER_CROP = 88

# LRS3 grayscale lip-roi normalisation statistics (mean, std) used by Chaplin.
LRS3_MEAN = 0.421
LRS3_STD = 0.165

# Chaplin trains and infers at 25 fps video; the pipeline re-indexes frames when
# the input fps differs (VideoTransform's linspace branch).
TARGET_V_FPS = 25
