
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
from wrapped import CachedTemplate, Styled
from pylons import c, request, g
from utils import  query_string, timeago
from strings import StringHandler, plurals
from r2.lib.db import operators
from r2.lib.filters import _force_unicode
from pylons.i18n import _



class MenuHandler(StringHandler):
    """Bastard child of StringHandler and plurals.  Menus are
    typically a single word (and in some cases, a single plural word
    like 'moderators' or 'contributors' so this class first checks its
    own dictionary of string translations before falling back on the
    plurals list."""
    def __getattr__(self, attr):
        try:
            return StringHandler.__getattr__(self, attr)
        except KeyError:
            return getattr(plurals, attr)

# selected menu styles, primarily used on the main nav bar
menu_selected=StringHandler(hot          = _("what's hot"),
                            new          = _("what's new"),
                            top          = _("top scoring"),
                            controversial= _("most controversial"),
                            saved        = _("saved"),
                            recommended  = _("recommended"),
                            promote      = _('promote'),
                            upcoming     = _('upcoming'),
                            )

# translation strings for every menu on the site
menu =   MenuHandler(hot          = _('hot'),
                     new          = _('new'),
                     old          = _('old'),
                     ups          = _('ups'),
                     downs        = _('downs'),
                     top          = _('top'),
                     more         = _('more'),
                     relevance    = _('relevance'),
                     controversial  = _('controversial'),
                     saved        = _('saved {toolbar}'),
                     recommended  = _('recommended'),
                     rising       = _('rising'), 
                     admin        = _('admin'), 
                     upcoming     = _('upcoming'), 
                     
                     # time sort words
                     hour         = _('this hour'),
                     day          = _('today'),
                     week         = _('this week'),
                     month        = _('this month'),
                     year         = _('this year'),
                     all          = _('all time'),
                                  
                     # "kind" words
                     spam         = _("spam"),
                     autobanned   = _("autobanned"),

                     # reddit header strings
                     adminon      = _("turn admin on"),
                     adminoff     = _("turn admin off"), 
                     prefs        = _("preferences"), 
                     stats        = _("stats"), 
                     submit       = _("submit"),
                     help         = _("help"),
                     blog         = _("the reddit blog"),
                     logout       = _("logout"),
                     
                     #reddit footer strings
                     feedback     = _("feedback"),
                     bookmarklets = _("bookmarklets"),
                     socialite    = _("socialite firefox extension"),
                     buttons      = _("buttons"),
                     widget       = _("widget"), 
                     code         = _("source code"),
                     mobile       = _("mobile"), 
                     store        = _("store"),  
                     ad_inq       = _("advertise on reddit"),
                     toplinks     = _("top links"),
                     random       = _('random'),
                     iphone       = _("iPhone app"),

                     #preferences
                     options      = _('options'),
                     friends      = _("friends"),
                     update       = _("password/email"),
                     delete       = _("delete"),

                     # messages
                     compose      = _("compose"),
                     inbox        = _("inbox"),
                     sent         = _("sent"),

                     # comments
                     related      = _("related"),
                     details      = _("details"),
                     duplicates   = _("other discussions (%(num)s)"),
                     shirt        = _("shirt"),
                     traffic      = _("traffic"),

                     # reddits
                     home         = _("home"),
                     about        = _("about"),
                     edit         = _("edit"),
                     banned       = _("banned"),
                     banusers     = _("ban users"),

                     popular      = _("popular"),
                     create       = _("create"),
                     mine         = _("my reddits"),

                     i18n         = _("translate site"),
                     promoted     = _("promoted"),
                     reporters    = _("reporters"),
                     reports      = _("reports"),
                     reportedauth = _("reported authors"),
                     info         = _("info"),
                     share        = _("share"),

                     overview     = _("overview"),
                     submitted    = _("submitted"),
                     liked        = _("liked"),
                     disliked     = _("disliked"),
                     hidden       = _("hidden {toolbar}"),
                     deleted      = _("deleted"),
                     reported     = _("reported"),

                     promote      = _('promote'),
                     new_promo    = _('new promoted link'),
                     current_promos = _('promoted links'),
                     )

