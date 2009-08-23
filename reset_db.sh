#!/bin/sh
sudo -u postgres psql < reset_db.sql
sudo -u postgres createdb -E utf8 newreddit
sudo -u postgres createdb -E utf8 changed
sudo -u postgres createdb -E utf8 email
sudo -u postgres createdb -E utf8 query_queue
sudo -u postgres psql newreddit < sql/functions.sql
sudo /etc/init.d/memcached restart
