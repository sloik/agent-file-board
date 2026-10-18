"""Bounded, data-only board-report v2 validation; no renderer dependencies."""
import math
import re

TONES = {'info', 'success', 'warning', 'danger'}
CHARTS = {'line-chart', 'area-chart', 'grouped-bar-chart', 'stacked-bar-chart'}
TRIM = ' \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'


def text(value, limit=200, multiline=False):
    pattern = r'[\x00-\x08\x0b-\x1f\x7f\ud800-\udfff]' if multiline else r'[\x00-\x1f\x7f\ud800-\udfff]'
    return isinstance(value, str) and 1 <= len(value) <= limit and bool(value.strip(TRIM)) and not re.search(pattern, value)


def number(value):
    return type(value) in (int, float) and abs(value) <= 1e12 and math.isfinite(value)


def validate_report(report, version=2, extra=None):
    def require(condition, message):
        if not condition:
            raise ValueError(f'UI v{version}: ' + message)

    def keys(obj, names):
        return isinstance(obj, dict) and set(obj) == set(names.split())

    require(keys(report, 'library version title components') and report['library'] == 'board-report'
            and type(report['version']) in (int, float) and report['version'] == version and text(report['title']), 'invalid report')
    count = 0

    def children(items, depth):
        require(isinstance(items, list) and 1 <= len(items) <= 16, 'requires 1–16 children')
        for item in items:
            node(item, depth)

    def strings(items, limit=200, maximum=50):
        return isinstance(items, list) and 1 <= len(items) <= maximum and all(text(v, limit) for v in items)

    def values(items, length):
        return isinstance(items, list) and len(items) == length and all(number(v) for v in items)

    def node(c, depth):
        nonlocal count
        count += 1
        require(count <= 64 and depth <= 4, 'maximum 64 nodes and nesting depth 4')
        require(isinstance(c, dict) and text(c.get('title')), 'invalid component title')
        kind = c.get('type')
        require(isinstance(kind, str), 'invalid component type')
        if kind == 'table':
            require(keys(c, 'type title columns rows') and strings(c['columns'], maximum=8)
                    and isinstance(c['rows'], list) and 1 <= len(c['rows']) <= 50
                    and all(strings(row, 1000, 8) and len(row) == len(c['columns']) for row in c['rows']), 'invalid table')
        elif kind == 'bar-chart':
            require(keys(c, 'type title labels values') and strings(c['labels']) and values(c['values'], len(c['labels'])), 'invalid bars')
        elif kind in CHARTS:
            require(keys(c, 'type title labels series') and strings(c['labels']) and isinstance(c['series'], list)
                    and 1 <= len(c['series']) <= 6, 'invalid chart')
            require(all(keys(s, 'name values') and text(s['name']) and values(s['values'], len(c['labels'])) for s in c['series']), 'invalid chart series')
            require(len({s['name'] for s in c['series']}) == len(c['series']), 'duplicate series name')
        elif kind == 'metric':
            require((keys(c, 'type title value') or keys(c, 'type title value detail')) and text(c['value'])
                    and ('detail' not in c or text(c['detail'], 1000)), 'invalid metric')
        elif kind in {'text', 'code-block', 'callout'}:
            field = 'code' if kind == 'code-block' else 'text'
            fields = 'type title ' + field + (' tone' if kind == 'callout' else '')
            require(keys(c, fields) and text(c[field], 4000, kind == 'code-block'), 'invalid content')
            if kind == 'callout':
                require(isinstance(c['tone'], str) and c['tone'] in TONES, 'invalid callout tone')
        elif kind == 'tag':
            require(keys(c, 'type title tone') and isinstance(c['tone'], str) and c['tone'] in TONES, 'invalid tag')
        elif kind == 'separator':
            require(keys(c, 'type title'), 'invalid separator')
        elif kind == 'list':
            require(keys(c, 'type title items') and strings(c['items'], 1000), 'invalid list')
        elif kind in {'card', 'stack'}:
            require(keys(c, 'type title children' + (' direction' if kind == 'stack' else '')), 'invalid container')
            if kind == 'stack':
                require(isinstance(c['direction'], str) and c['direction'] in {'row', 'column'}, 'invalid stack direction')
            children(c['children'], depth + 1)
        elif kind in {'tabs', 'accordion'}:
            require(keys(c, 'type title items') and isinstance(c['items'], list) and 1 <= len(c['items']) <= 8, 'invalid sections')
            ids = set()
            for item in c['items']:
                require(keys(item, 'id title children') and text(item['title']) and isinstance(item['id'], str)
                        and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', item['id']) and item['id'] not in ids, 'invalid/duplicate section ID')
                ids.add(item['id'])
                children(item['children'], depth + 1)
        elif kind == 'steps':
            require(keys(c, 'type title items') and isinstance(c['items'], list) and 1 <= len(c['items']) <= 16, 'invalid steps')
            for item in c['items']:
                require(keys(item, 'title text state') and text(item['title']) and text(item['text'], 1000)
                        and isinstance(item['state'], str) and item['state'] in {'pending', 'current', 'complete'}, 'invalid step')
        elif extra is not None:
            extra(c, depth, children)
        else:
            raise ValueError(f'UI v{version}: unknown component ' + kind)

    children(report['components'], 1)
    return report