def menu_style(type):
    """Simple manager function for the styled menus.  Returns a
    (style, css_class) pair given a 'type', defaulting to style =
    'dropdown' with no css_class."""
    default = ('dropdown', '')
    d = dict(heavydrop = ('dropdown', 'heavydrop'),
             lightdrop = ('dropdown', 'lightdrop'),
             tabdrop = ('dropdown', 'tabdrop'),
             srdrop = ('dropdown', 'srdrop'),
             flatlist =  ('flatlist', 'flat-list'),
             tabmenu = ('tabmenu', ''),
             formtab = ('tabmenu', 'formtab'),
             flat_vert = ('flatlist', 'flat-vert'),
             )
    return d.get(type, default)

class NavMenu(Styled):
    """generates a navigation menu.  The intention here is that the
    'style' parameter sets what template/layout to use to differentiate, say,
    a dropdown from a flatlist, while the optional _class, and _id attributes
    can be used to set individualized CSS."""

    def __init__(self, options, default = None, title = '', type = "dropdown",
                 base_path = '', separator = '|', **kw):
        self.options = options
        self.base_path = base_path
        kw['style'], kw['css_class'] = menu_style(type)

        #used by flatlist to delimit menu items
        self.separator = separator

        # since the menu contains the path info, it's buttons need a
        # configuration pass to get them pointing to the proper urls
        for opt in self.options:
            opt.build(self.base_path)

        # selected holds the currently selected button defined as the
        # one whose path most specifically matches the current URL
        # (possibly None)
        self.default = default
        self.selected = self.find_selected()

        Styled.__init__(self, title = title, **kw)

    def find_selected(self):
        maybe_selected = [o for o in self.options if o.is_selected()]
        if maybe_selected:
            # pick the button with the most restrictive pathing
            maybe_selected.sort(lambda x, y:
                                len(y.bare_path) - len(x.bare_path))
            return maybe_selected[0]
        elif self.default:
            #lookup the menu with the 'dest' that matches 'default'
            for opt in self.options:
                if opt.dest == self.default:
                    return opt

    def __iter__(self):
        for opt in self.options:
            yield opt

class NavButton(Styled):
    """Smallest unit of site navigation.  A button once constructed
    must also have its build() method called with the current path to
    set self.path.  This step is done automatically if the button is
    passed to a NavMenu instance upon its construction."""
    def __init__(self, title, dest, sr_path = True, 
                 nocname=False, opt = '', aliases = [],
                 target = "", style = "plain", **kw):
        # keep original dest to check against c.location when rendering
        aliases = set(a.rstrip('/') for a in aliases)
        aliases.add(dest.rstrip('/'))

        self.request_params = dict(request.GET)
        self.stripped_path = request.path.rstrip('/').lower()

        Styled.__init__(self, style = style, sr_path = sr_path, 
                        nocname = nocname, target = target,
                        aliases = aliases, dest = dest,
                        selected = False, 
                        title = title, opt = opt, **kw)

    def build(self, base_path = ''):
        '''Generates the href of the button based on the base_path provided.'''

        # append to the path or update the get params dependent on presence
        # of opt 
        if self.opt:
            p = self.request_params.copy()
            p[self.opt] = self.dest
        else:
            p = {}
            base_path = ("%s/%s/" % (base_path, self.dest)).replace('//', '/')

        self.bare_path = _force_unicode(base_path.replace('//', '/')).lower()
        self.bare_path = self.bare_path.rstrip('/')
        
        # append the query string
        base_path += query_string(p)
        
        # since we've been sloppy of keeping track of "//", get rid
        # of any that may be present
        self.path = base_path.replace('//', '/')

    def is_selected(self):
        """Given the current request path, would the button be selected."""
        if self.opt:
            return self.request_params.get(self.opt, '') in self.aliases
        else:
            if self.stripped_path == self.bare_path:
                return True
            if self.stripped_path in self.aliases:
                return True

    def selected_title(self):
        """returns the title of the button when selected (for cases
        when it is different from self.title)"""
        return self.title

