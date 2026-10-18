#!/usr/bin/env python3
"""Structural schemas; semantic/source-dependent rules live in form_contract.py."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parent.parent
ID={'type':'string','pattern':r'^[a-z][a-z0-9-]{0,63}(?![\s\S])'}
def text(n=200,multi=False):return {'type':'string','minLength':1,'maxLength':n,'pattern':r'^[^\u0000-\u0008\u000b-\u001f\u007f\ud800-\udfff]+(?![\s\S])'if multi else r'^[^\u0000-\u001f\u007f\ud800-\udfff]+(?![\s\S])'}
def obj(props,required=None):return {'type':'object','additionalProperties':False,'properties':props,'required':list(props)if required is None else required}
def arr(item,min=1,max=32):return {'type':'array','minItems':min,'maxItems':max,'items':item}
NUMBER={'type':'number','minimum':-1e9,'maximum':1e9}
OPTION=obj({'id':ID,'label':text(),'description':text(1000)},['id','label'])
def scalar(kind,column=False,data_type=None,version=2):
 props={'id':ID,'type':{'const':kind},'label':text(),'required':{'type':'boolean'},'help':text(1000)};needed=['id','type','label','required']
 actual=data_type if kind=='input'else kind
 if kind=='input':props['dataType']={'const':data_type};needed+=['dataType']
 if actual in ('text','textarea'):props['maxLength']={'type':'integer','minimum':1,'maximum':4000};needed+=['maxLength']
 if actual in ('number','slider'):props.update(min=NUMBER,max=NUMBER);needed+=['min','max']
 if actual=='slider':props['step']={'type':'number','exclusiveMinimum':0,'maximum':1e9};needed+=['step']
 if actual in ('select','radio-group','checkbox-group','chips','option-cards','switch-group'):props['options']=arr(obj({**OPTION['properties'],**({'when':CONDITION} if version==3 and not column else {})},OPTION['required']));needed+=['options']
 if actual in ('chips','option-cards'):props['multiple']={'type':'boolean'};needed+=['multiple']
 if actual=='date-picker':
  for key in ('min','max'):props[key]={'type':'string','pattern':r'^\d{4}-\d{2}-\d{2}(?![\s\S])'}
 if not column and version==3:props['visibleWhen']=CONDITION
 if not column:props['default']={'description':'Must satisfy this field’s semantic value rules, including required/default constraints.'}
 return obj(props,needed)
CONDITION=obj({'field':ID,'equals':{'type':['string','number']}})
def build(version=2):
 columns=[scalar(k,True,version=version)for k in ('text','number','select','boolean')]
 row=obj({'id':ID,'values':{'type':'object','minProperties':1,'maxProperties':8,'propertyNames':ID}})
 table=obj({'id':ID,'type':{'const':'editable-table'},'label':text(),'required':{'type':'boolean'},'help':text(1000),'columns':arr({'oneOf':columns},max=8),'rows':arr(row,min=0 if version==3 else 1,max=50),**({'visibleWhen':CONDITION,'rowOperations':obj({'add':{'type':'boolean'},'remove':{'type':'boolean'},'reorder':{'type':'boolean'},'minRows':{'type':'integer','minimum':0,'maximum':50},'maxRows':{'type':'integer','minimum':0,'maximum':50}})} if version==3 else {})},['id','type','label','required','columns','rows'])
 fields=[scalar('input',data_type=k,version=version)for k in ('text','number')]+[scalar(k,version=version)for k in ('textarea','select','radio-group','checkbox-group','chips','option-cards','date-picker','slider','switch-group')]+[table]
 button=obj({'id':ID,'label':text(),'action':{'enum':['submit','reset']},'icon':{'enum':['info','check','warning','error','star','heart','file','folder','chart','image','clock','user']}},['id','label','action'])
 question=obj({'version':{'const':version},'id':ID,'type':{'const':'form'},'prompt':text(5000,True),'fields':arr({'oneOf':fields},max=24),'buttons':arr(button,max=2),**({'validations':arr(obj({'left':ID,'op':{'enum':['eq','ne','lt','lte','gt','gte']},'right':ID,'message':text(1000)}),min=0,max=24)} if version==3 else {})},['version','id','type','prompt','fields','buttons'])
 change=obj({'row':ID,'column':ID,'value':{'type':['string','number','boolean','null']}})
 answer=obj({'version':{'const':version},'question':ID,'values':{'type':'object','minProperties':1,'maxProperties':24,'propertyNames':ID,'additionalProperties':{'oneOf':[{'type':['string','number','boolean','null']},arr(ID,min=0),obj({'changes':arr(change,min=0,max=400)}),*([obj({'changes':arr(change,min=0,max=400),'added':arr(row,min=0,max=50),'removed':arr(ID,min=0,max=50),'order':arr(ID,min=0,max=50)})] if version==3 else [])]}}})
 for name,data in [('question',question),('answer',answer)]:
  data={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':f'urn:agent-file-board:form-{name}:{version}','title':f'Form {name} version{version}','description':('Version3 adds earlier-field conditions, conditional choices, typed cross-field rules and bounded immutable row operations. ' if version==3 else '')+'Maximum65536 UTF-8 bytes. Runtime validates nonblank text, unique IDs, exact answer field/cell bindings, typed required/default values, actual calendar dates, number ranges, slider grids, exactly one submit/optional reset, valid baseline cells, total400 cells and distinct non-no-op changes. No URLs or arbitrary actions.',**data}
  yield ROOT/f'.agent-board/components/form-{name}-v{version}.schema.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n'
if __name__=='__main__':
 for path,data in [*build(2),*build(3)]:
  if '--check' in sys.argv:
   if path.read_text()!=data:raise SystemExit('Form schemas stale: run scripts/build_form_schemas.py')
  else:path.write_text(data)
