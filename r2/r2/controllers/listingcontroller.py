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
from reddit_base import RedditController, base_listing
from validator import *

from r2.models import *
from r2.lib.pages import *
from r2.lib.pages.things import wrap_links
from r2.lib.menus import NewMenu, TimeMenu, SortMenu, RecSortMenu, ControversyTimeMenu
from r2.lib.rising import get_rising
from r2.lib.wrapped import Wrapped
from r2.lib.normalized_hot import normalized_hot, get_hot
from r2.lib.recommendation import get_recommended
from r2.lib.db.thing import Query, Merge, Relations
from r2.lib.db import queries
from r2.lib.strings import Score
from r2.lib import organic
from r2.lib.jsontemplates import is_api
from r2.lib.solrsearch import SearchQuery
from r2.lib.utils import iters, check_cheating, timeago
from r2.lib import sup

from admin import admin_profile_query

from pylons.i18n import _

import random

class ListingController(RedditController):
    """Generalized controller for pages with lists of links."""

    # toggle skipping of links based on the users' save/hide/vote preferences
    skip = True

    # toggles showing numbers 
    show_nums = True

    # any text that should be shown on the top of the page
    infotext = None

    # builder class to use to generate the listing. if none, we'll try
    # to figure it out based on the query type
    builder_cls = None

    # page title
    title_text = ''

    # login box, subreddit box, submit box, etc, visible
    show_sidebar = True

    # class (probably a subclass of Reddit) to use to render the page.
    render_cls = Reddit

    #extra parameters to send to the render_cls constructor
    render_params = {}

    @property
    def menus(self):
        """list of menus underneat the header (e.g., sort, time, kind,
        etc) to be displayed on this listing page"""
        return []
    
    @base_listing
    def build_listing(self, num, after, reverse, count):
        """uses the query() method to define the contents of the
        listing and renders the page self.render_cls(..).render() with
        the listing as contents"""
        self.num = num
        self.count = count
        self.after = after
        self.reverse = reverse

        self.query_obj = self.query()
        self.builder_obj = self.builder()
        self.listing_obj = self.listing()
        content = self.content()
        res =  self.render_cls(content = content,
                               show_sidebar = self.show_sidebar, 
                               nav_menus = self.menus, 
                               title = self.title(),
                               infotext = self.infotext,
                               **self.render_params).render()
        return res


    def content(self):
        """Renderable object which will end up as content of the render_cls"""
        return self.listing_obj
        
    def query(self):
        """Query to execute to generate the listing"""
        raise NotImplementedError

    def builder(self):
        #store the query itself so it can be used elsewhere
        if self.builder_cls:
            builder_cls = self.builder_cls
        elif isinstance(self.query_obj, Query):
            builder_cls = QueryBuilder
        elif isinstance(self.query_obj, SearchQuery):
            builder_cls = SearchBuilder
        elif isinstance(self.query_obj, iters):
            builder_cls = IDBuilder
        elif isinstance(self.query_obj, queries.CachedResults):
            builder_cls = IDBuilder

        b = builder_cls(self.query_obj,
                        num = self.num,
                        skip = self.skip,
                        after = self.after,
                        count = self.count,
                        reverse = self.reverse,
                        keep_fn = self.keep_fn(),
                        wrap = self.builder_wrapper)

        return b

    def keep_fn(self):
        return None

    def listing(self):
        """Listing to generate from the builder"""
        listing = LinkListing(self.builder_obj, show_nums = self.show_nums)
        return listing.listing()

    def title(self):
        """Page <title>"""
        return _(self.title_text) + " : " + c.site.name

    def rightbox(self):
        """Contents of the right box when rendering"""
        pass

    builder_wrapper = staticmethod(default_thing_wrapper())

    def GET_listing(self, **env):
        return self.build_listing(**env)

class FixListing(object):
    """When sorting by hotness, computing a listing when the before/after
    link has a hottness of 0 is very slow. This class avoids drawing
    next/prev links when that will happen."""
    fix_listing = True

    def listing(self):
        listing = ListingController.listing(self)

        if not self.fix_listing:
            return listing

        #404 existing bad pages
        if self.after and self.after._hot == 0:
            self.abort404()

        #don't draw next/prev links for 
        if listing.things:
            if listing.things[-1]._hot == 0:
                listing.next = None

            if listing.things[0]._hot == 0:
                listing.prev = None

        return listing

