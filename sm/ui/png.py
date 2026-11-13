import struct
import zlib


def encode(rows):
    height, width = len(rows), len(rows[0])
    raw = b''.join(b'\0' + bytes(c for p in row for c in
                              ((p >> 16) & 255, (p >> 8) & 255, p & 255, p >> 24)) for row in rows)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def edge_alpha(rows, colour, tolerance=0):
    rows = [list(row) for row in rows]
    height, width = len(rows), len(rows[0])
    pending = [(x, y) for x in range(width) for y in (0, height-1)]
    pending += [(x, y) for y in range(height) for x in (0, width-1)]
    seen = set()
    while pending:
        x, y = pending.pop()
        if (x, y) in seen or not (0 <= x < width and 0 <= y < height): continue
        seen.add((x, y))
        pixel = rows[y][x]
        if pixel >> 24 and any(abs(((pixel >> shift) & 255)-((colour >> shift) & 255)) > tolerance for shift in (16, 8, 0)): continue
        rows[y][x] = 0
        pending.extend(((x-1, y), (x+1, y), (x, y-1), (x, y+1)))
    return tuple(tuple(row) for row in rows)


def decode(data):
    if len(data) > 16 * 1024 * 1024 or data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Expected a PNG smaller than 16 MiB')
    offset, chunks, compressed, palette, alpha = 8, [], bytearray(), b'', b''
    while offset + 12 <= len(data):
        size, = struct.unpack_from('>I', data, offset)
        end = offset + 12 + size
        if end > len(data): raise ValueError('Truncated PNG chunk')
        kind, payload = data[offset+4:offset+8], data[offset+8:end-4]
        crc, = struct.unpack_from('>I', data, end-4)
        if zlib.crc32(kind + payload) != crc: raise ValueError('PNG checksum mismatch')
        chunks.append(kind)
        if kind == b'IHDR':
            if len(chunks) != 1 or size != 13: raise ValueError('Invalid PNG header')
            width, height, depth, colour, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if not (0 < width <= 2048 and 0 < height <= 2048 and width*height <= 1048576):
                raise ValueError('PNG dimensions exceed 2048 per side or one million pixels')
            if depth != 8 or colour not in (0, 2, 3, 4, 6) or compression or filtering or interlace:
                raise ValueError('Use an 8-bit non-interlaced PNG')
        elif kind == b'PLTE': palette = payload
        elif kind == b'tRNS': alpha = payload
        elif kind == b'IDAT': compressed.extend(payload)
        elif kind == b'IEND': break
        elif not kind[0] & 32: raise ValueError('Unsupported PNG chunk')
        offset = end
    if not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or not compressed:
        raise ValueError('Incomplete PNG')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
    stride, expected = width * channels, (width * channels + 1) * height
    decoder = zlib.decompressobj()
    try: raw = decoder.decompress(compressed, expected + 1)
    except zlib.error as error: raise ValueError('Invalid PNG compression') from error
    if len(raw) != expected or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid PNG pixel extent')
    if colour == 3 and (not palette or len(palette) % 3 or len(palette) > 768 or len(alpha) > len(palette)//3):
        raise ValueError('Invalid PNG palette')
    if alpha and colour != 3 and len(alpha) != {0: 2, 2: 6}.get(colour):
        raise ValueError('Invalid PNG transparency')
    transparent = struct.unpack('>' + 'H'*(len(alpha)//2), alpha) if alpha and colour in (0, 2) else None
    previous, rows = bytearray(stride), []
    for y in range(height):
        start = y*(stride+1)
        mode, row = raw[start], bytearray(raw[start+1:start+1+stride])
        if mode > 4: raise ValueError('Invalid PNG row filter')
        for x in range(stride):
            a, b, c = row[x-channels] if x >= channels else 0, previous[x], previous[x-channels] if x >= channels else 0
            p = a+b-c
            pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
            predictor = (0, a, b, (a+b)//2, a if pa <= pb and pa <= pc else b if pb <= pc else c)[mode]
            row[x] = (row[x]+predictor) & 255
        pixels = []
        for x in range(0, stride, channels):
            v = row[x:x+channels]
            if colour == 3:
                index = v[0]
                if index*3+3 > len(palette): raise ValueError('PNG index outside palette')
                r, g, b = palette[index*3:index*3+3]
                a = alpha[index] if index < len(alpha) else 255
            elif colour in (0, 4): r = g = b = v[0]; a = v[1] if colour == 4 else 0 if transparent == (v[0],) else 255
            else: r, g, b = v[:3]; a = v[3] if colour == 6 else 0 if transparent == tuple(v) else 255
            pixels.append((a << 24 | r << 16 | g << 8 | b) if a else 0)
        rows.append(tuple(pixels)); previous = row
    return tuple(rows)
