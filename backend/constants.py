# -*- coding: UTF-8 -*-

import enum


class AsrTaskStatus(enum.Enum):
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