class HotController(FixListing, ListingController):
    where = 'hot'

    def organic(self):
        o_links, pos = organic.organic_links(c.user)
        if o_links:
            # get links in proximity to pos
            l = min(len(o_links) - 3, 8)
            disp_links = [o_links[(i + pos) % len(o_links)] for i in xrange(-2, l)]

            b = IDBuilder(disp_links, wrap = self.builder_wrapper)
            o = OrganicListing(b,
                               org_links = o_links,
                               visible_link = o_links[pos],
                               max_num = self.listing_obj.max_num,
                               max_score = self.listing_obj.max_score).listing()

            if len(o.things) > 0:
                # only pass through a listing if the links made it
                # through our builder
                organic.update_pos(pos+1)

                return o


    def query(self):
        #no need to worry when working from the cache
        if g.use_query_cache or c.site == Default:
            self.fix_listing = False

        if c.site == Default:
            sr_ids = Subreddit.user_subreddits(c.user)
            return normalized_hot(sr_ids)
        #if not using the query_cache we still want cached front pages
        elif (not g.use_query_cache
              and not isinstance(c.site, FakeSubreddit)
              and self.after is None
              and self.count == 0):
            return [l._fullname for l in get_hot(c.site)]
        else:
            return c.site.get_links('hot', 'all')

    def content(self):
        # only send an organic listing for HTML rendering
        if (c.site == Default and c.render_style == "html"
            and (not c.user_is_loggedin
                 or (c.user_is_loggedin and c.user.pref_organic))):
            org = self.organic()
            if org:
                return PaneStack([org, self.listing_obj], css_class='spacer')
        return self.listing_obj

    def title(self):
        return c.site.title

    def GET_listing(self, **env):
        self.infotext = request.get.get('deleted') and strings.user_deleted
        return ListingController.GET_listing(self, **env)

class SavedController(ListingController):
    where = 'saved'
    skip = False
    title_text = _('saved')

    def query(self):
        return queries.get_saved(c.user)

    @validate(VUser())
    def GET_listing(self, **env):
        return ListingController.GET_listing(self, **env)

class ToplinksController(ListingController):
    where = 'toplinks'
    title_text = _('top scoring links')

    def query(self):
        return c.site.get_links('toplinks', 'all')

    def GET_listing(self, **env):
        return ListingController.GET_listing(self, **env)

class NewController(ListingController):
    where = 'new'
    title_text = _('newest submissions')

    @property
    def menus(self):
        return [NewMenu(default = self.sort)]

    def keep_fn(self):
        def keep(item):
            """Avoid showing links that are too young, to give time
            for things like the spam filter and thumbnail fetcher to
            act on them before releasing them into the wild"""
            wouldkeep = item.keep_item(item)
            if c.user_is_loggedin and (c.user_is_admin or item.subreddit.is_moderator(c.user)):
                # let admins and moderators see them regardless
                return wouldkeep
            elif wouldkeep and c.user_is_loggedin and c.user._id == item.author_id:
                # also let the author of the link see them
                return True
            elif item._date > timeago(g.new_incubation):
                # it's too young to show yet
                return False
            else:
                # otherwise, fall back to the regular logic (don't
                # show hidden links, etc)
                return wouldkeep

        return keep

    def query(self):
        if self.sort == 'rising':
            return get_rising(c.site)
        else:
            return c.site.get_links('new', 'all')

    @validate(sort = VMenu('controller', NewMenu))
    def GET_listing(self, sort, **env):
        self.sort = sort
        return ListingController.GET_listing(self, **env)

#copied from NewController
class UpcomingController(ListingController):
    where = 'upcoming'
    title_text = _('upcoming events')

    @property
    def menus(self):
        return [NewMenu(default = self.sort)]

    def keep_fn(self):
        def keep(item):
            """Avoid showing links that are too young, to give time
            for things like the spam filter and thumbnail fetcher to
            act on them before releasing them into the wild"""
            wouldkeep = item.keep_item(item)
            if c.user_is_loggedin and (c.user_is_admin or item.subreddit.is_moderator(c.user)):
                # let admins and moderators see them regardless
                return wouldkeep
            elif wouldkeep and c.user_is_loggedin and c.user._id == item.author_id:
                # also let the author of the link see them
                return True
            elif item._date > timeago(g.new_incubation):
                # it's too young to show yet
                return False
            else:
                # otherwise, fall back to the regular logic (don't
                # show hidden links, etc)
                return wouldkeep

        return keep

    def query(self):
        if self.sort == 'rising':
            return get_rising(c.site)
        else:
            return c.site.get_links('new', 'all')

    @validate(sort = VMenu('controller', NewMenu))
    def GET_listing(self, sort, **env):
        self.sort = sort
        return ListingController.GET_listing(self, **env)

