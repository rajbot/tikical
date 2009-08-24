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
from __future__ import with_statement

from pylons import c, g
from pylons.i18n import _

from r2.lib.db.thing import Thing, Relation, NotFound
from account import Account
from printable import Printable
from r2.lib.db.userrel import UserRel
from r2.lib.db.operators import lower, or_, and_, desc
from r2.lib.memoize import memoize
from r2.lib.utils import tup, interleave_lists
from r2.lib.strings import strings, Score
from r2.lib.filters import _force_unicode

import os.path
import random

class SubredditExists(Exception): pass

class Subreddit(Thing, Printable):
    _defaults = dict(static_path = g.static_path,
                     stylesheet = None,
                     stylesheet_rtl = None,
                     stylesheet_contents = '',
                     stylesheet_hash     = '0',
                     firsttext = strings.firsttext,
                     header = None,
                     description = '',
                     allow_top = True,
                     images = {},
                     ad_file = os.path.join(g.static_path, 'ad_default.html'),
                     reported = 0,
                     valid_votes = 0,
                     show_media = False,
                     domain = None,
                     )
    sr_limit = 50

    @classmethod
    def _new(self, name, title, author_id, ip, lang = g.lang, type = 'public',
             over_18 = False, **kw):
        with g.make_lock('create_sr_' + name.lower()):
            try:
                sr = Subreddit._by_name(name)
                raise SubredditExists
            except NotFound:
                sr = Subreddit(name = name,
                               title = title,
                               lang = lang,
                               type = type,
                               over_18 = over_18,
                               author_id = author_id,
                               ip = ip,
                               allow_top = True,
                               **kw)
                sr._commit()

                #clear cache
                Subreddit._by_name(name, _update = True)
                return sr

    @classmethod
    @memoize('subreddit._by_name')
    def _by_name_cache(cls, name):
        q = cls._query(lower(cls.c.name) == name.lower(),
                       cls.c._spam == (True, False),
                       limit = 1)
        l = list(q)
        if l:
            return l[0]._id

    @classmethod
    def _by_name(cls, name, _update = False):
        #lower name here so there is only one cache
        name = name.lower()

        if name == 'friends':
            return Friends
        elif name == 'all':
            return All
        else:
            sr_id = cls._by_name_cache(name, _update = _update)
            if sr_id:
                return cls._byID(sr_id, True)
            else:
                raise NotFound, 'Subreddit %s' % name

    @classmethod
    @memoize('subreddit._by_domain')
    def _by_domain_cache(cls, name):
        q = cls._query(cls.c.domain == name,
                       cls.c.over_18 == (True, False),
                       limit = 1)
        l = list(q)
        if l:
            return l[0]._id

    @classmethod
    def _by_domain(cls, domain, _update = False):
        sr_id = cls._by_domain_cache(_force_unicode(domain).lower(),
                                     _update = _update)
        if sr_id:
            return cls._byID(sr_id, True)
        else:
            return None

    @property
    def moderators(self):
        return self.moderator_ids()

    @property
    def contributors(self):
        return self.contributor_ids()

    @property
    def banned(self):
        return self.banned_ids()

    @property
    def subscribers(self):
        return self.subscriber_ids()

    def can_comment(self, user):
        if c.user_is_admin:
            return True
        elif self.is_banned(user):
            return False
        elif self.type in ('public','restricted'):
            return True
        elif self.is_moderator(user) or self.is_contributor(user):
            #private requires contributorship
            return True
        else:
            return False

    def can_submit(self, user):
        if c.user_is_admin:
            return True
        elif self.is_banned(user):
            return False
        elif self.type == 'public':
            return True
        elif self.is_moderator(user) or self.is_contributor(user):
            #restricted/private require contributorship
            return True
        else:
            return False

    def can_ban(self,user):
        return (user
                and (c.user_is_admin
                     or self.is_moderator(user)))

    def can_distinguish(self,user):
        return (user
                and (c.user_is_admin
                     or self.is_moderator(user)))

    def can_change_stylesheet(self, user):
        if c.user_is_loggedin:
            return c.user_is_admin or self.is_moderator(user)
        else:
            return False

    def is_special(self, user):
        return (user
                and (c.user_is_admin
                     or self.is_moderator(user)
                     or (self.type in ('restricted', 'private')
                         and self.is_contributor(user))))

    def can_give_karma(self, user):
        return self.is_special(user)

    def should_ratelimit(self, user, kind):
        if c.user_is_admin:
            return False

        if kind == 'comment':
            rl_karma = g.MIN_RATE_LIMIT_COMMENT_KARMA
        else:
            rl_karma = g.MIN_RATE_LIMIT_KARMA
            
        return not (self.is_special(user) or 
                    user.karma(kind, self) >= rl_karma)

    def can_view(self, user):
        if c.user_is_admin:
            return True

        if self.type in ('public', 'restricted'):
            return True
        elif c.user_is_loggedin:
            #private requires contributorship
            return self.is_contributor(user) or self.is_moderator(user)

    @classmethod
    def load_subreddits(cls, links, return_dict = True):
        """returns the subreddits for a list of links. it also preloads the
        permissions for the current user."""
        srids = set(l.sr_id for l in links if hasattr(l, "sr_id"))
        subreddits = {}
        if srids:
            subreddits = cls._byID(srids, True)

        if subreddits and c.user_is_loggedin:
            # dict( {Subreddit,Account,name} -> Relationship )
            SRMember._fast_query(subreddits.values(), (c.user,),
                                 ('subscriber','contributor','moderator'))

        return subreddits if return_dict else subreddits.values()

    #rising uses this to know which subreddits to include, doesn't
    #work for all/friends atm
    def rising_srs(self):
        if c.default_sr or not hasattr(self, '_id'):
            user = c.user if c.user_is_loggedin else None
            sr_ids = self.user_subreddits(user)
        else:
            sr_ids = (self._id,)
        return sr_ids

    def get_links(self, sort, time):
        from r2.lib.db import queries
        return queries.get_links(self, sort, time)

    def get_spam(self):
        from r2.lib.db import queries
        return queries.get_spam(self)

    def get_reported(self):
        from r2.lib.db import queries
        return queries.get_reported(self)

    @classmethod
    def add_props(cls, user, wrapped):
        names = ('subscriber', 'moderator', 'contributor')
        rels = (SRMember._fast_query(wrapped, [user], names) if c.user_is_loggedin else {})
        defaults = Subreddit.default_subreddits()
        for item in wrapped:
            if not user or not user.has_subscribed:
                item.subscriber = item._id in defaults
            else:
                item.subscriber = bool(rels.get((item, user, 'subscriber')))
            item.moderator = bool(rels.get((item, user, 'moderator')))
            item.contributor = bool(item.moderator or \
                                    rels.get((item, user, 'contributor')))
            item.score = item._ups
            # override "voting" score behavior (it will override the use of
            # item.score in builder.py to be ups-downs)
            item.likes = item.subscriber or None
            base_score = item.score - (1 if item.likes else 0)
            item.voting_score = [(base_score + x - 1) for x in range(3)]
            item.score_fmt = Score.subscribers
        Printable.add_props(user, wrapped)
    #TODO: make this work
    cache_ignore = set(["subscribers"]).union(Printable.cache_ignore)
    @staticmethod
    def wrapped_cache_key(wrapped, style):
        s = Printable.wrapped_cache_key(wrapped, style)
        s.extend([wrapped._spam])
        return s

    @classmethod
    def top_lang_srs(cls, lang, limit):
        """Returns the default list of subreddits for a given language, sorted
        by popularity"""
        pop_reddits = Subreddit._query(Subreddit.c.type == ('public',
                                                            'restricted'),
                                       sort=desc('_downs'),
                                       limit = limit * 1.5 if limit else None,
                                       data = True,
                                       read_cache = True,
                                       write_cache = True,
                                       cache_time = g.page_cache_time)
        if lang != 'all':
            pop_reddits._filter(Subreddit.c.lang == lang)

        if not c.over18:
            pop_reddits._filter(Subreddit.c.over_18 == False)

        # evaluate the query and remove the ones with
        # allow_top==False.  Note that because this filtering is done
        # after the query is run, if there are a lot of top reddits
        # with allow_top==False, we may return fewer than `limit`
        # results.
        srs = filter(lambda sr: sr.allow_top, pop_reddits)

        return srs[:limit] if limit else srs

    @classmethod
    def default_subreddits(cls, ids = True, limit = g.num_default_reddits):
        """
        Generates a list of the subreddits any user with the current
        set of language preferences and no subscriptions would see.

        An optional kw argument 'limit' is defaulted to g.num_default_reddits
        """
        srs = cls.top_lang_srs(c.content_langs, limit)
        return [s._id for s in srs] if ids else srs

    @classmethod
    @memoize('random_reddits', time = 1800)
    def random_reddits(cls, user_name, sr_ids, limit):
        """This gets called when a user is subscribed to more than 50
        reddits. Randomly choose 50 of those reddits and cache it for
        a while so their front page doesn't jump around."""
        return random.sample(sr_ids, limit)

    @classmethod
    def user_subreddits(cls, user, ids = True, limit = sr_limit):
        """
        subreddits that appear in a user's listings. If the user has
        subscribed, returns the stored set of subscriptions.

        Otherwise, return the default set.
        """
        # note: for user not logged in, the fake user account has
        # has_subscribed == False by default.
        if user and user.has_subscribed:
            sr_ids = Subreddit.reverse_subscriber_ids(user)
            if limit and len(sr_ids) > limit:
                sr_ids.sort()
                sr_ids = cls.random_reddits(user.name, sr_ids, limit)
            return sr_ids if ids else Subreddit._byID(sr_ids, True, False)
        else:
            # if there is a limit, we want *at most* limit subreddits.
            # Allow the default_subreddit list to return the number it
            # would normally and then slice.
            srs = cls.default_subreddits(ids = ids)
            if limit:
                srs = srs[:limit]
            return srs
            
    def is_subscriber_defaults(self, user):
        if user.has_subscribed:
            return self.is_subscriber(user)
        else:
            return self in self.default_subreddits(ids = False)

    @classmethod
    def subscribe_defaults(cls, user):
        if not user.has_subscribed:
            for sr in cls.user_subreddits(None, False,
                                          limit = g.num_default_reddits):
                #this will call reverse_subscriber_ids after every
                #addition. if it becomes a problem we should make an
                #add_multiple_subscriber fn
                if sr.add_subscriber(c.user):
                    sr._incr('_ups', 1)
            user.has_subscribed = True
            user._commit()

    @classmethod
    def submit_sr_names(cls, user):
        """subreddit names that appear in a user's submit page. basically a
        sorted/rearranged version of user_subreddits()."""
        srs = cls.user_subreddits(user, ids = False)
        names = [s.name for s in srs if s.can_submit(user)]
        names.sort()

        #add the current site to the top (default_sr)
        if g.default_sr in names:
            names.remove(g.default_sr)
            names.insert(0, g.default_sr)

        if c.lang in names:
            names.remove(c.lang)
            names.insert(0, c.lang)

        return names

    @property
    def path(self):
        return "/r/%s/" % self.name


    def keep_item(self, wrapped):
        if c.user_is_admin:
            return True

        user = c.user if c.user_is_loggedin else None
        return self.can_view(user)

    def get_images(self):
        """
        Iterator over list of (name, image_num) pairs which have been
        uploaded for custom styling of this subreddit.
        """
        for name, img_num in self.images.iteritems():
            if isinstance(img_num, int):
                yield (name, img_num)

    def add_image(self, name, max_num = None):
        """
        Adds an image to the subreddit's image list.  The resulting
        number of the image is returned.  Note that image numbers are
        non-sequential insofar as unused numbers in an existing range
        will be populated before a number outside the range is
        returned.  Imaged deleted with del_image are pushed onto the
        "/empties/" stack in the images dict, and those values are
        pop'd until the stack is empty.

        raises ValueError if the resulting number is >= max_num.

        The Subreddit will be _dirty if a new image has been added to
        its images list, and no _commit is called.
        """
        if not self.images.has_key(name):
            # copy and blank out the images list to flag as _dirty
            l = self.images
            self.images = None
            # initialize the /empties/ list 
            l.setdefault('/empties/', [])
            try:
                num = l['/empties/'].pop() # grab old number if we can
            except IndexError:
                num = len(l) - 1 # one less to account for /empties/ key
            if max_num is not None and num >= max_num:
                raise ValueError, "too many images"
            # update the dictionary and rewrite to images attr
            l[name] = num
            self.images = l
        else:
            # we've seen the image before, so just return the existing num
            num = self.images[name]
        return num

    def del_image(self, name):
        """
        Deletes an image from the images dictionary assuming an image
        of that name is in the current dictionary.  The freed up
        number is pushed onto the /empties/ stack for later recycling
        by add_image.

        The Subreddit will be _dirty if image has been removed from
        its images list, and no _commit is called.
        """
        if self.images.has_key(name):
            l = self.images
            self.images = None
            l.setdefault('/empties/', [])
            # push the number on the empties list
            l['/empties/'].append(l[name])
            del l[name]
            self.images = l

