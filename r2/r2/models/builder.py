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
from account import *
from link import *
from vote import *
from report import *
from subreddit import SRMember, FakeSubreddit
from listing import Listing
from pylons import i18n, request, g
from pylons.i18n import _

import subreddit

from r2.lib.wrapped import Wrapped
from r2.lib import utils
from r2.lib.db import operators
from r2.lib.cache import sgm
from r2.lib.comment_tree import link_comments

from copy import deepcopy, copy

import time
from datetime import datetime,timedelta
from admintools import compute_votes, admintools

EXTRA_FACTOR = 1.5
MAX_RECURSION = 10

# Appends to the list "attrs" a tuple of:
# <priority (higher trumps lower), letter,
#  css class, i18n'ed mouseover label, hyperlink (or None)>
def add_attr(attrs, code, label=None, link=None):
    if code == 'F':
        priority = 1
        cssclass = 'friend'
        if not label:
            label = _('friend')
        if not link:
            link = '/prefs/friends'
    elif code == 'S':
        priority = 2
        cssclass = 'submitter'
        if not label:
            label = _('submitter')
        if not link:
            raise ValueError ("Need a link")
    elif code == 'M':
        priority = 3
        cssclass = 'moderator'
        if not label:
            raise ValueError ("Need a label")
        if not link:
            raise ValueError ("Need a link")
    elif code == 'A':
        priority = 4
        cssclass = 'admin'
        if not label:
            label = _('reddit admin, speaking officially')
        if not link:
            link = '/help/faq#Whomadereddit'
    else:
        raise ValueError ("Got weird code [%s]" % code)

    attrs.append( (priority, code, cssclass, label, link) )

class Builder(object):
    def __init__(self, wrap = Wrapped, keep_fn = None):
        self.wrap = wrap
        self.keep_fn = keep_fn

    def keep_item(self, item):
        if self.keep_fn:
            return self.keep_fn(item)
        else:
            return item.keep_item(item)

    def wrap_items(self, items):
        user = c.user if c.user_is_loggedin else None

        #get authors
        #TODO pull the author stuff into add_props for links and
        #comments and messages?
        try:
            aids = set(l.author_id for l in items)
        except AttributeError:
            aids = None

        authors = Account._byID(aids, True) if aids else {}
        # srids = set(l.sr_id for l in items if hasattr(l, "sr_id"))
        subreddits = Subreddit.load_subreddits(items)

        if not user:
            can_ban_set = set()
        else:
            can_ban_set = set(id for (id,sr) in subreddits.iteritems()
                              if sr.can_ban(user))

        #get likes/dislikes
        #TODO Vote.likes should accept empty lists
        likes = Vote.likes(user, items) if user and items else {}

        uid = user._id if user else None

        types = {}
        wrapped = []
        count = 0

        if isinstance(c.site, FakeSubreddit):
            mods = []
        else:
            mods = c.site.moderators
            modlink = ''
            if c.cname:
                modlink = '/about/moderators'
            else:
                modlink = '/r/%s/about/moderators' % c.site.name

            modlabel = (_('moderator of /r/%(reddit)s, speaking officially') %
                        dict(reddit = c.site.name) )


        for item in items:
            w = self.wrap(item)
            wrapped.append(w)
            # add for caching (plus it should be bad form to use _
            # variables in templates)
            w.fullname = item._fullname
            types.setdefault(w.render_class, []).append(w)

            #TODO pull the author stuff into add_props for links and
            #comments and messages?
            w.author = None
            w.friend = False

            # List of tuples <priority (higher trumps lower), letter,
            # css class, i18n'ed mouseover label, hyperlink (or None)>
            w.attribs = []

            w.distinguished = None
            if hasattr(item, "distinguished"):
                if item.distinguished == 'yes':
                    w.distinguished = 'moderator'
                elif item.distinguished == 'admin':
                    w.distinguished = 'admin'

            try:
                w.author = authors.get(item.author_id)
                if user and item.author_id in user.friends:
                        # deprecated old way:
                        w.friend = True
                        # new way:
                        add_attr(w.attribs, 'F')

            except AttributeError:
                pass

            if (w.distinguished == 'admin' and
                w.author and w.author.name in g.admins):
                add_attr(w.attribs, 'A')

            if (w.distinguished == 'moderator' and
                getattr(item, "author_id", None) in mods):
                add_attr(w.attribs, 'M', label=modlabel, link=modlink)

            if hasattr(item, "sr_id"):
                w.subreddit = subreddits[item.sr_id]

            vote = likes.get((user, item))
            if vote:
                w.likes = (True if vote._name == '1'
                             else False if vote._name == '-1'
                             else None)
            else:
                w.likes = None


            # update vote tallies
            compute_votes(w, item)
            
            w.score = w.upvotes - w.downvotes
            if w.likes:
                base_score = w.score - 1
            elif w.likes is None:
                base_score = w.score
            else:
                base_score = w.score + 1
            # store the set of available scores based on the vote
            # for ease of i18n when there is a label
            w.voting_score = [(base_score + x - 1) for x in range(3)]

            w.deleted = item._deleted

            w.rowstyle = getattr(w, 'rowstyle', "")
            w.rowstyle += ' ' + ('even' if (count % 2) else 'odd')

            count += 1

            # if the user can ban things on a given subreddit, or an
            # admin, then allow them to see that the item is spam, and
            # add the other spam-related display attributes
            w.show_reports = False
            w.show_spam    = False
            w.can_ban      = False
            if (c.user_is_admin
                or (user
                    and hasattr(item,'sr_id')
                    and item.sr_id in can_ban_set)):
                w.can_ban = True
                if item._spam:
                    w.show_spam = True
                    ban_info = getattr(item, 'ban_info', {})
                    w.moderator_banned = ban_info.get('moderator_banned', False)
                    w.autobanned = ban_info.get('auto', False)
                    w.banner = ban_info.get('banner')

                elif getattr(item, 'reported', 0) > 0:
                    w.show_reports = True

        # recache the user object: it may be None if user is not logged in,
        # whereas now we are happy to have the UnloggedUser object
        user = c.user
        for cls in types.keys():
            cls.add_props(user, types[cls])

        return wrapped

    def get_items(self):
        raise NotImplementedError

    def item_iter(self, *a):
        """Iterates over the items returned by get_items"""
        raise NotImplementedError

    def must_skip(self, item):
        """whether or not to skip any item regardless of whether the builder
        was contructed with skip=true"""
        user = c.user if c.user_is_loggedin else None
        if hasattr(item, 'subreddit') and not item.subreddit.can_view(user):
            return True