class BrowseController(ListingController):
    where = 'browse'

    @property
    def menus(self):
        return [ControversyTimeMenu(default = self.time)]
    
    def query(self):
        return c.site.get_links(self.sort, self.time)

    # TODO: this is a hack with sort.
    @validate(sort = VOneOf('sort', ('top', 'controversial')),
              time = VMenu('where', ControversyTimeMenu))
    def GET_listing(self, sort, time, **env):
        self.sort = sort
        if sort == 'top':
            self.title_text = _('top scoring links')
        elif sort == 'controversial':
            self.title_text = _('most controversial links')
        self.time = time
        return ListingController.GET_listing(self, **env)


class RandomrisingController(ListingController):
    where = 'randomrising'
    title_text = _('you\'re really bored now, eh?')

    def query(self):
        links = get_rising(c.site)

        if not links:
            # just pull from the new page if the rising page isn't
            # populated for some reason
            links = c.site.get_links('new', 'all')
            if isinstance(links, Query):
                links._limit = 200
                links = [x._fullname for x in links]
        
        random.shuffle(links)

        return links

class ByIDController(ListingController):
    title_text = _('API')
    skip = False

    def query(self):
        return self.names

    @validate(links = VByName("names", thing_cls = Link, multiple = True))
    def GET_listing(self, links, **env):
        if not links:
            return self.abort404()
        self.names = [l._fullname for l in links]
        return ListingController.GET_listing(self, **env)


class RecommendedController(ListingController):
    where = 'recommended'
    title_text = _('recommended for you')
    
    @property
    def menus(self):
        return [RecSortMenu(default = self.sort)]
    
    def query(self):
        return get_recommended(c.user._id, sort = self.sort)
        
    @validate(VUser(),
              sort = VMenu("controller", RecSortMenu))
    def GET_listing(self, sort, **env):
        self.sort = sort
        return ListingController.GET_listing(self, **env)

class UserController(ListingController):
    render_cls = ProfilePage
    skip = False
    show_nums = False

    def title(self):
        titles = {'overview': _("overview for %(user)s"),
                  'comments': _("comments by %(user)s"),
                  'submitted': _("submitted by %(user)s"),
                  'liked': _("liked by %(user)s"),
                  'disliked': _("disliked by %(user)s"),
                  'hidden': _("hidden by %(user)s")}
        title = titles.get(self.where, _('profile for %(user)s')) \
            % dict(user = self.vuser.name, site = c.site.name)
        return title

    def query(self):
        q = None
        if self.where == 'overview':
            self.check_modified(self.vuser, 'overview')
            q = queries.get_overview(self.vuser, 'new', 'all')

        elif self.where == 'comments':
            sup.set_sup_header(self.vuser, 'commented')
            self.check_modified(self.vuser, 'commented')
            q = queries.get_comments(self.vuser, 'new', 'all')

        elif self.where == 'submitted':
            sup.set_sup_header(self.vuser, 'submitted')
            self.check_modified(self.vuser, 'submitted')
            q = queries.get_submitted(self.vuser, 'new', 'all')

        elif self.where in ('liked', 'disliked'):
            sup.set_sup_header(self.vuser, self.where)
            self.check_modified(self.vuser, self.where)
            if self.where == 'liked':
                q = queries.get_liked(self.vuser)
            else:
                q = queries.get_disliked(self.vuser)

        elif self.where == 'hidden':
            q = queries.get_hidden(self.vuser)

        elif c.user_is_admin:
            q = admin_profile_query(self.vuser, self.where, desc('_date'))

        if q is None:
            return self.abort404()

        return q 

    @validate(vuser = VExistingUname('username'))
    def GET_listing(self, where, vuser, **env):
        self.where = where

        # the validator will ensure that vuser is a valid account
        if not vuser:
            return self.abort404()

        # hide spammers profile pages
        if (not c.user_is_loggedin or 
            (c.user._id != vuser._id and not c.user_is_admin)) \
               and vuser._spam:
            return self.abort404()

        if (where not in ('overview', 'submitted', 'comments')
            and not votes_visible(vuser)):
            return self.abort404()

        check_cheating('user')
            
        self.vuser = vuser
        self.render_params = {'user' : vuser}
        c.profilepage = True

        return ListingController.GET_listing(self, **env)

    @validate(vuser = VExistingUname('username'))
    def GET_about(self, vuser):
        if not is_api() or not vuser:
            return self.abort404()
        return Reddit(content = Wrapped(vuser)).render()

