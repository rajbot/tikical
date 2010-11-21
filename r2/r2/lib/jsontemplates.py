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
from utils import to36, tup, iters
from wrapped import Wrapped, StringTemplate, CacheStub, CachedVariable, Templated
from mako.template import Template
from r2.lib.filters import spaceCompress, safemarkdown
import time, pytz
from pylons import c

def api_type(subtype = ''):
    return 'api-' + subtype if subtype else 'api'

def is_api(subtype = ''):
    return c.render_style and c.render_style.startswith(api_type(subtype))
    
def get_api_subtype():
    if is_api() and c.render_style.startswith('api-'):
        return c.render_style[4:]

def make_typename(typ):
    return 't%s' % to36(typ._type_id)

def make_fullname(typ, _id):
    return '%s_%s' % (make_typename(typ), to36(_id))


class ObjectTemplate(StringTemplate):
    def __init__(self, d):
        self.d = d
    
    def update(self, kw):
        def _update(obj):
            if isinstance(obj, (str, unicode)):
                return StringTemplate(obj).finalize(kw)
            elif isinstance(obj, dict):
                return dict((k, _update(v)) for k, v in obj.iteritems())
            elif isinstance(obj, (list, tuple)):
                return map(_update, obj)
            elif isinstance(obj, CacheStub) and kw.has_key(obj.name):
                r = kw[obj.name]
                if isinstance(r, (str, unicode)):
                    r = spaceCompress(r)
                return r    
            else:
                return obj
        res = _update(self.d)
        return ObjectTemplate(res)

    def finalize(self, kw = {}):
        return self.update(kw).d
    
class JsonTemplate(Template):
    def __init__(self): pass

    def render(self, thing = None, *a, **kw):
        return ObjectTemplate({})

class TableRowTemplate(JsonTemplate):
    def cells(self, thing):
        raise NotImplementedError
    
    def css_id(self, thing):
        return ""

    def css_class(self, thing):
        return ""

    def render(self, thing = None, *a, **kw):
        return ObjectTemplate(dict(id = self.css_id(thing),
                                   css_class = self.css_class(thing),
                                   cells = self.cells(thing)))

class UserItemJsonTemplate(TableRowTemplate):
    def cells(self, thing):
        cells = []
        for cell in thing.cells:
            thing.name = cell
            r = thing.part_render('cell_type', style = "html")
            cells.append(spaceCompress(r))
        return cells

    def css_id(self, thing):
        return thing.user._fullname

    def css_class(self, thing):
        return "thing"


class ThingJsonTemplate(JsonTemplate):
    _data_attrs_ = dict(id           = "_id36",
                        name         = "_fullname",
                        created      = "created",
                        created_utc  = "created_utc")

    @classmethod
    def data_attrs(cls, **kw):
        d = cls._data_attrs_.copy()
        d.update(kw)
        return d
    
    def kind(self, wrapped):
        """
        Returns a string literal which identifies the type of this
        thing.  For subclasses of Thing, it will be 't's + kind_id.
        """
        _thing = wrapped.lookups[0] if isinstance(wrapped, Wrapped) else wrapped
        return make_typename(_thing.__class__)

    def rendered_data(self, thing):
        """
        Called only when get_api_type is non-None (i.e., a JSON
        request has been made with partial rendering of the object to
        be returned)

        Canonical Thing data representation for JS, which is currently
        a dictionary of three elements (translated into a JS Object
        when sent out).  The elements are:

         * id : Thing _fullname of thing.
         * content : rendered  representation of the thing by
           calling render on it using the style of get_api_subtype().
        """
        res =  dict(id = thing._fullname,
                    content = thing.render(style=get_api_subtype()))
        return res
        
    def raw_data(self, thing):
        """
        Complement to rendered_data.  Called when a dictionary of
        thing data attributes is to be sent across the wire.
        """
        return dict((k, self.thing_attr(thing, v))
                    for k, v in self._data_attrs_.iteritems())
            
    def thing_attr(self, thing, attr):
        """
        For the benefit of subclasses, to lookup attributes which may
        require more work than a simple getattr (for example, 'author'
        which has to be gotten from the author_id attribute on most
        things).
        """
        if attr == "author":
            return thing.author.name
        elif attr == "created":
            return time.mktime(thing._date.timetuple())
        elif attr == "created_utc":
            return (time.mktime(thing._date.astimezone(pytz.UTC).timetuple())
                    - time.timezone)
        elif attr == "child":
            return CachedVariable("childlisting")
        return getattr(thing, attr, None)

    def data(self, thing):
        if get_api_subtype():
            return self.rendered_data(thing)
        else:
            return self.raw_data(thing)
        
    def render(self, thing = None, action = None, *a, **kw):
        return ObjectTemplate(dict(kind = self.kind(thing),
                                   data = self.data(thing)))
        
class SubredditJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(subscribers  = "score",
                                                title        = "title",
                                                url          = "path",
                                                over18       = "over_18", 
                                                description  = "description")

class AccountJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(name = "name",
                                                link_karma = "safe_karma",
                                                comment_karma = "comment_karma")

class LinkJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(ups          = "upvotes",
                                                downs        = "downvotes",
                                                score        = "score",
                                                saved        = "saved",
                                                clicked      = "clicked",
                                                hidden       = "hidden",
                                                likes        = "likes",
                                                domain       = "domain",
                                                title        = "title",
                                                url          = "url",
                                                author       = "author", 
                                                thumbnail    = "thumbnail",
                                                media        = "media_object",
                                                media_embed  = "media_embed",
                                                selftext     = "selftext",
                                                num_comments = "num_comments",
                                                subreddit    = "subreddit",
                                                subreddit_id = "subreddit_id")

    def thing_attr(self, thing, attr):
        from r2.lib.scraper import scrapers
        if attr == "media_embed":
           if (thing.media_object and
               not isinstance(thing.media_object, basestring)):
               scraper = scrapers[thing.media_object['type']]
               media_embed = scraper.media_embed(**thing.media_object)
               return dict(scrolling = media_embed.scrolling,
                           width = media_embed.width,
                           height = media_embed.height,
                           content = media_embed.content)
           return dict()
        elif attr == 'subreddit':
            return thing.subreddit.name
        elif attr == 'subreddit_id':
            return thing.subreddit._fullname
        elif attr == 'selftext':
            return safemarkdown(thing.selftext)
        return ThingJsonTemplate.thing_attr(self, thing, attr)

    def rendered_data(self, thing):
        d = ThingJsonTemplate.rendered_data(self, thing)
        d['sr'] = thing.subreddit._fullname
        return d



class CommentJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(ups          = "upvotes",
                                                downs        = "downvotes",
                                                replies      = "child",
                                                body         = "body",
                                                body_html    = "body_html",
                                                likes        = "likes",
                                                author       = "author", 
                                                link_id      = "link_id",
                                                sr_id        = "sr_id",
                                                parent_id    = "parent_id",
                                                )

    def thing_attr(self, thing, attr):
        from r2.models import Comment, Link, Subreddit
        if attr == 'link_id':
            return make_fullname(Link, thing.link_id)
        elif attr == 'sr_id':
            if hasattr(thing, attr):
                return make_fullname(Subreddit, thing.sr_id)
            return None
        elif attr == "parent_id":
            try:
                return make_fullname(Comment, thing.parent_id)
            except AttributeError:
                return make_fullname(Link, thing.link_id)
        elif attr == "body_html":
            return spaceCompress(safemarkdown(thing.body))
        return ThingJsonTemplate.thing_attr(self, thing, attr)

    def kind(self, wrapped):
        from r2.models import Comment
        return make_typename(Comment)

    def raw_data(self, thing):
        d = ThingJsonTemplate.raw_data(self, thing)
        if c.profilepage:
            d['link_title'] = thing.link.title
        return d

    def rendered_data(self, wrapped):
        d = ThingJsonTemplate.rendered_data(self, wrapped)
        d['replies'] = self.thing_attr(wrapped, 'child')
        d['contentText'] = self.thing_attr(wrapped, 'body')
        d['contentHTML'] = self.thing_attr(wrapped, 'body_html')
        d['link'] = self.thing_attr(wrapped, 'link_id')
        d['parent'] = self.thing_attr(wrapped, 'parent_id')
        return d

class MoreCommentJsonTemplate(CommentJsonTemplate):
    _data_attrs_ = dict(id           = "_id36",
                        name         = "_fullname")
    def kind(self, wrapped):
        return "more"

    def rendered_data(self, wrapped):
        return ThingJsonTemplate.rendered_data(self, wrapped)

class MessageJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(new          = "new",
                                                subject      = "subject",
                                                body         = "body",
                                                body_html    = "body_html",
                                                author       = "author",
                                                dest         = "dest",
                                                was_comment  = "was_comment",
                                                context      = "context", 
                                                created      = "created")

    def thing_attr(self, thing, attr):
        if attr == "was_comment":
            return hasattr(thing, "was_comment")
        elif attr == "context":
            return ("" if not hasattr(thing, "was_comment")
                    else thing.permalink + "?context=3")
        elif attr == "dest":
            return thing.to.name
        elif attr == "body_html":
            return safemarkdown(thing.body)
        return ThingJsonTemplate.thing_attr(self, thing, attr)

    def rendered_data(self, wrapped):
        from r2.models import Message
        try:
            parent_id = wrapped.parent_id
        except AttributeError:
            parent_id = None
        else:
            parent_id = make_fullname(Message, parent_id)
        d = ThingJsonTemplate.rendered_data(self, wrapped)
        d['parent'] = parent_id
        d['contentText'] = self.thing_attr(wrapped, 'body')
        d['contentHTML'] = self.thing_attr(wrapped, 'body_html')
        return d


class RedditJsonTemplate(JsonTemplate):
    def render(self, thing = None, *a, **kw):
        return ObjectTemplate(thing.content().render() if thing else {})

class PanestackJsonTemplate(JsonTemplate):
    def render(self, thing = None, *a, **kw):
        res = [t.render() for t in thing.stack if t] if thing else []
        res = [x for x in res if x]
        if not res:
            return {}
        return ObjectTemplate(res if len(res) > 1 else res[0] )

class NullJsonTemplate(JsonTemplate):
    def render(self, thing = None, *a, **kw):
        return ""

class ListingJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = dict(children = "things",
                        after = "after",
                        before = "before")
    
    def thing_attr(self, thing, attr):
        if attr == "things":
            res = []
            for a in thing.things:
                a.childlisting = False
                r = a.render()
                res.append(r)
            return res
        return ThingJsonTemplate.thing_attr(self, thing, attr)
        

    def rendered_data(self, thing):
        return self.thing_attr(thing, "things")
    
    def kind(self, wrapped):
        return "Listing"

class OrganicListingJsonTemplate(ListingJsonTemplate):
    def kind(self, wrapped):
        return "OrganicListing"

class TrafficJsonTemplate(JsonTemplate):
    def render(self, thing, *a, **kw):
        res = {}
        for ival in ("hour", "day", "month"):
            if hasattr(thing, ival + "_data"):
                res[ival] = [[time.mktime(date.timetuple())] + list(data)
                             for date, data in getattr(thing, ival+"_data")]
        return ObjectTemplate(res)
