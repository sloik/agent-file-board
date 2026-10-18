"""Versioned, bounded offline form questions and typed immutable answers."""
import calendar
import json
import math
import re
from static_reports import text

ICONS = {'info','check','warning','error','star','heart','file','folder','chart','image','clock','user'}
KINDS = {'input','textarea','select','radio-group','checkbox-group','chips','option-cards','date-picker','slider','switch-group','editable-table'}
OPTION_KINDS = {'select','radio-group','checkbox-group','chips','option-cards','switch-group'}


def require(ok, message):
    if not ok:
        raise ValueError('Form: ' + message)


def keys(value, needed, optional=''):
    return isinstance(value, dict) and set(needed.split()) <= set(value) <= set((needed+' '+optional).split())


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,63}', value) is not None


def number(value):
    return type(value) in (int, float) and abs(value) <= 1e9 and math.isfinite(value)


def date(value):
    if not isinstance(value, str) or re.fullmatch(r'\d{4}-\d{2}-\d{2}', value, re.ASCII) is None:
        return False
    year, month, day = map(int, value.split('-'))
    return 1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= calendar.monthrange(year, month)[1]


def multiple(field):
    return field['type'] in {'checkbox-group','switch-group'} or (field['type'] in {'chips','option-cards'} and field['multiple'])


def value_valid(field, value):
    kind = field['type']
    if value is None:
        return not field['required'] and kind not in {'checkbox-group','switch-group','slider','boolean'} and not (kind in {'chips','option-cards'} and field['multiple'])
    if kind == 'boolean':
        return type(value) is bool
    if kind == 'textarea' or (kind == 'input' and field['dataType'] == 'text') or kind == 'text':
        return text(value, field['maxLength'], kind == 'textarea')
    if kind == 'number' or (kind == 'input' and field['dataType'] == 'number'):
        return number(value) and field['min'] <= value <= field['max']
    if kind in OPTION_KINDS:
        allowed = {o['id'] for o in field['options']}
        if multiple(field):
            return isinstance(value, list) and (bool(value) or not field['required']) and all(isinstance(v, str) and v in allowed for v in value) and len(set(value)) == len(value)
        return isinstance(value, str) and value in allowed
    if kind == 'date-picker':
        return date(value) and ('min' not in field or value >= field['min']) and ('max' not in field or value <= field['max'])
    if kind == 'slider':
        if not number(value) or not field['min'] <= value <= field['max']:
            return False
        position = (value-field['min']) / field['step']
        return abs(position-round(position)) <= 1e-7
    return False


def options(field):
    items = field['options']
    require(isinstance(items, list) and 1 <= len(items) <= 32, 'options require 1–32 entries')
    for item in items:
        require(keys(item, 'id label', 'description') and identifier(item['id']) and text(item['label'])
                and ('description' not in item or text(item['description'],1000)), 'invalid option')
    require(len({o['id'] for o in items}) == len(items), 'duplicate option ID')


def scalar_definition(field, *, column=False):
    kind = field['type']
    extra, needed = '', ''
    if column:
        require(kind in {'text','number','select','boolean'}, 'unknown column type')
    else:
        require(kind in KINDS-{'editable-table'}, 'unknown field type')
    if kind == 'input':
        require(field.get('dataType') in ('text','number'), 'invalid input dataType')
        needed += ' dataType'
    if kind in {'text','textarea'} or (kind == 'input' and field['dataType']=='text'):
        needed += ' maxLength'
        require(number(field.get('maxLength')) and 1 <= field['maxLength'] <= 4000 and field['maxLength'] == int(field['maxLength']), 'invalid maxLength')
    if kind == 'number' or (kind == 'input' and field['dataType']=='number') or kind == 'slider':
        needed += ' min max'
        require(number(field.get('min')) and number(field.get('max')) and field['min'] <= field['max'], 'invalid number bounds')
    if kind == 'slider':
        needed += ' step'
        require(number(field.get('step')) and field['step'] > 0 and field['min'] < field['max'], 'invalid slider step')
        count = (field['max']-field['min'])/field['step']
        require(1 <= count <= 10000 and abs(count-round(count)) <= 1e-7, 'slider must have 1–10000 integral steps')
    if kind in OPTION_KINDS:
        needed += ' options'
        require('options' in field, 'missing options'); options(field)
    if kind in {'chips','option-cards'}:
        needed += ' multiple'
        require(type(field.get('multiple')) is bool, 'multiple must be boolean')
    if kind == 'date-picker':
        extra += ' min max'
        require(all(date(field[k]) for k in ('min','max') if k in field), 'invalid date bounds')
        require('min' not in field or 'max' not in field or field['min'] <= field['max'], 'inverted date bounds')
    require(keys(field, 'id type label required'+needed, 'help'+extra+('' if column else ' default')), 'unknown/missing field properties')
    if 'default' in field:
        require(value_valid(field,field['default']), 'invalid default value')