class FakeSubreddit(Subreddit):
    over_18 = False
    _nodb = True

    def __init__(self):
        Subreddit.__init__(self)
        self.title = ''

    def is_moderator(self, user):
        return c.user_is_loggedin and c.user_is_admin

    def can_view(self, user):
        return True

    def can_comment(self, user):
        return False

    def can_submit(self, user):
        return False

    def can_change_stylesheet(self, user):
        return False

    def is_banned(self, user):
        return False

class FriendsSR(FakeSubreddit):
    name = 'friends'
    title = 'friends'

    def get_links(self, sort, time):
        from r2.lib.db import queries
        from r2.models import Link
        from r2.controllers.errors import UserRequiredException

        if not c.user_is_loggedin:
            raise UserRequiredException

        q = Link._query(Link.c.author_id == c.user.friends,
                        sort = queries.db_sort(sort))
        if time != 'all':
            q._filter(queries.db_times[time])
        return q
            
class AllSR(FakeSubreddit):
    name = 'all'
    title = 'all'

    def get_links(self, sort, time):
        from r2.models import Link
        from r2.lib.db import queries
        q = Link._query(sort = queries.db_sort(sort))
        if time != 'all':
            q._filter(queries.db_times[time])
        return q

    def rising_srs(self):
        return None


class DefaultSR(FakeSubreddit):
    #notice the space before reddit.com
    name = ' tikical.com'
    path = '/'
    header = 'http://tikical.com:8080/static/tikical.com.header.png'

    def get_links_sr_ids(self, sr_ids, sort, time):
        from r2.lib.db import queries
        from r2.models import Link

        if not sr_ids:
            return []
        else:
            srs = Subreddit._byID(sr_ids, return_dict = False)

        if g.use_query_cache:
            results = []
            for sr in srs:
                results.append(queries.get_links(sr, sort, time))
            return queries.merge_cached_results(*results)
        else:
            q = Link._query(Link.c.sr_id == sr_ids,
                            sort = queries.db_sort(sort))
            if sort == 'toplinks':
                q._filter(Link.c.top_link == True)
            if time != 'all':
                q._filter(queries.db_times[time])
            return q

    def get_links(self, sort, time):
        user = c.user if c.user_is_loggedin else None
        sr_ids = Subreddit.user_subreddits(user)
        return self.get_links_sr_ids(sr_ids, sort, time)

    @property
    def title(self):
        return _("reddit.com: what's new online!")