class OffsiteButton(NavButton):
    def build(self, base_path = ''):
        self.sr_path = False
        self.path = self.bare_path = self.dest

    def cachable_attrs(self):
        return [('path', self.path), ('title', self.title)]

class SubredditButton(NavButton):
    def __init__(self, sr):
        self.path = sr.path
        NavButton.__init__(self, sr.name, sr.path, False,
                           isselected = (c.site == sr))

    def build(self, base_path = ''):
        pass

    def is_selected(self):
        return self.isselected

    def cachable_attrs(self):
        return [('path', self.path), ('title', self.title),
                ('isselected', self.isselected)]

class NamedButton(NavButton):
    """Convenience class for handling the majority of NavButtons
    whereby the 'title' is just the translation of 'name' and the
    'dest' defaults to the 'name' as well (unless specified
    separately)."""
    
    def __init__(self, name, sr_path = True, nocname=False, dest = None, fmt_args = {}, **kw):
        self.name = name.strip('/')
        menutext = menu[self.name] % fmt_args
        NavButton.__init__(self, menutext, name if dest is None else dest,
                           sr_path = sr_path, nocname=nocname, **kw)

    def selected_title(self):
        """Overrides selected_title to use menu_selected dictionary"""
        try:
            return menu_selected[self.name]
        except KeyError:
            return NavButton.selected_title(self)



class JsButton(NavButton):
    """A button which fires a JS event and thus has no path and cannot
    be in the 'selected' state"""
    def __init__(self, title, style = 'js', **kw):
        NavButton.__init__(self, title, '#', style = style, **kw)

    def build(self, *a, **kw):
        self.path = 'javascript:void(0)'

    def is_selected(self):
        return False

class PageNameNav(Styled):
    """generates the links and/or labels which live in the header
    between the header image and the first nav menu (e.g., the
    subreddit name, the page name, etc.)"""
    pass

class SimpleGetMenu(NavMenu):
    """Parent class of menus used for sorting and time sensitivity of
    results.  More specifically, defines a type of menu which changes
    the url by adding a GET parameter with name 'get_param' and which
    defaults to 'default' (both of which are class-level parameters).

    The value of the GET parameter must be one of the entries in
    'cls.options'.  This parameter is also used to construct the list
    of NavButtons contained in this Menu instance.  The goal here is
    to have a menu object which 'out of the box' is self validating."""
    options   = []
    get_param = ''
    title     = ''
    default = None
    type = 'lightdrop'
    
    def __init__(self, **kw):
        buttons = [NavButton(self.make_title(n), n, opt = self.get_param)
                   for n in self.options]
        kw['default'] = kw.get('default', self.default)
        kw['base_path'] = kw.get('base_path') or request.path
        NavMenu.__init__(self, buttons, type = self.type, **kw)
    
    def make_title(self, attr):
        return menu[attr]

    @classmethod
    def operator(self, sort):
        """Converts the opt into a DB-esque operator used for sorting results"""
        return None

class SortMenu(SimpleGetMenu):
    """The default sort menu."""
    get_param = 'sort'
    default   = 'hot'
    options   = ('hot', 'new', 'top', 'old', 'controversial')

    def __init__(self, **kw):
        kw['title'] = _("sorted by")
        SimpleGetMenu.__init__(self, **kw)
    
    @classmethod
    def operator(self, sort):
        if sort == 'hot':
            return operators.desc('_hot')
        elif sort == 'new':
            return operators.desc('_date')
        elif sort == 'old':
            return operators.asc('_date')
        elif sort == 'top':
            return operators.desc('_score')
        elif sort == 'controversial':
            return operators.desc('_controversy')