def validate_form(form):
    require(keys(form,'version id type prompt fields buttons') and type(form['version']) in (int,float) and form['version']==2 and form['type']=='form'
            and identifier(form['id']) and text(form['prompt'],5000,True), 'invalid question envelope')
    fields=form['fields']
    require(isinstance(fields,list) and 1<=len(fields)<=24, 'requires 1–24 fields')
    ids=set();cells=0
    for field in fields:
        require(isinstance(field,dict) and identifier(field.get('id')) and field['id'] not in ids and isinstance(field.get('type'),str)
                and text(field.get('label')) and type(field.get('required')) is bool and ('help' not in field or text(field['help'],1000)), 'invalid/duplicate field')
        ids.add(field['id'])
        if field['type']!='editable-table':
            scalar_definition(field); continue
        require(keys(field,'id type label required columns rows','help') and isinstance(field['columns'],list) and 1<=len(field['columns'])<=8
                and isinstance(field['rows'],list) and 1<=len(field['rows'])<=50, 'invalid editable table')
        columns=field['columns'];column_ids=set();row_ids=set()
        for col in columns:
            require(isinstance(col,dict) and identifier(col.get('id')) and col['id'] not in column_ids and isinstance(col.get('type'),str)
                    and text(col.get('label')) and type(col.get('required')) is bool and ('help' not in col or text(col['help'],1000)), 'invalid column')
            column_ids.add(col['id']);scalar_definition(col,column=True)
        for row in field['rows']:
            require(keys(row,'id values') and identifier(row['id']) and row['id'] not in row_ids and isinstance(row['values'],dict) and set(row['values'])==column_ids, 'invalid row')
            row_ids.add(row['id'])
            require(all(value_valid(c,row['values'][c['id']]) for c in columns), 'invalid baseline cell')
        cells+=len(columns)*len(field['rows']);require(cells<=400, 'maximum 400 editable cells per form')
    buttons=form['buttons']
    require(isinstance(buttons,list) and 1<=len(buttons)<=2, 'requires submit and optional reset')
    for button in buttons:
        require(keys(button,'id label action','icon') and identifier(button['id']) and text(button['label'])
                and isinstance(button['action'],str) and button['action'] in {'submit','reset'}
                and ('icon' not in button or isinstance(button['icon'],str) and button['icon'] in ICONS), 'invalid button')
    require(len({b['id'] for b in buttons})==len(buttons) and sum(b['action']=='submit' for b in buttons)==1
            and sum(b['action']=='reset' for b in buttons)<=1, 'duplicate buttons/actions')
    return form


def validate_answer(answer, form):
    validate_form(form)
    require(keys(answer,'version question values') and type(answer['version']) in (int,float) and answer['version']==2 and answer['question']==form['id']
            and isinstance(answer['values'],dict) and set(answer['values'])=={f['id'] for f in form['fields']}, 'answer must contain exactly the defined fields')
    for field in form['fields']:
        value=answer['values'][field['id']]
        if field['type']!='editable-table':
            require(value_valid(field,value), 'invalid answer field '+field['id']);continue
        require(keys(value,'changes') and isinstance(value['changes'],list) and len(value['changes'])<=len(field['rows'])*len(field['columns'])
                and (value['changes'] or not field['required']), 'invalid table changes')
        columns={c['id']:c for c in field['columns']};rows={r['id']:r['values'] for r in field['rows']};seen=set()
        for change in value['changes']:
            require(keys(change,'row column value') and isinstance(change['row'],str) and isinstance(change['column'],str)
                    and change['row'] in rows and change['column'] in columns, 'unknown cell')
            pair=(change['row'],change['column']);require(pair not in seen,'duplicate cell');seen.add(pair)
            require(value_valid(columns[change['column']],change['value']), 'invalid changed cell')
            before=rows[change['row']][change['column']]
            require(not ((number(before) and number(change['value']) or type(before) is type(change['value'])) and before==change['value']), 'unchanged cell in patch')
    return answer
