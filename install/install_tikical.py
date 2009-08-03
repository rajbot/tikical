#!/usr/bin/python

'''
instructions from http://code.reddit.com/wiki/RedditStartToFinishIntrepid
run as unix user 'tikical'
'''

user = 'tikical'
repo_path = '/home/tikical/tikical.git'

import commands
import os

def cmd(description, command):
    print description
    (ret, out) = commands.getstatusoutput(command)
    print out
    assert 0 == ret
    
cmd('installing deb packages', """sudo DEBIAN_FRONTEND=noninteractive apt-get --force-yes -qq install curl gcc gettext git-core libfreetype6 libfreetype6-dev libjpeg62 libjpeg62-dev libpng12-0 libpq-dev memcached postgresql python python-dev python-setuptools subversion  python-imaging""")


if not os.path.exists(repo_path):
    cmd('cloning github repo', """git clone git://github.com/rajbot/tikical.git '%s'""" % (repo_path))

cmd('chowning repo', """sudo chown -R %s '%s'""" % (user, repo_path))

cmd('updating repo', """cd '%s' && git pull""" % (repo_path))

cmd('running setup.py', """cd '%s/r2' && sudo python setup.py develop""" % (repo_path))

cmd('running make', """make -C '%s/r2'""" % (repo_path))

cmd('making pgsql dir', """sudo mkdir -p /usr/local/pgsql""")
cmd('making pgsql data dir', """sudo mkdir -p /usr/local/pgsql/data""")
cmd('chowning pgsql dir', """sudo chown postgres /usr/local/pgsql/data""")

# doesn't work
#cmd('setting postgress password', """sudo passwd postgres""")
print 'run "sudo passwd postgres" manually'

cmd('running initdb', """sudo -u postgres /usr/lib/postgresql/8.3/bin/initdb -D /usr/local/pgsql/data""")

cmd('creating db newreddit',   """sudo -u postgres createdb -E utf8 newreddit""")
cmd('creating db changed',     """sudo -u postgres createdb -E utf8 changed""")
cmd('creating db email',       """sudo -u postgres createdb -E utf8 email""")
cmd('creating db query_queue', """sudo -u postgres createdb -E utf8 query_queue""")

cmd('importing functions.sql', """sudo -u postgres psql newreddit < '%s/sql/functions.sql'""" % (repo_path))

cmd('create ri user with password "password"', """sudo -u postgres createuser -P ri""")

cmd('setting write perms for egg cache', """sudo chmod a+w '/home/%s/.python-eggs'""" % (user))

print """
You must populate the db manually. Run these:

cd '%s/r2'
sudo -u postgres paster shell example.ini

Run these in the pylons shell manually:
>>>from r2.models import populatedb
>>>populatedb.populate()


After that is done, you should be able to start the service by running:
paster serve --reload example.ini port=8080
""" % (repo_path)