class QueryBuilder(Builder):
    def __init__(self, query, wrap = Wrapped, keep_fn = None,
                 skip = False, **kw):
        Builder.__init__(self, wrap, keep_fn)
        self.query = query
        self.skip = skip
        self.num = kw.get('num')
        self.start_count = kw.get('count', 0) or 0
        self.after = kw.get('after')
        self.reverse = kw.get('reverse')
        
        self.prewrap_fn = None
        if hasattr(query, 'prewrap_fn'):
            self.prewrap_fn = query.prewrap_fn
        #self.prewrap_fn = kw.get('prewrap_fn')

    def item_iter(self, a):
        """Iterates over the items returned by get_items"""
        for i in a[0]:
            yield i

    def init_query(self):
        q = self.query

        if self.reverse:
            q._reverse()

        q._data = True
        self.orig_rules = deepcopy(q._rules)
        if self.after:
            q._after(self.after)

    def fetch_more(self, last_item, num_have):
        done = False
        q = self.query
        if self.num:
            num_need = self.num - num_have
            if num_need <= 0:
                #will cause the loop below to break
                return True, None
            else:
                #q = self.query
                #check last_item if we have a num because we may need to iterate
                if last_item:
                    q._rules = deepcopy(self.orig_rules)
                    q._after(last_item)
                    last_item = None
                q._limit = max(int(num_need * EXTRA_FACTOR), 1)
        else:
            done = True
        new_items = list(q)

        return done, new_items

    def get_items(self):
        self.init_query()

        num_have = 0
        done = False
        items = []
        count = self.start_count
        first_item = None
        last_item = None
        have_next = True

        #for prewrap
        orig_items = {}

        #logloop
        self.loopcount = 0
        
        while not done:
            done, new_items = self.fetch_more(last_item, num_have)

            #log loop
            self.loopcount += 1
            if self.loopcount == 20:
                g.log.debug('BREAKING: %s' % self)
                done = True

            #no results, we're done
            if not new_items:
                break;

            #if fewer results than we wanted, we're done
            elif self.num and len(new_items) < self.num - num_have:
                done = True
                have_next = False

            if not first_item and self.start_count > 0:
                first_item = new_items[0]

            #pre-wrap
            if self.prewrap_fn:
                new_items2 = []
                for i in new_items:
                    new = self.prewrap_fn(i)
                    orig_items[new._id] = i
                    new_items2.append(new)
                new_items = new_items2

            #wrap
            if self.wrap:
                new_items = self.wrap_items(new_items)

            #skip and count
            while new_items and (not self.num or num_have < self.num):
                i = new_items.pop(0)
                count = count - 1 if self.reverse else count + 1
                if not (self.must_skip(i) or self.skip and not self.keep_item(i)):
                    items.append(i)
                    num_have += 1
                if self.wrap:
                    i.num = count
                last_item = i
        
            #unprewrap the last item
            if self.prewrap_fn and last_item:
                last_item = orig_items[last_item._id]

        if self.reverse:
            items.reverse()
            last_item, first_item = first_item, have_next and last_item
            before_count = count
            after_count = self.start_count - 1
        else:
            last_item = have_next and last_item
            before_count = self.start_count + 1
            after_count = count

        #listing is expecting (things, prev, next, bcount, acount)
        return (items,
                first_item,
                last_item,
                before_count,
                after_count)

