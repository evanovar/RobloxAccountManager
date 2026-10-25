from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import zlib

from features.theme_model import ThemeError


MAX_MEDIA_BYTES = 250 * 1024 * 1024
MEDIA_EXTENSIONS = {'.gif', '.mov', '.jpg', '.avi', '.webp', '.mp4', '.bmp', '.png', '.mkv', '.webm', '.jpeg'}
_CHUNK_BYTES = 1024 * 1024
_MAX_CONTAINER_NODES = 1000000
_MAX_CONTAINER_DEPTH = 16
_MAX_PNG_DECODED_BYTES = 256 * 1024 * 1024
_JPEG_SCAN_MARKER = re.compile(b'\xff[^\x00\xff\xd0-\xd7]')


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError('The media container is incomplete or structurally invalid.')


def _read(source, length: int, end: int) -> bytes:
    _require(0 <= length <= end - source.tell())
    data = source.read(length)
    _require(len(data) == length)
    return data


def _skip(source, length: int, end: int) -> None:
    _require(0 <= length <= end - source.tell())
    source.seek(length, os.SEEK_CUR)


def _node(budget: list[int]) -> None:
    budget[0] -= 1
    _require(budget[0] >= 0)


def _inflate_png(decoder, data: bytes, decoded: int, expected: int) -> int:
    if decoder.eof:
        return decoded
    while data:
        output = decoder.decompress(data, min(_CHUNK_BYTES, expected - decoded + 1))
        decoded += len(output)
        _require(decoded <= expected)
        if decoder.eof:
            return decoded
        tail = decoder.unconsumed_tail
        _require(not tail or len(tail) < len(data) or bool(output))
        data = tail
    return decoded