class MessageController(ListingController):
    show_sidebar = False
    render_cls = MessagePage

    def title(self):
        return _('messages') + ': ' + _(self.where)

    @staticmethod
    def builder_wrapper(thing):
        if isinstance(thing, Comment):
            p = thing.make_permalink_slow()
            f = thing._fullname
            w = Wrapped(thing)
            w.render_class = Message
            w.to_id = c.user._id
            w.subject = _('comment reply')
            w.was_comment = True
            w.permalink, w._fullname = p, f
            return w
        else:
            return ListingController.builder_wrapper(thing)

    def query(self):
        if self.where == 'inbox':
            q = queries.get_inbox(c.user)

            #reset the inbox
            if c.have_messages and self.mark != 'false':
                c.user.msgtime = False
                c.user._commit()

        elif self.where == 'sent':
            q = queries.get_sent(c.user)

        return q

    @validate(VUser(),
              mark = VOneOf('mark',('true','false'), default = 'true'))
    def GET_listing(self, where, mark, **env):
        self.where = where
        self.mark = mark
        c.msg_location = where
        return ListingController.GET_listing(self, **env)

    @validate(VUser(),
              to = nop('to'),
              subject = nop('subject'),
              message = nop('message'),
              success = nop('success'))
    def GET_compose(self, to, subject, message, success):
        captcha = Captcha() if c.user.needs_captcha() else None
        content = MessageCompose(to = to, subject = subject,
                                 captcha = captcha, 
                                 message = message,
                                 success = success)
        return MessagePage(content = content).render()
    
class RedditsController(ListingController):
    render_cls = SubredditsPage

    def title(self):
        return _('reddits')

    def query(self):
        if self.where == 'banned' and c.user_is_admin:
            reddits = Subreddit._query(Subreddit.c._spam == True,
                                       sort = desc('_date'))
        else:
            reddits = Subreddit._query()
            if self.where == 'new':
                reddits._sort = desc('_date')
            else:
                reddits._sort = desc('_downs')
            if c.content_langs != 'all':
                reddits._filter(Subreddit.c.lang == c.content_langs)
            if not c.over18:
                reddits._filter(Subreddit.c.over_18 == False)
                
        return reddits
    def GET_listing(self, where, **env):
        self.where = where
        return ListingController.GET_listing(self, **env)

class MyredditsController(ListingController):
    render_cls = MySubredditsPage

    @property
    def menus(self):
        buttons = (NavButton(plurals.subscriber,  'subscriber'),
                    NavButton(plurals.contributor, 'contributor'),
                    NavButton(plurals.moderator,   'moderator'))

        return [NavMenu(buttons, base_path = '/reddits/mine/', default = 'subscriber', type = "flatlist")]

    def title(self):
        return _('reddits: ') + self.where

    def query(self):
        reddits = SRMember._query(SRMember.c._name == self.where,
                                  SRMember.c._thing2_id == c.user._id,
                                  #hack to prevent the query from
                                  #adding it's own date
                                  sort = (desc('_t1_ups'), desc('_t1_date')),
                                  eager_load = True,
                                  thing_data = True)
        reddits.prewrap_fn = lambda x: x._thing1
        return reddits

    def content(self):
        user = c.user if c.user_is_loggedin else None
        num_subscriptions = len(Subreddit.reverse_subscriber_ids(user))
        if self.where == 'subscriber' and num_subscriptions == 0:
            message = strings.sr_messages['empty']
        else:
            message = strings.sr_messages.get(self.where)

        stack = PaneStack()

        if message:
            stack.append(InfoBar(message=message))

        stack.append(self.listing_obj)
        
        return stack

    @validate(VUser())
    def GET_listing(self, where, **env):
        self.where = where
        return ListingController.GET_listing(self, **env)

class CommentsController(ListingController):
    title_text = _('comments')

    def query(self):
        q = Comment._query(Comment.c._spam == (True,False),
                           sort = desc('_date'))
        if not c.user_is_admin:
            q._filter(Comment.c._spam == False)

        return q
