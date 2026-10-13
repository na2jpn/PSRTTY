"""One raw ADIF datagram per saved QSO; no automatic retry or receipt claim."""
from ipaddress import ip_address
import socket
from .adif import adif_record

DEFAULT_OPTIONS = {'enabled': False, 'host': '127.0.0.1', 'port': 2236}

class UdpError(ValueError):
    def __init__(self,key):super().__init__(key);self.key=key

def options_checked(value):
    if not isinstance(value,dict):raise UdpError('udp.bad_settings')
    host=value.get('host',DEFAULT_OPTIONS['host'])
    try:host=str(ip_address(str(host).strip()))
    except ValueError:raise UdpError('udp.bad_ip')
    port=value.get('port',DEFAULT_OPTIONS['port'])
    if type(port) is not int or not 1<=port<=65535:raise UdpError('udp.bad_port')
    return {'enabled':value.get('enabled') is True,'host':host,'port':port}

def payload(qso):
    data=adif_record(qso).encode('utf-8')
    if len(data)>65507:raise UdpError('udp.too_large')
    return data

def send_qso(qso,options):
    options=options_checked(options)
    if not options['enabled']:return None
    data=payload(qso);host=options['host'];port=options['port']
    family=socket.AF_INET6 if ip_address(host).version==6 else socket.AF_INET
    target=(host,port,0,0) if family==socket.AF_INET6 else (host,port)
    with socket.socket(family,socket.SOCK_DGRAM) as sock:
        sock.settimeout(.5)
        if sock.sendto(data,target)!=len(data):raise OSError('Incomplete UDP datagram')
    return f'[{host}]:{port}' if family==socket.AF_INET6 else f'{host}:{port}'
