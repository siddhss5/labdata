"""
Export utilities for sslabdata.

Serializes LabData to YAML or JSON files.

Copyright (c) 2024 Personal Robotics Laboratory, University of Washington
Author: Siddhartha Srinivasa <siddh@cs.washington.edu>
MIT License - see LICENSE file for details.
"""

import json
import os
import shutil
import uuid
import yaml
from pathlib import Path

from .models import LabData


def _write(output_path: str, text: str) -> None:
    """Write a serialized document, after it has been serialized.

    The document is built in full before anything is created, so a document
    sslabdata refuses to emit -- one whose `source.file` is absolute, say --
    leaves no file behind. It is then written in full to a temporary sibling
    and moved over the destination in one step, so a failure at any point
    leaves an existing file as it was, creates none where there was none, and
    leaves no temporary file behind.
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp = output_file.with_name(f".{output_file.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temp, 'x', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if output_file.exists():
            shutil.copymode(output_file, temp)
        os.replace(temp, output_file)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def export_to_yaml(data: LabData, output_path: str):
    """Export LabData to a YAML file.

    Args:
        data: Assembled LabData instance
        output_path: Path to output YAML file
    """
    _write(output_path,
           yaml.dump(data.to_dict(), default_flow_style=False,
                     allow_unicode=True, sort_keys=False))


def export_to_json(data: LabData, output_path: str, indent: int = 2):
    """Export LabData to a JSON file.

    Args:
        data: Assembled LabData instance
        output_path: Path to output JSON file
        indent: Indentation level for pretty printing
    """
    _write(output_path,
           json.dumps(data.to_dict(), indent=indent, ensure_ascii=False))
