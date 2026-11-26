# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Offline export of the attributed, privacy-clean sample plate (CC BY-NC-SA)."""
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile
import io

SAMPLE_NAME = 'Filament-Swatch-Beispielplatte.3mf'
ASSETS = Path(__file__).resolve().parent/'sample-assets'
# Updated only when the reviewed built-in asset changes.
SAMPLE_SHA256 = '7cf538399e5a25cdd2babcba7efdd3513033634b476d32737578769b74a5070b'


def sample_bytes():
    data = (ASSETS/SAMPLE_NAME).read_bytes()
    if hashlib.sha256(data).hexdigest() != SAMPLE_SHA256:
        raise ValueError('Die eingebaute Beispielplatte ist beschädigt. App-Paket erneut entpacken.')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None or not {'3D/3dmodel.model','Metadata/ATTRIBUTION.txt'} <= set(archive.namelist()):
            raise ValueError('Die eingebaute Beispielplatte ist unvollständig.')
    return data


def export_swatch(destination):
    """Export the built-in 3MF atomically; never read private source projects."""
    target = Path(destination).expanduser()
    if target.suffix.casefold() != '.3mf':
        raise ValueError('Die Beispielplatte bitte mit der Dateiendung .3mf speichern.')
    if target.resolve() == (ASSETS/SAMPLE_NAME).resolve():
        raise ValueError('Bitte einen eigenen Speicherort außerhalb der eingebauten Beispielplatte wählen.')
    data = sample_bytes()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.cfs-swatch-',suffix='.tmp',delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,target)
        temporary = None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return target
