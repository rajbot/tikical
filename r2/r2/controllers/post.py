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
from r2.lib.pages import *
from api import ApiController
from r2.lib.utils import Storage, query_string, UrlParser
from r2.lib.emailer import opt_in, opt_out
from pylons import request, c, g
from validator import *
from pylons.i18n import _
import sha

def to_referer(func, **params):
    def _to_referer(self, *a, **kw):
        res = func(self, *a, **kw)
        dest = res.get('redirect') or request.referer or '/'
        return self.redirect(dest + query_string(params))        
    return _to_referer


class PostController(ApiController):
    def response_func(self, kw):
        return Storage(**kw)

#TODO: feature disabled for now
#     @to_referer
#     @validate(VUser(),
#               key = VOneOf('key', ('pref_bio','pref_location',
#                                    'pref_url')),
#               value = nop('value'))
#     def POST_user_desc(self, key, value):
#         setattr(c.user, key, value)
#         c.user._commit()
#         return {}

    def set_options(self, all_langs, pref_lang, **kw):
        if c.errors.errors:
            print "fucker"
            raise "broken"

        if all_langs == 'all':
            langs = 'all'
        elif all_langs == 'some':
            langs = []
            for lang in g.all_languages:
                if request.post.get('lang-' + lang):
                    langs.append(str(lang)) #unicode
            if langs:
                langs.sort()
                langs = tuple(langs)
            else:
                langs = 'all'

        for k, v in kw.iteritems():
            #startswith is important because kw has all sorts of
            #request info in it
            if k.startswith('pref_'):
                setattr(c.user, k, v)

        c.user.pref_content_langs = langs
        c.user.pref_lang = pref_lang
        c.user._commit()


    @validate(pref_lang = VLang('lang'),
              all_langs = nop('all-langs', default = 'all'))
    def POST_unlogged_options(self, all_langs, pref_lang):
        self.set_options( all_langs, pref_lang)
        return self.redirect(request.referer)

    @validate(pref_frame = VBoolean('frame'),
              pref_clickgadget = VBoolean('clickgadget'),
              pref_organic = VBoolean('organic'),
              pref_newwindow = VBoolean('newwindow'),
              pref_public_votes = VBoolean('public_votes'),
              pref_hide_ups = VBoolean('hide_ups'),
              pref_hide_downs = VBoolean('hide_downs'),
              pref_over_18 = VBoolean('over_18'),
              pref_numsites = VInt('numsites', 1, 100),
              pref_lang = VLang('lang'),
              pref_media = VOneOf('media', ('on', 'off', 'subreddit')),
              pref_compress = VBoolean('compress'),
              pref_min_link_score = VInt('min_link_score', -100, 100),
              pref_min_comment_score = VInt('min_comment_score', -100, 100),
              pref_num_comments = VInt('num_comments', 1, g.max_comments,
                                       default = g.num_comments),
              pref_show_stylesheets = VBoolean('show_stylesheets'),
              all_langs = nop('all-langs', default = 'all'))
    def POST_options(self, all_langs, pref_lang, **kw):
        #temporary. eventually we'll change pref_clickgadget to an
        #integer preference
        kw['pref_clickgadget'] = kw['pref_clickgadget'] and 5 or 0

        self.set_options(all_langs, pref_lang, **kw)
        u = UrlParser(c.site.path + "prefs")
        u.update_query(done = 'true')
        if c.cname:
            u.put_in_frame()
        return self.redirect(u.unparse())
            
    def GET_over18(self):
        return BoringPage(_("over 18?"),
                          content = Over18()).render()

    @validate(over18 = nop('over18'),
              uh = nop('uh'),
              dest = nop('dest'))
    def POST_over18(self, over18, uh, dest):
        if over18 == 'yes':
            if c.user_is_loggedin and c.user.valid_hash(uh):
                c.user.pref_over_18 = True
                c.user._commit()
            else:
                ip_hash = sha.new(request.ip).hexdigest()
                domain = g.domain if not c.frameless_cname else None
                c.cookies.add('over18', ip_hash,
                              domain = domain)
            return self.redirect(dest)
        else:
            return self.redirect('/')


    @validate(msg_hash = nop('x'))
    def POST_optout(self, msg_hash):
        email, sent = opt_out(msg_hash)
        if not email:
            return self.abort404()
        return BoringPage(_("opt out"),
                          content = OptOut(email = email, leave = True,
                                           sent = True,
                                           msg_hash = msg_hash)).render()

    @validate(msg_hash = nop('x'))
    def POST_optin(self, msg_hash):
        email, sent = opt_in(msg_hash)
        if not email:
            return self.abort404()
        return BoringPage(_("welcome back"),
                          content = OptOut(email = email, leave = False,
                                           sent = True,
                                           msg_hash = msg_hash)).render()


    def POST_login(self, *a, **kw):
        ApiController.POST_login(self, *a, **kw)
        c.render_style = "html"
        c.response_content_type = ""

        dest = request.post.get('dest', request.referer or '/')
        errors = list(c.errors)
        if errors:
            for e in errors:
                if not e[0].endswith("_login"):
                    msg = c.errors[e].message
                    c.errors.remove(e)
                    c.errors.add(e[0], msg)

            dest = request.post.get('dest', request.referer or '/')
            return LoginPage(user_login = request.post.get('user'),
                             dest = dest).render()

        return self.redirect(dest)

    def POST_reg(self, *a, **kw):
        ApiController.POST_register(self, *a, **kw)
        c.render_style = "html"
        c.response_content_type = ""

        dest = request.post.get('dest', request.referer or '/')
        errors = list(c.errors)
        if errors:
            for e in errors:
                if not e[0].endswith("_reg"):
                    msg = c.errors[e].message
                    c.errors.remove(e)
                    c.errors.add(e[0], msg)
            return LoginPage(user_reg = request.post.get('user'),
                             dest = dest).render()

        return self.redirect(dest)

    def GET_login(self, *a, **kw):
        return self.redirect('/login' + query_string(dict(dest="/")))