class IDBuilder(QueryBuilder):
    def init_query(self):
        names = self.names = list(tup(self.query))

        if self.reverse:
            names.reverse()

        if self.after:
            try:
                i = names.index(self.after._fullname)
            except ValueError:
                self.names = ()
            else:
                self.names = names[i + 1:]

    def fetch_more(self, last_item, num_have):
        done = False
        names = self.names
        if self.num:
            num_need = self.num - num_have
            if num_need <= 0:
                return True, None
            else:
                if last_item:
                    last_item = None
                slice_size = max(int(num_need * EXTRA_FACTOR), 1)
        else:
            slice_size = len(names)
            done = True

        self.names, new_names = names[slice_size:], names[:slice_size]
        new_items = Thing._by_fullname(new_names, data = True, return_dict=False)

        return done, new_items

class SearchBuilder(QueryBuilder):
    def init_query(self):
        self.skip = True
        self.total_num = 0
        self.start_time = time.time()

        self.start_time = time.time()

    def keep_item(self,item):
        # doesn't use the default keep_item because we want to keep
        # things that were voted on, even if they've chosen to hide
        # them in normal listings
        if item._spam or item._deleted:
            return False
        else:
            return True


    def fetch_more(self, last_item, num_have):
        from r2.lib import solrsearch

        done = False
        limit = None
        if self.num:
            num_need = self.num - num_have
            if num_need <= 0:
                return True, None
            else:
                limit = max(int(num_need * EXTRA_FACTOR), 1)
        else:
            done = True

        search = self.query.run(after = last_item or self.after,
                                reverse = self.reverse,
                                num = limit)

        new_items = Thing._by_fullname(search.docs, data = True, return_dict=False)

        self.total_num = search.hits

        return done, new_items