def _valid_png_chunks(path: Path, size: int) -> bool:
    decoder = zlib.decompressobj()
    decoded = 0
    budget = [_MAX_CONTAINER_NODES]
    with path.open('rb') as source:
        source.seek(16)
        width, height, bits, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', _read(source, 13, size))
        depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
        _require(width > 0 and height > 0 and bits in depths.get(color, set()) and
                 compression == filtering == 0 and interlace in (0, 1))
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
        passes = ((0, 0, 1, 1),) if not interlace else (
            (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
            (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
        )
        expected = 0
        for x, y, dx, dy in passes:
            columns, rows = max(0, (width - x + dx - 1) // dx), max(0, (height - y + dy - 1) // dy)
            if columns and rows:
                expected += rows * (1 + (columns * channels * bits + 7) // 8)
        _require(expected <= _MAX_PNG_DECODED_BYTES)
        source.seek(8)
        while source.tell() + 12 <= size:
            _node(budget)
            first = source.tell() == 8
            length = int.from_bytes(source.read(4), 'big')
            kind = source.read(4)
            _require(length <= size - source.tell() - 4 and (kind == b'IHDR') == first)
            crc = zlib.crc32(kind)
            remaining = length
            while remaining:
                chunk = _read(source, min(_CHUNK_BYTES, remaining), size)
                crc = zlib.crc32(chunk, crc)
                if kind == b'IDAT':
                    decoded = _inflate_png(decoder, chunk, decoded, expected)
                remaining -= len(chunk)
            _require(int.from_bytes(_read(source, 4, size), 'big') == crc)
            if kind == b'IEND':
                return length == 0 and decoder.eof and decoded == expected and source.tell() == size
    return False


def _gif_subblocks(source, end: int, budget: list[int]) -> int:
    total = 0
    while True:
        _node(budget)
        length = _read(source, 1, end)[0]
        if not length:
            return total
        _skip(source, length, end)
        total += length


def _valid_gif(path: Path, size: int) -> bool:
    budget = [_MAX_CONTAINER_NODES]
    saw_image = False
    with path.open('rb') as source:
        header = _read(source, 13, size)
        width, height = struct.unpack('<HH', header[6:10])
        _require(header[:6] in (b'GIF87a', b'GIF89a') and width > 0 and height > 0)
        global_table = bool(header[10] & 0x80)
        if global_table:
            _skip(source, 3 * (2 << (header[10] & 7)), size)
        while source.tell() < size:
            _node(budget)
            kind = _read(source, 1, size)
            if kind == b';':
                return saw_image and source.tell() == size
            if kind == b'!':
                _read(source, 1, size)
                _gif_subblocks(source, size, budget)
            elif kind == b',':
                descriptor = _read(source, 9, size)
                left, top, columns, rows, flags = struct.unpack('<HHHHB', descriptor)
                _require(columns > 0 and rows > 0 and left + columns <= width and top + rows <= height)
                _require(global_table or flags & 0x80)
                if flags & 0x80:
                    _skip(source, 3 * (2 << (flags & 7)), size)
                _require(2 <= _read(source, 1, size)[0] <= 8)
                _require(_gif_subblocks(source, size, budget) > 0)
                saw_image = True
            else:
                return False
    return False


def _valid_jpeg(path: Path, size: int) -> bool:
    frame = scan = False
    budget = [_MAX_CONTAINER_NODES]
    with path.open('rb') as source:
        _require(_read(source, 2, size) == b'\xff\xd8')
        while source.tell() < size:
            _node(budget)
            _require(_read(source, 1, size) == b'\xff')
            marker = _read(source, 1, size)[0]
            while marker == 0xff:
                _node(budget)
                marker = _read(source, 1, size)[0]
            if marker == 0xd9:
                return frame and scan and source.tell() == size
            _require(marker not in (0, 0xd8) and not 0xd0 <= marker <= 0xd7)
            length = int.from_bytes(_read(source, 2, size), 'big')
            _require(length >= 2)
            payload = _read(source, length - 2, size)
            if marker in {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}:
                _require(len(payload) >= 6 and len(payload) == 6 + 3 * payload[5] and payload[5] > 0 and
                         int.from_bytes(payload[1:3], 'big') > 0 and int.from_bytes(payload[3:5], 'big') > 0)
                frame = True
            if marker == 0xda:
                _require(frame and len(payload) >= 4 and payload[0] > 0 and len(payload) == 4 + 2 * payload[0])
                entropy = False
                while source.tell() < size:
                    start = source.tell()
                    chunk = source.read(min(65536, size - start))
                    found = _JPEG_SCAN_MARKER.search(chunk)
                    if found:
                        entropy |= bool(chunk[:found.start()].strip(b'\xff'))
                        source.seek(start + found.start())
                        break
                    if chunk.endswith(b'\xff'):
                        _require(len(chunk) > 1)
                        source.seek(-1, os.SEEK_CUR)
                    entropy |= bool(chunk.strip(b'\xff'))
                _require(entropy)
                scan = True
    return False


def _valid_bmp(header: bytes, size: int) -> bool:
    _require(len(header) >= 26 and header[:2] == b'BM' and int.from_bytes(header[2:6], 'little') == size)
    dib = int.from_bytes(header[14:18], 'little')
    offset = int.from_bytes(header[10:14], 'little')
    _require(dib in {12, 16, 40, 52, 56, 64, 108, 124} and 14 + dib <= offset < size)
    if dib == 12:
        width, height, planes, bits = struct.unpack('<HHHH', header[18:26])
        compression = 0
    else:
        _require(len(header) >= 14 + dib)
        width, height, planes, bits = struct.unpack('<iiHH', header[18:30])
        compression = int.from_bytes(header[30:34], 'little') if dib >= 40 else 0
    _require(width > 0 and height != 0 and planes == 1 and bits in (1, 4, 8, 16, 24, 32))
    if compression in (0, 3, 6):
        return ((width * bits + 31) // 32) * 4 * abs(height) <= size - offset
    return compression in (1, 2, 4, 5) and size - offset > 2


def _riff_entries(source, start: int, end: int, budget: list[int]):
    position = start
    while position < end:
        _node(budget)
        source.seek(position)
        kind, length = struct.unpack('<4sI', _read(source, 8, end))
        payload = position + 8
        following = payload + length + length % 2
        _require(following <= end)
        yield kind, payload, length
        position = following


def _webp_frame(source, kind: bytes, position: int, length: int) -> bool:
    source.seek(position)
    if kind == b'VP8 ':
        header = _read(source, min(length, 10), position + length)
        return (length > 10 and not header[0] & 1 and header[3:6] == b'\x9d\x01\x2a' and
                int.from_bytes(header[6:8], 'little') & 0x3fff > 0 and
                int.from_bytes(header[8:10], 'little') & 0x3fff > 0)
    if kind == b'VP8L':
        header = _read(source, min(length, 5), position + length)
        return length > 5 and header[0] == 0x2f and not int.from_bytes(header[1:5], 'little') >> 29
    return False


def _valid_riff(path: Path, size: int, extension: str) -> bool:
    budget = [_MAX_CONTAINER_NODES]
    video_stream = frame = False
    with path.open('rb') as source:
        if extension == '.webp':
            header = _read(source, 12, size)
            _require(header[:4] == b'RIFF' and header[8:] == b'WEBP' and
                     int.from_bytes(header[4:8], 'little') + 8 == size)
            for kind, position, length in _riff_entries(source, 12, size, budget):
                if kind == b'ANMF':
                    _require(length >= 16)
                    for subkind, subposition, sublength in _riff_entries(source, position + 16, position + length, budget):
                        frame |= _webp_frame(source, subkind, subposition, sublength)
                else:
                    frame |= _webp_frame(source, kind, position, length)
            return frame

        def walk(start, end, depth=0, movie=False):
            nonlocal video_stream, frame
            _require(depth <= _MAX_CONTAINER_DEPTH)
            for kind, position, length in _riff_entries(source, start, end, budget):
                if kind == b'LIST':
                    source.seek(position)
                    list_type = _read(source, 4, position + length)
                    walk(position + 4, position + length, depth + 1, movie or list_type == b'movi')
                elif kind == b'strh':
                    source.seek(position)
                    _require(length >= 48)
                    video_stream |= _read(source, 4, position + length) == b'vids'
                elif movie and kind[2:] in (b'dc', b'db') and kind[:2].isdigit():
                    frame |= length > 0

        position = 0
        while position < size:
            _node(budget)
            source.seek(position)
            header = _read(source, 12, size)
            end = position + 8 + int.from_bytes(header[4:8], 'little')
            _require(header[:4] == b'RIFF' and header[8:] == (b'AVI ' if position == 0 else b'AVIX') and
                     position + 12 <= end <= size)
            walk(position + 12, end)
            position = end + end % 2
        return position == size and video_stream and frame


def _atom_entries(source, start: int, end: int, budget: list[int]):
    position = start
    while position < end:
        _node(budget)
        source.seek(position)
        length, kind = struct.unpack('>I4s', _read(source, 8, end))
        header_size = 8
        if length == 1:
            length = int.from_bytes(_read(source, 8, end), 'big')
            header_size = 16
        elif length == 0:
            length = end - position
        _require(header_size <= length <= end - position)
        yield kind, position + header_size, length - header_size
        position += length


def _valid_bmff(path: Path, size: int, extension: str) -> bool:
    budget = [_MAX_CONTAINER_NODES]
    video_track = media_data = movie = file_type = False
    containers = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'moof', b'traf', b'mvex', b'edts', b'dinf'}
    with path.open('rb') as source:
        def walk(start, end, parents=()):
            nonlocal video_track, media_data, movie, file_type
            depth = len(parents)
            _require(depth <= _MAX_CONTAINER_DEPTH)
            for kind, position, length in _atom_entries(source, start, end, budget):
                if kind == b'ftyp' and depth == 0:
                    source.seek(position)
                    _require(length >= 8 and length % 4 == 0)
                    file_type = True
                if kind == b'mdat' and depth == 0:
                    media_data |= length > 0
                if kind == b'hdlr' and parents[-3:] == (b'moov', b'trak', b'mdia'):
                    source.seek(position)
                    _require(length >= 12)
                    video_track |= _read(source, 12, position + length)[8:12] == b'vide'
                if kind in containers:
                    movie |= kind == b'moov' and depth == 0
                    walk(position, position + length, parents + (kind,))
        walk(0, size)
    return movie and media_data and video_track and (file_type or extension == '.mov')


def _ebml_vint(source, end: int, identifier=False):
    first = _read(source, 1, end)[0]
    _require(first > 0)
    width = 9 - first.bit_length()
    _require(width <= (4 if identifier else 8))
    value = first if identifier else first & ((1 << (8 - width)) - 1)
    for byte in _read(source, width - 1, end):
        value = value * 256 + byte
    return None if not identifier and value == (1 << (7 * width)) - 1 else value


def _unknown_cluster_end(source, start: int, end: int, budget: list[int]) -> int:
    # Step over complete child elements so frame payload bytes cannot become boundaries
    segment_children = {0x114d9b74, 0x1549a966, 0x1654ae6b, 0x1f43b675,
                        0x1c53bb6b, 0x1941a469, 0x1043a770, 0x1254c367, 0x18538067}
    position = start
    while position < end:
        _node(budget)
        source.seek(position)
        kind = _ebml_vint(source, end, True)
        if kind in segment_children:
            return position
        length = _ebml_vint(source, end)
        _require(length is not None and length <= end - source.tell())
        position = source.tell() + length
    return end


def _ebml_entries(source, start: int, end: int, budget: list[int]):
    position = start
    while position < end:
        _node(budget)
        source.seek(position)
        kind = _ebml_vint(source, end, True)
        length = _ebml_vint(source, end)
        payload = source.tell()
        if length is None:
            _require(kind in (0x18538067, 0x1f43b675))
            following = _unknown_cluster_end(source, payload, end, budget) if kind == 0x1f43b675 else end
            length = following - payload
        _require(length <= end - payload)
        yield kind, payload, length
        position = payload + length


def _valid_ebml(path: Path, size: int, extension: str) -> bool:
    budget = [_MAX_CONTAINER_NODES]
    video_tracks, block_tracks = set(), set()
    header_valid = False
    with path.open('rb') as source:
        def walk(start, end, depth=0):
            _require(depth <= _MAX_CONTAINER_DEPTH)
            for kind, position, length in _ebml_entries(source, start, end, budget):
                if kind == 0xae:
                    number = track_type = None
                    for field, offset, field_size in _ebml_entries(source, position, position + length, budget):
                        if field in (0xd7, 0x83):
                            _require(1 <= field_size <= 8)
                            source.seek(offset)
                            value = int.from_bytes(_read(source, field_size, offset + field_size), 'big')
                            if field == 0xd7:
                                number = value
                            else:
                                track_type = value
                    if track_type == 1 and number:
                        video_tracks.add(number)
                elif kind in (0xa3, 0xa1):
                    source.seek(position)
                    track = _ebml_vint(source, position + length)
                    _require(track is not None and track > 0 and position + length - source.tell() > 3)
                    block_tracks.add(track)
                elif kind in (0x18538067, 0x1654ae6b, 0x1f43b675, 0xa0):
                    walk(position, position + length, depth + 1)

        for kind, position, length in _ebml_entries(source, 0, size, budget):
            if kind == 0x1a45dfa3 and not header_valid:
                for field, offset, field_size in _ebml_entries(source, position, position + length, budget):
                    if field == 0x4282:
                        source.seek(offset)
                        _require(field_size <= 32)
                        header_valid = _read(source, field_size, offset + field_size) == (
                            b'webm' if extension == '.webm' else b'matroska')
            elif kind == 0x18538067:
                _require(header_valid)
                walk(position, position + length)
    return header_valid and bool(video_tracks & block_tracks)


def validate_media(path: Path, max_bytes: int = MAX_MEDIA_BYTES) -> None:
    extension = path.suffix.lower()
    if extension not in MEDIA_EXTENSIONS:
        raise ThemeError('Choose a PNG, JPEG, GIF, BMP, WebP, MP4, MOV, WebM, MKV, or AVI background.')
    size = path.stat().st_size
    if size > max_bytes:
        raise ThemeError('The background is too large. Choose media smaller than 250 MiB.')
    with path.open('rb') as handle:
        header = handle.read(65536)
        handle.seek(max(0, size - 64))
        trailer = handle.read(64)
    try:
        if extension == '.png':
            valid = (size >= 45 and header[:8] == b'\x89PNG\r\n\x1a\n' and
                     header[8:16] == b'\x00\x00\x00\rIHDR' and b'IEND\xaeB`\x82' in trailer and
                     _valid_png_chunks(path, size))
        elif extension in {'.jpg', '.jpeg'}:
            valid = _valid_jpeg(path, size)
        elif extension == '.gif':
            valid = _valid_gif(path, size)
        elif extension == '.bmp':
            valid = _valid_bmp(header, size)
        elif extension in {'.webp', '.avi'}:
            valid = _valid_riff(path, size, extension)
        elif extension in {'.webm', '.mkv'}:
            valid = _valid_ebml(path, size, extension)
        else:
            valid = _valid_bmff(path, size, extension)
    except (ValueError, struct.error, zlib.error):
        valid = False
    if not valid:
        raise ThemeError('The background content does not match its file type or is damaged. Choose a valid media file.')