class CommentSortMenu(SortMenu):
    """Sort menu for comments pages"""
    options   = ('hot', 'new', 'controversial', 'top', 'old')

class SearchSortMenu(SortMenu):
    """Sort menu for search pages."""
    default   = 'relevance'
    mapping   = dict(relevance = 'score desc',
                     hot = 'hot desc',
                     new = 'date desc',
                     old = 'date asc',
                     top = 'points desc')
    options   = mapping.keys()

    @classmethod
    def operator(cls, sort):
        return cls.mapping.get(sort, cls.mapping[cls.default])

class RecSortMenu(SortMenu):
    """Sort menu for recommendation page"""
    default   = 'new'
    options   = ('hot', 'new', 'top', 'controversial', 'relevance')

class NewMenu(SimpleGetMenu):
    get_param = 'sort'
    default   = 'rising'
    options   = ('new', 'rising')
    type = 'flatlist'

    def __init__(self, **kw):
        kw['title'] = ""
        SimpleGetMenu.__init__(self, **kw)

    @classmethod
    def operator(self, sort):
        if sort == 'new':
            return operators.desc('_date')
        

class KindMenu(SimpleGetMenu):
    get_param = 'kind'
    default = 'all'
    options = ('links', 'comments', 'messages', 'all')

    def __init__(self, **kw):
        kw['title'] = _("kind")
        SimpleGetMenu.__init__(self, **kw)

    def make_title(self, attr):
        if attr == "all":
            return _("all")
        return menu[attr]

class TimeMenu(SimpleGetMenu):
    """Menu for setting the time interval of the listing (from 'hour' to 'all')"""
    get_param = 't'
    default   = 'all'
    options   = ('hour', 'day', 'week', 'month', 'year', 'all')

    def __init__(self, **kw):
        kw['title'] = _("links from")
        SimpleGetMenu.__init__(self, **kw)

    @classmethod
    def operator(self, time):
        from r2.models import Link
        if time != 'all':
            return Link.c._date >= timeago(time)

class ControversyTimeMenu(TimeMenu):
    """time interval for controversial sort.  Make default time 'day' rather than 'all'"""
    default = 'day'

class NumCommentsMenu(SimpleGetMenu):
    """menu for toggling between the user's preferred number of
    comments and the max allowed in the display, assuming the number
    of comments in the listing exceeds one or both."""
    get_param = 'all'
    default   = 'false'
    options   = ('true', 'false')

    def __init__(self, num_comments, **context):
        self.num_comments = num_comments
        self.max_comments = g.max_comments
        self.user_num = c.user.pref_num_comments
        SimpleGetMenu.__init__(self, **context)

    def make_title(self, attr):
        if self.user_num > self.num_comments:
            # no menus needed if the number of comments is smaller
            # than any of the limits
            return ""
        elif self.num_comments > self.max_comments:
            # if the number present is larger than the global max,
            # label the menu as the user pref and the max number
            return dict(true=str(self.max_comments), 
                        false=str(self.user_num))[attr]
        else:
            # if the number is less than the global max, display "all"
            # instead for the upper bound.
            return dict(true=_("all"),
                        false=str(self.user_num))[attr]
        

    def render(self, **kw):
        if self.user_num > self.num_comments:
            return ""
        return SimpleGetMenu.render(self, **kw)

class SubredditMenu(NavMenu):
    def find_selected(self):
        """Always return False so the title is always displayed"""
        return None

class JsNavMenu(NavMenu):
    def find_selected(self):
        """Always return the first element."""
        return self.options[0]

# --------------------
# TODO: move to admin area
class AdminReporterMenu(SortMenu):
    default = 'top'
    options = ('hot', 'new', 'top')

class AdminKindMenu(KindMenu):
    options = ('all', 'links', 'comments', 'spam', 'autobanned')


class AdminTimeMenu(TimeMenu):
    get_param = 't'
    default   = 'day'
    options   = ('hour', 'day', 'week')


