# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Read-only LAN display-name/model lookup; no firmware changes."""
import ipaddress
import json
import socket
import urllib.request


def clean_name(value):
    return value.strip() if isinstance(value,str) and value.strip() and len(value.strip())<=80 and not any(ord(c)<32 for c in value) else ''


def probe_printer(address):
    from cfs_connection_errors import ConnectionIssue,network_issue
    try:
        ip=ipaddress.IPv4Address(str(address).strip())
        if ip.is_unspecified or ip.is_loopback or ip.is_multicast or int(ip)==0xffffffff:raise ValueError()
        address=str(ip)
    except ValueError:
        raise ConnectionIssue('BAD_IP','Ungültige Drucker-IP. Eine lokale IPv4-Adresse ohne http:// oder Port eingeben.') from None
    try:
        with urllib.request.urlopen('http://'+address+':4408/printer/info',timeout=4) as response:
            raw=response.read(256001)
        if len(raw)>256000:raise ValueError()
        info=json.loads(raw).get('result')
        if not isinstance(info,dict) or info.get('state') not in ('ready','startup','shutdown','error') or not clean_name(info.get('hostname')):
            raise ValueError()
        return info
    except (ValueError,TypeError,AttributeError):
        raise ConnectionIssue('NOT_PRINTER','Die IP antwortet, liefert aber keinen unterstützten Druckerzugang. Die Drucker-IP prüfen; es wurde keine SSH-Anmeldung ausgeführt.') from None
    except Exception as error:
        raise network_issue(error,address) from error


def printer_identity(address):
    info=probe_printer(address)
    address=str(ipaddress.IPv4Address(address))
    result={'ip':address,'name':'','hostname':'','model':'','source':''}
    def fetch(path):
        with urllib.request.urlopen('http://'+address+':4408'+path,timeout=4) as response:
            data=response.read(256001)
        if len(data)>256000:raise ValueError('Antwort für Gerätenamen zu groß.')
        return json.loads(data)
    result['hostname']=clean_name(info.get('hostname'))
    name=clean_name(info.get('device_name')) or clean_name(info.get('printer_name'))
    if name:result.update(name=name,source='Drucker')
    if not result['name']:
        try:
            dns=clean_name(socket.gethostbyaddr(address)[0])
            if dns and dns!=address:result.update(name=dns,source='Netzwerk / DNS')
        except OSError:pass
    if not result['name'] and result['hostname']:
        result.update(name=result['hostname'],source='Drucker-Hostname')
    try:
        info=fetch('/server/files/config/cfs_cloud_profiles/tag-materials.json')
        result['model']=clean_name(info.get('printer_int_name'))
    except (OSError,ValueError,TypeError):pass
    if not result['model']:
        host=result['hostname'].lower().replace('-','').replace(' ','')
        for token,model in (('k2pro','F012'),('k2plus','F008'),('crealityhi','F018'),('hi','F018'),('k1','K1')):
            if host.startswith(token):result['model']=model;break
    if not result['name']:raise ValueError('Kein Gerätename gemeldet. Die Bezeichnung kann manuell eingetragen werden.')
    return result


def icon_name(model):
    if str(model)=='F018':return 'printer-hi.png'
    if str(model) in ('F012','F008') or str(model).upper().startswith(('K1','CR-K1')):return 'printer-closed.png'
    return 'printer-generic.png'
