# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Display-only manufacturer convention; never change profile values or IDs."""
import re
from functools import lru_cache
NOZZLES={'Hi':'High Unicorn','Ob':'Obsidian'}


def split_manufacturer(value):
    value=str(value or '').strip()
    return _split_manufacturer(value)


@lru_cache(maxsize=512)
def _split_manufacturer(value):
    match=re.fullmatch(r'(.+?)\s+(Hi|Ob)',value,re.IGNORECASE)
    if not match:return value,''
    code='Hi' if match.group(2).casefold()=='hi' else 'Ob'
    return match.group(1).strip(),code


def nozzle_code(material):
    return split_manufacturer(manufacturer_value(material))[1]


def manufacturer_value(material):
    """The saved filament vendor may be newer than the native display brand."""
    for params in (material.get('resolved'),material.get('params')):
        if isinstance(params,dict):
            value=params.get('filament_vendor')
            if isinstance(value,list):value=value[0] if len(value)==1 else None
            if isinstance(value,str) and value.strip():return value.strip()
    return material.get('raw_brand') or material.get('brand') or ''


def manufacturer_name(material):
    return split_manufacturer(manufacturer_value(material))[0]


def inventory_text(materials):
    rows=[p for p in materials if p.get('registry_managed')]
    counts={code:sum(nozzle_code(p)==code for p in rows) for code in ('Hi','Ob','')}
    text=f"Druckerprofile: {counts['Hi']} Hi · {counts['Ob']} Ob · {counts['']} ohne Düsentyp."
    if rows and not counts['Hi'] and not counts['Ob']:
        text+=' Der geladene Druckerstand enthält noch keine Hi-/Ob-Hersteller. Slicer-Profile lassen sich separat für Etiketten öffnen; NFC-Codes brauchen eine bestätigte Druckerzuordnung.'
    return text


def nozzle_text(material):
    code=nozzle_code(material)
    return NOZZLES.get(code,'nicht erfasst')


def matches(material,search='',manufacturer='Alle',nozzle='Alle'):
    brand=manufacturer_name(material);code=nozzle_code(material)
    if manufacturer!='Alle' and brand.casefold()!=manufacturer.casefold():return False
    wanted={'High Unicorn (Hi)':'Hi','Obsidian (Ob)':'Ob','Nicht erfasst':''}.get(nozzle,nozzle)
    if nozzle!='Alle' and code!=wanted:return False
    haystack=' '.join(str(material.get(k,'')) for k in ('name','brand','raw_brand','id','type','printer_manufacturer','printer_model'))+' '+brand+' '+NOZZLES.get(code,'')+' '+code
    return all(word in haystack.casefold() for word in str(search).casefold().split())


def search_fields(material):
    """Immutable search index, rebuilt when confirmed material data changes."""
    brand,code=split_manufacturer(manufacturer_value(material))
    text=' '.join(str(material.get(k,'')) for k in ('name','brand','raw_brand','id','type','printer_manufacturer','printer_model'))+' '+brand+' '+NOZZLES.get(code,'')+' '+code
    return brand.casefold(),code,text.casefold()
