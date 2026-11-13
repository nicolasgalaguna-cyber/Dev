"""Build private Icecast config from environment, without shell interpolation."""
import os
from xml.etree.ElementTree import Element, SubElement, ElementTree


def node(parent, tag, text=None):
    el = SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el

root = Element('icecast')
node(root,'location','Community')
node(root,'admin','admin@localhost')
limits=node(root,'limits')
for tag, value in [('clients',100),('sources',2),('queue-size',524288),('client-timeout',30),('header-timeout',15),('source-timeout',10)]:
    node(limits,tag,value)
auth=node(root,'authentication')
node(auth,'source-password',os.environ['ICECAST_SOURCE_PASSWORD'])
node(auth,'relay-password',os.environ['ICECAST_SOURCE_PASSWORD'])
node(auth,'admin-user','admin')
node(auth,'admin-password',os.environ['ICECAST_ADMIN_PASSWORD'])
node(root,'hostname','localhost')
listen=node(root,'listen-socket');node(listen,'port',8000)
paths=node(root,'paths')
for tag,value in [('basedir','/usr/share/icecast2'),('logdir','/tmp'),('webroot','/usr/share/icecast2/web'),('adminroot','/usr/share/icecast2/admin')]:
    node(paths,tag,value)
logs=node(root,'logging');node(logs,'accesslog','-');node(logs,'errorlog','-');node(logs,'loglevel',2)
security=node(root,'security');node(security,'chroot',0)
ElementTree(root).write('/tmp/icecast.xml',encoding='utf-8',xml_declaration=True)
os.execvp('icecast2',['icecast2','-c','/tmp/icecast.xml'])
