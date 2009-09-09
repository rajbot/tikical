#!/usr/bin/python

'''
instructions from http://code.reddit.com/wiki/MemcachedChanges
'''

repo_path         = '/home/tikical/tikical'
tmp_install_path  = '/tmp/install-memcached'
memcached_tarball = 'memcached-1.2.5.tar.gz'

import commands
import os

def cmd(description, command):
    print description
    (ret, out) = commands.getstatusoutput(command)
    print out
    assert 0 == ret


cmd('making tmp_install dir', """mkdir -p %s""" % (tmp_install_path))

memcached_tarball_path = """%s/%s""" % (tmp_install_path, memcached_tarball)
if not os.path.exists(memcached_tarball_path):
    cmd('downloading memcached', """cd '%s' && wget 'http://www.danga.com/memcached/dist/memcached-1.2.5.tar.gz'""" % (tmp_install_path)) 

memcached_unpack_path = memcached_tarball_path.replace('.tar.gz', '')

if os.path.exists(memcached_unpack_path):
    cmd('removing previously untarred source, so that this script is re-runnable', """rm -r '%s'""" % (memcached_unpack_path))

cmd('untarring memcached', """cd '%s' && tar -zxf '%s'""" % (tmp_install_path, memcached_tarball))

cmd('downloading patch', """cd '%s' && wget 'http://code.reddit.com/raw-attachment/wiki/MemcachedChanges/memcached_1.2.5.patch.gz'""" % (memcached_unpack_path))

cmd('unzipping patch', """cd '%s' && gunzip memcached_1.2.5.patch.gz""" % (memcached_unpack_path))

cmd('applying path', """cd '%s' && patch memcached.c < memcached_1.2.5.patch""" % (memcached_unpack_path))
    
cmd('apt-get installing libevent-dev', """sudo DEBIAN_FRONTEND=noninteractive apt-get --force-yes -qq install libevent-dev""")

cmd('running configure', """cd '%s' && ./configure""" % (memcached_unpack_path))

cmd('running make', """make -C '%s'""" % (memcached_unpack_path))

cmd('running make install', """sudo make install -C '%s'""" % (memcached_unpack_path))

cmd('copying upstart script to /etc/event.d/', """sudo cp '%s/install/upstart/memcached' /etc/event.d""" % (repo_path))

print """To start memcached, you can now run:
    #sudo start memcached
To stop memcached, you can now run:    
    #sudo stop memcached
"""
