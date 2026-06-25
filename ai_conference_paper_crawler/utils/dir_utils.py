#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Date    : Dec-16-20 16:22
# @Author  : Kan Huang (kan.huang@connect.ust.hk)

import os
import errno
import six


def makedir_exist_ok(dirpath):
    """makedir_exist_ok compatible for both Python 2 and Python 3
    """
    if six.PY3:
        os.makedirs(
            dirpath, exist_ok=True)  # pylint: disable=unexpected-keyword-arg
    else:
        # Python 2 doesn't have the exist_ok arg, so we try-except here.
        try:
            os.makedirs(dirpath)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