class CommentBuilder(Builder):
    def __init__(self, link, sort, comment = None, context = None,
                 load_more=True, continue_this_thread=True,
                 max_depth = MAX_RECURSION, **kw):
        Builder.__init__(self, **kw)
        self.link = link
        self.comment = comment
        self.context = context
        self.load_more = load_more
        self.max_depth = max_depth
        self.continue_this_thread = continue_this_thread

        if sort.col == '_date':
            self.sort_key = lambda x: x._date
        else:
            self.sort_key = lambda x: (getattr(x, sort.col), x._date)
        self.rev_sort = True if isinstance(sort, operators.desc) else False

    def item_iter(self, a):
        for i in a:
            yield i
            if hasattr(i, 'child'):
                for j in self.item_iter(i.child.things):
                    yield j

    def get_items(self, num, starting_depth = 0):
        r = link_comments(self.link._id)
        cids, comment_tree, depth, num_children = r
        if cids:
            comments = set(Comment._byID(cids, data = True, 
                                         return_dict = False))
        else:
            comments = ()

        def empty_listing(*things):
            parent_name = None
            for t in things:
                try:
                    parent_name = t.parent_name
                    break
                except AttributeError:
                    continue
            l = Listing(None, None, parent_name = parent_name)
            l.things = list(things)
            return Wrapped(l)
            
        comment_dict = dict((cm._id, cm) for cm in comments)

        #convert tree into objects
        for k, v in comment_tree.iteritems():
            comment_tree[k] = [comment_dict[cid] for cid in comment_tree[k]]

        items = []
        extra = {}
        top = None
        dont_collapse = []
        #loading a portion of the tree
        if isinstance(self.comment, utils.iters):
            candidates = []
            candidates.extend(self.comment)
            dont_collapse.extend(cm._id for cm in self.comment)
            #assume the comments all have the same parent
            # TODO: removed by Chris to get rid of parent being sent
            # when morecomments is used.  
            #if hasattr(candidates[0], "parent_id"):
            #    parent = comment_dict[candidates[0].parent_id]
            #    items.append(parent)
        #if permalink
        elif self.comment:
            top = self.comment
            dont_collapse.append(top._id)
            #add parents for context
            while self.context > 0 and hasattr(top, 'parent_id'):
                self.context -= 1
                new_top = comment_dict[top.parent_id]
                comment_tree[new_top._id] = [top]
                num_children[new_top._id] = num_children[top._id] + 1
                dont_collapse.append(new_top._id)
                top = new_top
            candidates = [top]
        #else start with the root comments
        else:
            candidates = []
            candidates.extend(comment_tree.get(top, ()))

        #update the starting depth if required
        if top and depth[top._id] > 0:
            delta = depth[top._id]
            for k, v in depth.iteritems():
                depth[k] = v - delta

        def sort_candidates():
            candidates.sort(key = self.sort_key, reverse = self.rev_sort)
        
        #find the comments
        num_have = 0
        sort_candidates()
        while num_have < num and candidates:
            to_add = candidates.pop(0)
            comments.remove(to_add)
            if to_add._deleted and not comment_tree.has_key(to_add._id):
                pass
            elif depth[to_add._id] < self.max_depth:
                #add children
                if comment_tree.has_key(to_add._id):
                    candidates.extend(comment_tree[to_add._id])
                    sort_candidates()
                items.append(to_add)
                num_have += 1
            elif self.continue_this_thread:
                #add the recursion limit
                p_id = to_add.parent_id
                w = Wrapped(MoreRecursion(self.link, 0,
                                          comment_dict[p_id]))
                w.children.append(to_add)
                extra[p_id] = w

        wrapped = self.wrap_items(items)

        cids = dict((cm._id, cm) for cm in wrapped)
        
        final = []
        #make tree

        for cm in wrapped:
            # don't show spam with no children
            if cm.deleted and not comment_tree.has_key(cm._id):
                continue
            cm.num_children = num_children[cm._id]
            if cm.collapsed and cm._id in dont_collapse:
                cm.collapsed = False
            parent = cids.get(cm.parent_id) \
                if hasattr(cm, 'parent_id') else None
            if parent:
                if not hasattr(parent, 'child'):
                    parent.child = empty_listing()
                parent.child.parent_name = parent._fullname
                parent.child.things.append(cm)
            else:
                final.append(cm)

        #put the extras in the tree
        for p_id, morelink in extra.iteritems():
            parent = cids[p_id]
            parent.child = empty_listing(morelink)
            parent.child.parent_name = parent._fullname

        if not self.load_more:
            return final

        #put the remaining comments into the tree (the show more comments link)
        more_comments = {}
        while candidates:
            to_add = candidates.pop(0)
            direct_child = True
            #ignore top-level comments for now
            if not hasattr(to_add, 'parent_id'):
                p_id = None
            else:
                #find the parent actually being displayed
                #direct_child is whether the comment is 'top-level'
                p_id = to_add.parent_id
                while p_id and not cids.has_key(p_id):
                    p = comment_dict[p_id]
                    if hasattr(p, 'parent_id'):
                        p_id = p.parent_id
                    else:
                        p_id = None
                    direct_child = False

            mc2 = more_comments.get(p_id)
            if not mc2:
                mc2 = MoreChildren(self.link, depth[to_add._id],
                                   parent = comment_dict.get(p_id))
                more_comments[p_id] = mc2
                w_mc2 = Wrapped(mc2)
                if p_id is None:
                    final.append(w_mc2)
                else:
                    parent = cids[p_id]
                    if hasattr(parent, 'child'):
                        parent.child.things.append(w_mc2)
                    else:
                        parent.child = empty_listing(w_mc2)
                        parent.child.parent_name = parent._fullname

            #add more children
            if comment_tree.has_key(to_add._id):
                candidates.extend(comment_tree[to_add._id])
                
            if direct_child:
                mc2.children.append(to_add)

            mc2.count += 1

        return final

def make_wrapper(parent_wrapper = Wrapped, **params):
    def wrapper_fn(thing):
        w = parent_wrapper(thing)
        for k, v in params.iteritems():
            setattr(w, k, v)
        return w
    return wrapper_fn

class TopCommentBuilder(CommentBuilder):
    """A comment builder to fetch only the top-level, non-spam,
       non-deleted comments"""
    def __init__(self, link, sort, wrap = Wrapped):
        CommentBuilder.__init__(self, link, sort,
                                load_more = False,
                                continue_this_thread = False,
                                max_depth = 1, wrap = wrap)

    def get_items(self, num = 10):
        final = CommentBuilder.get_items(self, num = num, starting_depth = 0)
        return [ cm for cm in final if not cm.deleted ]
