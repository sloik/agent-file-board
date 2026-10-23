"""Static report v3 additions and bounded embedded PNGs; stdlib only."""
import base64
import binascii
import re
from static_reports import text, number

ICONS = {'info', 'check', 'warning', 'error', 'star', 'heart', 'file', 'folder', 'chart', 'image', 'clock', 'user'}
TONES = {'info', 'success', 'warning', 'danger'}


def png_pixels(value):
    def require(ok):
        if not ok:
            raise ValueError('UI v3: invalid embedded PNG (64KiB, 1024px maximum)')
    require(isinstance(value, str) and value.startswith('data:image/png;base64,'))
    encoded = value[len('data:image/png;base64,'):]
    require(1 <= len(encoded) <= 87384 and re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', encoded) is not None)
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        require(False)
    require(base64.b64encode(data).decode() == encoded and len(data) <= 65536 and data[:8] == b'\x89PNG\r\n\x1a\n')
    pos = 8
    pixels = 0
    idat = False
    idat_closed = False
    idat_bytes = 0
    palette = False
    color = bits = 0
    while pos < len(data):
        require(pos + 12 <= len(data))
        size = int.from_bytes(data[pos:pos+4], 'big')
        kind = data[pos+4:pos+8]
        end = pos + 12 + size
        require(end <= len(data) and re.fullmatch(b'[A-Za-z]{4}', kind) is not None and 65 <= kind[2] <= 90)
        payload = data[pos+8:pos+8+size]
        require(binascii.crc32(kind + payload) & 0xffffffff == int.from_bytes(data[end-4:end], 'big'))
        require(kind not in {b'acTL', b'fcTL', b'fdAT'})
        require(kind[0] >= 97 or kind in {b'IHDR', b'PLTE', b'IDAT', b'IEND'})
        if pos == 8:
            require(kind == b'IHDR' and size == 13)
            width, height = int.from_bytes(payload[:4], 'big'), int.from_bytes(payload[4:8], 'big')
            require(1 <= width <= 1024 and 1 <= height <= 1024)
            bits, color, compression, filtering, interlace = payload[8:13]
            require(bits in {0: [1,2,4,8,16], 2: [8,16], 3: [1,2,4,8], 4: [8,16], 6: [8,16]}.get(color, [])
                    and compression == 0 and filtering == 0 and interlace in (0,1))
            pixels = width * height
        else:
            require(kind != b'IHDR')
        if kind == b'PLTE':
            require(not palette and not idat and color not in (0, 4) and size % 3 == 0 and 3 <= size <= 768)
            if color == 3:
                require(size // 3 <= 2 ** bits)
            palette = True
        if kind == b'IDAT':
            require(not idat_closed and (color != 3 or palette))
            idat = True
            idat_bytes += size
        elif idat:
            idat_closed = True
        if kind == b'IEND':
            require(size == 0 and idat and idat_bytes > 0 and end == len(data))
            return pixels
        pos = end
    require(False)


def extension_validator():
    pixels = 0
    modal_depths = []

    def require(ok, message):
        if not ok:
            raise ValueError('UI v3: ' + message)

    def keys(obj, names, optional=''):
        needed = set(names.split())
        return isinstance(obj, dict) and needed <= set(obj) <= needed | set(optional.split())

    def strings(values, limit=200, maximum=50):
        return isinstance(values, list) and 1 <= len(values) <= maximum and all(text(v, limit) for v in values)

    def numbers(values, length, nonnegative=False):
        return isinstance(values, list) and len(values) == length and all(number(v) and (not nonnegative or v >= 0) for v in values)

    def image(obj):
        nonlocal pixels
        require(keys(obj, 'src alt', 'caption') and text(obj['alt']) and ('caption' not in obj or text(obj['caption'], 1000)), 'invalid image description')
        pixels += png_pixels(obj['src'])
        require(pixels <= 4194304, 'total image pixels exceed 4194304')

    def validate(c, depth, children):
        kind = c['type']
        if kind in {'pie-chart', 'radial-chart', 'single-stacked-bar-chart'}:
            require(keys(c, 'type title labels values' + (' variant' if kind == 'pie-chart' else ''))
                    and strings(c['labels']) and numbers(c['values'], len(c['labels']), True), 'invalid nonnegative chart')
            if kind == 'pie-chart':
                require(isinstance(c['variant'], str) and c['variant'] in {'pie', 'donut'}, 'invalid pie variant')
        elif kind == 'radar-chart':
            require(keys(c, 'type title labels series') and strings(c['labels']) and len(c['labels']) >= 3
                    and isinstance(c['series'], list) and 1 <= len(c['series']) <= 6, 'invalid radar')
            require(all(keys(s, 'name values') and text(s['name']) and numbers(s['values'], len(c['labels']), True) for s in c['series']), 'invalid radar series')
            require(len({s['name'] for s in c['series']}) == len(c['series']), 'duplicate radar series')
        elif kind == 'scatter-chart':
            require(keys(c, 'type title xLabel yLabel datasets') and text(c['xLabel']) and text(c['yLabel'])
                    and isinstance(c['datasets'], list) and 1 <= len(c['datasets']) <= 6, 'invalid scatter')
            for dataset in c['datasets']:
                require(keys(dataset, 'name points') and text(dataset['name']) and isinstance(dataset['points'], list)
                        and 1 <= len(dataset['points']) <= 50, 'invalid scatter dataset')
                require(all(keys(p, 'x y', 'z') and number(p['x']) and number(p['y'])
                            and ('z' not in p or (number(p['z']) and p['z'] >= 0)) for p in dataset['points']), 'invalid scatter point')
            require(len({s['name'] for s in c['datasets']}) == len(c['datasets']), 'duplicate scatter series')
        elif kind in {'icon', 'icon-text'}:
            require(keys(c, 'type title name' + (' text' if kind == 'icon-text' else ''))
                    and isinstance(c['name'], str) and c['name'] in ICONS, 'invalid icon')
            if kind == 'icon-text':
                require(text(c['text'], 1000), 'invalid icon text')
        elif kind == 'metric-comparison':
            require(keys(c, 'type title value previous', 'detail') and text(c['value']) and text(c['previous'])
                    and ('detail' not in c or text(c['detail'], 1000)), 'invalid metric comparison')
        elif kind == 'tag-block':
            require(keys(c, 'type title items') and isinstance(c['items'], list) and 1 <= len(c['items']) <= 32, 'invalid tag block')
            require(all(keys(item, 'text tone') and text(item['text']) and isinstance(item['tone'], str)
                        and item['tone'] in TONES for item in c['items']), 'invalid tag item')
        elif kind == 'markdown':
            require(keys(c, 'type title text') and text(c['text'], 4000, True), 'invalid Markdown')
        elif kind == 'image':
            require(keys(c, 'type title src alt', 'caption'), 'invalid image')
            image({k:v for k,v in c.items() if k not in {'type', 'title'}})
        elif kind == 'image-text':
            require(keys(c, 'type title src alt text size') and text(c['text'], 1000)
                    and isinstance(c['size'], str) and c['size'] in {'small', 'large'}, 'invalid image text')
            image({'src':c['src'], 'alt':c['alt']})
        elif kind == 'image-gallery':
            require(keys(c, 'type title images') and isinstance(c['images'], list) and 1 <= len(c['images']) <= 8, 'invalid image gallery')
            for item in c['images']:
                image(item)
        elif kind == 'card-grid':
            require(keys(c, 'type title variant children') and isinstance(c['variant'], str)
                    and c['variant'] in {'snippet', 'context', 'composite', 'visual'}, 'invalid card grid')
            require(isinstance(c['children'], list) and all(isinstance(n, dict) and n.get('type') == 'card' for n in c['children']), 'card grid requires cards')
            if c['variant'] == 'visual':
                require(all(isinstance(n.get('children'), list) and len(n['children']) > 0
                            and isinstance(n['children'][0], dict) and n['children'][0].get('type') == 'image' for n in c['children']), 'visual cards require leading image')
            children(c['children'], depth+1)
        elif kind == 'carousel':
            require(keys(c, 'type title items') and isinstance(c['items'], list) and 1 <= len(c['items']) <= 8, 'invalid carousel')
            ids = set()
            for item in c['items']:
                require(keys(item, 'id title children') and text(item['title']) and isinstance(item['id'], str)
                        and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', item['id']) and item['id'] not in ids, 'invalid carousel item')
                ids.add(item['id']); children(item['children'], depth+1)
        elif kind == 'modal':
            require(keys(c, 'type title children') and not modal_depths, 'invalid or nested modal')
            modal_depths.append(depth)
            try:
                children(c['children'], depth+1)
            finally:
                modal_depths.pop()
        else:
            raise ValueError('UI v3: unknown component ' + kind)
    return validate


def gallery_hint(report):
    """Advisory only: several separate `image` components in one report are easier to
    read as one `image-gallery`, which viewers can enlarge and browse together."""
    count = 0
    pending = [report]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if node.get("type") == "image":
                count += 1
            if node.get("type") != "image-gallery":
                pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    if count < 2:
        return None
    return (f"hint: this report has {count} separate image components; one image-gallery with a "
            "title and alt text per image lets readers enlarge and browse them together (see the "
            "convention's static report section). The message was posted unchanged.")
