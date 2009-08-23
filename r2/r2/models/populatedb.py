# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
# 
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
# 
# The Original Code is Reddit.
# 
# The Original Developer is the Initial Developer.  The Initial Developer of the
# Original Code is CondeNet, Inc.
# 
# All portions of the code written by CondeNet are Copyright (c) 2006-2009
# CondeNet, Inc. All Rights Reserved.
################################################################################
from r2.models import *
from r2.lib import promote
from r2.lib.utils import fetch_things2, link_from_url

import datetime
import string
import random
import urllib2

class PSTx(datetime.tzinfo):
	def utcoffset(self, dt):
		return datetime.timedelta(hours=8) + self.dst(dt)
	def _FirstSunday(self, dt):
		return dt+datetime.timedelta(days=(6-dt.weekday()))
	def dst(self, dt):
		dst_start = self._FirstSunday(datetime.datetime(dt.year, 3, 8, 2))
		dst_end = self._FirstSunday(datetime.datetime(dt.year, 11, 1, 1))
		if dst_start <= dt.replace(tzinfo=None) < dst_end:
			return datetime.timedelta(hours=1)
		else:
			return datetime.timedelta(hours=0)
	def tzname(self, dt):
		return self.dst(dt) == datetime.timedelta(hours=0) and 'PST' or 'PDT'

#  url=http%3A%2F%2Fsquidlist.com%2Fevents%2Flink%2FiCalendar.php
#
# #self.debug(c.name == 'VEVENT' and (c.decoded('summary'),c.decoded('description'),c.decoded('url'),c.decoded('transp'), c.decoded('dtstart'),c.decoded('categories')) or 'boo')
class icalendar(object):
    def sync(self, sr_name, sr_title, url, limit=None):
        a = list(Account._query(limit = 1))[0]
        try:
            sr = Subreddit._new(name = sr_name, title = sr_title, ip = '0.0.0.0', author_id = a._id)
            sr._commit()
        except SubredditExists:
            sr = Subreddit._by_name(name=sr_name)

        from icalendar import Calendar
        data = urllib2.urlopen(url).read()
        cal = Calendar.from_string(data)
	count = 0
        keys = ['summary', 'description', 'url', 'transp', 'dtstart', 'dtend', 'categories']
        events = [ ]
	pstx = PSTx()
        for c in cal.walk():
            count = count + 1
            if limit and count > limit:
                break
            if c.name == 'VEVENT':
                d = {}
                for k in keys:
                    d[k] = c.decoded(k)
                date = d['dtstart']
		if type(date) == datetime.date:
                    date = datetime.datetime(date.year, date.month, date.day)
		date = date.replace(tzinfo=pstx)
		#print date
                title = d['summary']
                url = d['url']
                links = link_from_url(url)
                if links:
                    #print 'already submitted %s' % title.encode('utf-8')
                    print 'already submitted %s' % links
                    continue
                user = a
                l = Link._submit(title, url, user, sr, '127.0.0.1', event_dt=date)


def populate(sr_name = 'tikical.com', sr_title = "tikical.com: social calendaring",
             num = 100):
    create_accounts(num)

    a = list(Account._query(limit = 1))[0]

    try:
        sr = Subreddit._new(name = sr_name, title = sr_title,
                            ip = '0.0.0.0', author_id = a._id)
        sr._commit()
    except SubredditExists:
        pass

    #create_links(num)
    
def create_accounts(num):
    for i in range(num):
        name_ext = ''.join([ random.choice(string.letters)
                             for x
                             in range(int(random.uniform(1, 10))) ])
        name = 'test_' + name_ext
        try:
            register(name, name)
        except AccountExists:
            pass

def create_links(num):
    accounts = list(Account._query(limit = num, data = True))
    subreddits = list(Subreddit._query(limit = num, data = True))
    import datetime
    d = datetime.datetime.utcnow()
    d = d - datetime.timedelta(microseconds=d.microsecond)
    for i in range(num):
        #id = random.uniform(1,100)
	id = random.choice(xrange(10))
        title = url = 'http://google.com/?q=' + str(id)
        links = link_from_url(url)
        if links:
		print 'already submitted %s' % link
		continue
        user = random.choice(accounts)
        sr = random.choice(subreddits)
        date = d + datetime.timedelta(days=i)
        l = Link._submit(title, url, user, sr, '127.0.0.1', date.isoformat())
        
        if random.choice(([False] * 50) + [True]):
            promote.promote(l)
            

def by_url_cache():
    q = Link._query(Link.c._spam == (True,False),
                    data = True,
                    sort = desc('_date'))
    for i, link in enumerate(fetch_things2(q)):
        if i % 100 == 0:
            print "%s..." % i
        link.set_url_cache()