class MultiReddit(DefaultSR):
    name = 'multi'

    def __init__(self, sr_ids, path):
        DefaultSR.__init__(self)
        self.real_path = path
        self.sr_ids = sr_ids

    @property
    def path(self):
        return '/r/' + self.real_path

    def get_links(self, sort, time):
        return self.get_links_sr_ids(self.sr_ids, sort, time)

    def rising_srs(self):
        return self.sr_ids


class SubSR(FakeSubreddit):
    stylesheet = 'subreddit.css'
    #this will make the javascript not send an SR parameter
    name = ''

    def can_view(self, user):
        return True

    def can_comment(self, user):
        return False

    def can_submit(self, user):
        return True

    @property
    def path(self):
        return "/reddits/"

class DomainSR(FakeSubreddit):
    @property
    def path(self):
        return '/domain/' + self.domain

    def __init__(self, domain):
        FakeSubreddit.__init__(self)
        self.domain = domain
        self.name = domain 
        self.title = domain + ' ' + _('on reddit.com')

    def get_links(self, sort, time):
        from r2.lib.db import queries
        return queries.get_domain_links(self.domain, sort, time)
        
Sub = SubSR()
Friends = FriendsSR()
All = AllSR()
Default = DefaultSR()

class SRMember(Relation(Subreddit, Account)): pass
Subreddit.__bases__ += (UserRel('moderator', SRMember),
                        UserRel('contributor', SRMember),
                        UserRel('subscriber', SRMember, disable_ids_fn = True),
                        UserRel('banned', SRMember))
