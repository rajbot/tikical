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
from reddit_base import RedditController, set_user_cookie

from pylons.i18n import _
from pylons import c, request

from validator import *

from r2.models import *
from r2.models.subreddit import Default as DefaultSR
import r2.models.thing_changes as tc

from r2.lib.utils import get_title, sanitize_url, timeuntil, set_last_modified
from r2.lib.utils import query_string, to36, timefromnow, link_from_url
from r2.lib.pages import FriendList, ContributorList, ModList, \
    BannedList, BoringPage, FormPage, NewLink, CssError, UploadedImage, \
    ClickGadget
from r2.lib.pages.things import wrap_links, default_thing_wrapper

from r2.lib import spreadshirt
from r2.lib.menus import CommentSortMenu
from r2.lib.normalized_hot import expire_hot
from r2.lib.captcha import get_iden
from r2.lib.strings import strings
from r2.lib.filters import _force_unicode, websafe_json, websafe, spaceCompress
from r2.lib.db import queries
from r2.lib.media import force_thumbnail, thumbnail_url
from r2.lib.comment_tree import add_comment, delete_comment
from r2.lib import tracking, sup, cssfilter, emailer
from r2.lib.subreddit_search import search_reddits

from simplejson import dumps

from datetime import datetime, timedelta
from md5 import md5

from r2.lib.promote import promote, unpromote, get_promoted

class ApiController(RedditController):
    """
    Controller which deals with almost all AJAX site interaction.  
    """

    def response_func(self, kw):
        data = dumps(kw)
        if request.method == "GET" and request.GET.get("callback"):
            return "%s(%s)" % (websafe_json(request.GET.get("callback")),
                               websafe_json(data))
        return self.sendstring(data)


    @validatedForm()
    def ajax_login_redirect(self, form, jquery, dest):
        form.redirect("/login" + query_string(dict(dest=dest)))

    @validate(link = VUrl(['url']),
              count = VLimit('limit'))
    def GET_info(self, link, count):
        """
        Gets a listing of links which have the provided url.  
        """
        if not link or 'url' not in request.params:
            return abort(404, 'not found')

        links = link_from_url(request.params.get('url'), filter_spam = False)
        listing = wrap_links(links, num = count)
        return BoringPage(_("API"), content = listing).render()

    @validatedForm(VCaptcha(),
                   name=VRequired('name', errors.NO_NAME),
                   email=ValidEmails('email', num = 1),
                   reason = VOneOf('reason', ('ad_inq', 'feedback')),
                   message=VRequired('text', errors.NO_TEXT),
                   )
    def POST_feedback(self, form, jquery, name, email, reason, message):
        if not (form.has_errors('name',     errors.NO_NAME) or
                form.has_errors('email',    errors.BAD_EMAILS) or
                form.has_errors('text', errors.NO_TEXT) or
                form.has_errors('captcha', errors.BAD_CAPTCHA)):

            if reason != 'ad_inq':
                emailer.feedback_email(email, message, name, reply_to = '')
            else:
                emailer.ad_inq_email(email, message, name, reply_to = '')
            
            form.set_html(".status", _("thanks for your message! "
                            "you should hear back from us shortly."))
            form.set_inputs(text = "", captcha = "")

    POST_ad_inq = POST_feedback


    @validatedForm(VCaptcha(),
                   VUser(),
                   VModhash(),
                   ip = ValidIP(),
                   to = VExistingUname('to'),
                   subject = VRequired('subject', errors.NO_SUBJECT),
                   body = VMessage(['text', 'message']))
    def POST_compose(self, form, jquery, to, subject, body, ip):
        """
        handles message composition under /message/compose.  
        """
        if not (form.has_errors("to",  errors.USER_DOESNT_EXIST, 
                                errors.NO_USER) or
                form.has_errors("subject", errors.NO_SUBJECT) or
                form.has_errors("text", errors.NO_TEXT, errors.TOO_LONG) or
                form.has_errors("captcha", errors.BAD_CAPTCHA)):
            
            m, inbox_rel = Message._new(c.user, to, subject, body, ip)
            form.set_html(".status", _("your message has been delivered"))
            form.set_inputs(to = "", subject = "", text = "", captcha="")

            if g.write_query_queue:
                queries.new_message(m, inbox_rel)



    @validatedForm(VUser(),
                   VCaptcha(),
                   ValidDomain('url'),
                   VRatelimit(rate_user = True, rate_ip = True,
                              prefix = "rate_submit_"),
                   ip = ValidIP(),
                   sr = VSubmitSR('sr'),
                   url = VUrl(['url', 'sr']),
                   title = VTitle('title'),
                   save = VBoolean('save'),
                   selftext = VSelfText('text'),
                   kind = VOneOf('kind', ['link', 'self', 'poll']),
                   then = VOneOf('then', ('tb', 'comments'), default='comments'))
    def POST_submit(self, form, jquery, url, selftext, kind, title, save,
                    sr, ip, then):
        #backwards compatability
        if url == 'self':
            kind = 'self'

        if isinstance(url, (unicode, str)):
            # VUrl may have replaced 'url' by adding 'http://'
            form.set_inputs(url = url)

        if not kind:
            # this should only happen if somebody is trying to post
            # links in some automated manner outside of the regular
            # submission page, and hasn't updated their script
            return

        if form.has_errors('sr', errors.SUBREDDIT_NOEXIST,
                           errors.SUBREDDIT_NOTALLOWED,
                           errors.SUBREDDIT_REQUIRED):
            # checking to get the error set in the form, but we can't
            # check for rate-limiting if there's no subreddit
            return
        else:
            should_ratelimit = sr.should_ratelimit(c.user, 'link')
            #remove the ratelimit error if the user's karma is high
            if not should_ratelimit:
                c.errors.remove((errors.RATELIMIT, 'ratelimit'))

        if kind == 'link':
            # check for no url, or clear that error field on return
            if form.has_errors("url", errors.NO_URL, errors.BAD_URL):
                pass
            elif form.has_errors("url", errors.ALREADY_SUB):
                form.redirect(url[0].already_submitted_link)
            # check for title, otherwise look it up and return it
            elif form.has_errors("title", errors.NO_TEXT):
                pass

        elif kind == 'self' and form.has_errors('text', errors.TOO_LONG):
            pass

        if form.has_errors("title", errors.TOO_LONG, errors.NO_TEXT):
            pass

        if form.has_errors('ratelimit', errors.RATELIMIT):
            pass

        if form.has_error() or not title:
            return

        # well, nothing left to do but submit it
        l = Link._submit(request.post.title, url if kind == 'link' else 'self',
                         c.user, sr, ip)

        if kind == 'self':
            l.url = l.make_permalink_slow()
            l.is_self = True
            l.selftext = selftext

            l._commit()
            l.set_url_cache()

        v = Vote.vote(c.user, l, True, ip)
        if save:
            r = l._save(c.user)
            if g.write_query_queue:
                queries.new_savehide(r)

        #reset the hot page
        if v.valid_thing:
            expire_hot(sr)

        #set the ratelimiter
        if should_ratelimit:
            VRatelimit.ratelimit(rate_user=True, rate_ip = True, 
                                 prefix = "rate_submit_")

        #update the queries
        if g.write_query_queue:
            queries.new_link(l)
            queries.new_vote(v)

        #update the modified flags
        set_last_modified(c.user, 'overview')
        set_last_modified(c.user, 'submitted')
        set_last_modified(c.user, 'liked')

        #update sup listings
        sup.add_update(c.user, 'submitted')
        
        # flag search indexer that something has changed
        tc.changed(l)
        
        if then == 'comments':
            path = add_sr(l.make_permalink_slow())
        elif then == 'tb':
            form.attr('target', '_top')
            path = add_sr('/tb/%s' % l._id36)

        form.redirect(path)


    @validatedForm(VRatelimit(rate_ip = True,
                              rate_user = True,
                              prefix = 'fetchtitle_'),
                   VUser(),
                   url = VSanitizedUrl(['url']))
    def POST_fetch_title(self, form, jquery, url):
        if form.has_errors('ratelimit', errors.RATELIMIT):
            form.set_html(".title-status", "");
            return

        VRatelimit.ratelimit(rate_ip = True, rate_user = True,
                             prefix = 'fetchtitle_', seconds=1)
        if url:
            title = get_title(url)
            if title:
                form.set_inputs(title = title)
                form.set_html(".title-status", "");
            else:
                form.set_html(".title-status", _("no title found"))
        
    def _login(self, form, user, dest='', rem = None):
        """
        AJAX login handler, used by both login and register to set the
        user cookie and send back a redirect.
        """
        self.login(user, rem = rem)
        form._send_data(modhash = user.modhash())
        form._send_data(cookie  = user.make_cookie())
        dest = dest or request.referer or '/'
        form.redirect(dest)


    @validatedForm(VRatelimit(rate_ip = True, prefix = 'login_',
                              error = errors.WRONG_PASSWORD),
                   user = VLogin(['user', 'passwd']),
                   dest   = nop('dest'),
                   rem    = VBoolean('rem'),
                   reason = VReason('reason'))
    def POST_login(self, form, jquery, user, dest, rem, reason):
        if reason and reason[0] == 'redirect':
            dest = reason[1]
        if form.has_errors("passwd", errors.WRONG_PASSWORD):
            VRatelimit.ratelimit(rate_ip = True, prefix = 'login_', seconds=1)
        else:
            self._login(form, user, dest, rem)


    @validatedForm(VCaptcha(),
                   VRatelimit(rate_ip = True, prefix = "rate_register_"),
                   name = VUname(['user']),
                   email = ValidEmails("email", num = 1),
                   password = VPassword(['passwd', 'passwd2']),
                   dest = nop('dest'),
                   rem = VBoolean('rem'),
                   reason = VReason('reason'))
    def POST_register(self, form, jquery, name, email,
                      password, dest, rem, reason):
        if not (form.has_errors("user", errors.BAD_USERNAME,
                                errors.USERNAME_TAKEN) or
                form.has_errors("email", errors.BAD_EMAILS) or
                form.has_errors("passwd", errors.BAD_PASSWORD) or
                form.has_errors("passwd2", errors.BAD_PASSWORD_MATCH) or
                form.has_errors('ratelimit', errors.RATELIMIT) or
                form.has_errors('captcha', errors.BAD_CAPTCHA)):

            user = register(name, password)
            VRatelimit.ratelimit(rate_ip = True, prefix = "rate_register_")
    
            #anything else we know (email, languages)?
            if email:
                user.email = email
    
            user.pref_lang = c.lang
            if c.content_langs == 'all':
                user.pref_content_langs = 'all'
            else:
                langs = list(c.content_langs)
                langs.sort()
                user.pref_content_langs = tuple(langs)
    
            d = c.user._dirties.copy()
            user._commit()
                
            c.user = user
            if reason:
                if reason[0] == 'redirect':
                    dest = reason[1]
                elif reason[0] == 'subscribe':
                    for sr, sub in reason[1].iteritems():
                        self._subscribe(sr, sub)
    
            self._login(form, user, dest, rem)

    @noresponse(VUser(),
                VModhash(),
                container = VByName('id'))
    def POST_leave_moderator(self, container):
        """
        Handles self-removal as moderator from a subreddit as rendered
        in the subreddit sidebox on any of that subreddit's pages.
        """
        if container and container.is_moderator(c.user):
            container.remove_moderator(c.user)

    @noresponse(VUser(),
                VModhash(),
                container = VByName('id'))
    def POST_leave_contributor(self, container):
        """
        same comment as for POST_leave_moderator.
        """
        if container and container.is_contributor(c.user):
            container.remove_contributor(c.user)

    
    @noresponse(VUser(),
                VModhash(),
                nuser = VExistingUname('name'),
                iuser = VByName('id'),
                container = VByName('container'),
                type = VOneOf('type', ('friend', 'moderator',
                                       'contributor', 'banned')))
    def POST_unfriend(self, nuser, iuser, container, type):
        """
        Handles removal of a friend (a user-user relation) or removal
        of a user's priviledges from a subreddit (a user-subreddit
        relation).  The user can either be passed in by name (nuser)
        or buy fullname (iuser).  'container' will either be the
        current user or the subreddit.

        """
        # The user who made the request must be an admin or a moderator
        # for the privilege change to succeed.
        if (not c.user_is_admin
            and (type in ('moderator','contributer','banned')
                 and not c.site.is_moderator(c.user))):
            abort(403, 'forbidden')
        # if we are (strictly) unfriending, the container had better
        # be the current user.
        if type == "friend" and container != c.user:
            abort(403, 'forbidden')
        fn = getattr(container, 'remove_' + type)
        fn(iuser or nuser)



    @validatedForm(VUser(),
                   VModhash(),
                   ip = ValidIP(),
                   friend = VExistingUname('name'),
                   container = VByName('container'),
                   type = VOneOf('type', ('friend', 'moderator',
                                          'contributor', 'banned')))
    def POST_friend(self, form, jquery, ip, friend, 
                    container, type):
        """
        Complement to POST_unfriend: handles friending as well as
        privilege changes on subreddits.
        """
        fn = getattr(container, 'add_' + type)

        # The user who made the request must be an admin or a moderator
        # for the privilege change to succeed.
        if (not c.user_is_admin
            and (type in ('moderator','contributer','banned')
                 and not c.site.is_moderator(c.user))):
            abort(403,'forbidden')

        # if we are (strictly) friending, the container had better
        # be the current user.
        if type == "friend" and container != c.user:
            abort(403,'forbidden')

        elif not form.has_errors("name",
                                 errors.USER_DOESNT_EXIST, errors.NO_USER):
            new = fn(friend)
            cls = dict(friend=FriendList,
                       moderator=ModList,
                       contributor=ContributorList,
                       banned=BannedList).get(type)
            form.set_inputs(name = "")
            form.set_html(".status:first", _("added"))
            if new and cls:
                user_row = cls().user_row(friend)
                jquery("table").insert_table_rows(user_row)
                
                if type != 'friend':
                    msg = strings.msg_add_friend.get(type)
                    subj = strings.subj_add_friend.get(type)
                    if msg and subj and friend.name != c.user.name:
                        # fullpath with domain needed or the markdown link
                        # will break
                        d = dict(url = container.path, 
                                 title = container.title)
                        msg = msg % d
                        subj = subj % d
                        Message._new(c.user, friend, subj, msg, ip)


    @validatedForm(VUser('curpass', default = ''),
                   VModhash(), 
                   email = ValidEmails("email", num = 1),
                   password = VPassword(['newpass', 'verpass']))
    def POST_update(self, form, jquery, email, password):
        """
        handles /prefs/update for updating email address and password.
        """
        # password is required to proceed
        if form.has_errors("curpass", errors.WRONG_PASSWORD):
            return
        
        # check if the email is valid.  If one is given and it is
        # different from the current address (or there is not one
        # currently) apply it
        updated = False
        if (not form.has_errors("email", errors.BAD_EMAILS) and
            email and (not hasattr(c.user,'email') or c.user.email != email)):
            c.user.email = email
            c.user._commit()
            form.set_html('.status', _('your email has been updated'))
            updated = True
            
        # change password
        if (password and
            not (form.has_errors("newpass", errors.BAD_PASSWORD) or
                 form.has_errors("verpass", errors.BAD_PASSWORD_MATCH))):
            change_password(c.user, password)
            if updated:
                form.set_html(".status",
                              _('your email and password have been updated'))
            else:
                form.set_html('.status', 
                              _('your password has been updated'))
            form.set_inputs(curpass = "", newpass = "", verpass = "")
            # the password has changed, so the user's cookie has been
            # invalidated.  drop a new cookie.
            self.login(c.user)

    @validatedForm(VUser(),
                   VModhash(),
                   areyousure1 = VOneOf('areyousure1', ('yes', 'no')),
                   areyousure2 = VOneOf('areyousure2', ('yes', 'no')),
                   areyousure3 = VOneOf('areyousure3', ('yes', 'no')))
    def POST_delete_user(self, form, jquery,
                         areyousure1, areyousure2, areyousure3):
        """
        /prefs/delete.  Make sure there are three yes's.
        """
        if areyousure1 == areyousure2 == areyousure3 == 'yes':
            c.user.delete()
            form.redirect('/?deleted=true')
        else:
            form.set_html('.status', _("see? you don't really want to leave"))

    @noresponse(VUser(),
                VModhash(),
                thing = VByNameIfAuthor('id'))
    def POST_del(self, thing):
        if not thing: return
        '''for deleting all sorts of things'''
        thing._deleted = True
        thing._commit()

        # flag search indexer that something has changed
        tc.changed(thing)

        #expire the item from the sr cache
        if isinstance(thing, Link):
            sr = thing.subreddit_slow
            expire_hot(sr)
            if g.use_query_cache:
                queries.new_link(thing)

        #comments have special delete tasks
        elif isinstance(thing, Comment):
            thing._delete()
            delete_comment(thing)
            if g.use_query_cache:
                queries.new_comment(thing, None)

    @noresponse(VUser(), VModhash(),
                thing = VByName('id'))
    def POST_report(self, thing):
        '''for reporting...'''
        if (thing and not thing._deleted and
            not (hasattr(thing, "promoted") and thing.promoted)):
            Report.new(c.user, thing)

    @validatedForm(VUser(),
                   VModhash(),
                   item = VByNameIfAuthor('thing_id'),
                   text = VComment('text'))
    def POST_editusertext(self, form, jquery, item, text):
        if not form.has_errors("text",
                               errors.NO_TEXT, errors.TOO_LONG,
                               errors.NOT_AUTHOR):

            if isinstance(item, Comment):
                kind = 'comment'
                item.body = text
            elif isinstance(item, Link):
                kind = 'link'
                item.selftext = text

            item.editted = True
            item._commit()

            tc.changed(item)

            if kind == 'link':
                set_last_modified(item, 'comments')

            wrapper = default_thing_wrapper(expand_children = True)
            jquery(".content").replace_things(item, True, True, wrap = wrapper)
            jquery(".content .link .rank").hide()

    @validatedForm(VUser(),
                   VModhash(),
                   VRatelimit(rate_user = True, rate_ip = True,
                              prefix = "rate_comment_"),
                   ip = ValidIP(),
                   parent = VSubmitParent(['thing_id', 'parent']),
                   comment = VComment(['text', 'comment']))
    def POST_comment(self, commentform, jquery, parent, comment, ip):
        should_ratelimit = True
        #check the parent type here cause we need that for the
        #ratelimit checks
        if isinstance(parent, Message):
            is_message = True
            should_ratelimit = False
        else:
            is_message = False
            is_comment = True
            if isinstance(parent, Link):
                link = parent
                parent_comment = None
            else:
                link = Link._byID(parent.link_id, data = True)
                parent_comment = parent
            sr = parent.subreddit_slow
            if not sr.should_ratelimit(c.user, 'comment'):
                should_ratelimit = False

        #remove the ratelimit error if the user's karma is high
        if not should_ratelimit:
            c.errors.remove((errors.RATELIMIT, 'ratelimit'))

        if (not commentform.has_errors("text",
                                       errors.NO_TEXT,
                                       errors.TOO_LONG) and
            not commentform.has_errors("ratelimit",
                                       errors.RATELIMIT) and
            not commentform.has_errors("parent",
                                       errors.DELETED_COMMENT)):

            if is_message:
                to = Account._byID(parent.author_id)
                subject = parent.subject
                re = "re: "
                if not subject.startswith(re):
                    subject = re + subject
                item, inbox_rel = Message._new(c.user, to, subject,
                                               comment, ip)
                item.parent_id = parent._id
            else:
                item, inbox_rel =  Comment._new(c.user, link, parent_comment,
                                                comment, ip)
                Vote.vote(c.user, item, True, ip)
                # flag search indexer that something has changed
                tc.changed(item)
    
                #update last modified
                set_last_modified(c.user, 'overview')
                set_last_modified(c.user, 'commented')
                set_last_modified(link, 'comments')

                #update sup listings
                sup.add_update(c.user, 'commented')
    
                #update the comment cache
                add_comment(item)
    
            # clean up the submission form and remove it from the DOM (if reply)
            t = commentform.find("textarea")
            t.attr('rows', 3).html("").attr("value", "")
            if isinstance(parent, (Comment, Message)):
                commentform.remove()
                jquery.things(parent._fullname).set_html(".reply-button:first",
                                                         _("replied"))
    
            # insert the new comment
            jquery.insert_things(item)
            # remove any null listings that may be present
            jquery("#noresults").hide()
    
            #update the queries
            if g.write_query_queue:
                if is_message:
                    queries.new_message(item, inbox_rel)
                else:
                    queries.new_comment(item, inbox_rel)
    
            #set the ratelimiter
            if should_ratelimit:
                VRatelimit.ratelimit(rate_user=True, rate_ip = True,
                                     prefix = "rate_comment_")
            


    @validatedForm(VUser(),
                   VModhash(),
                   VCaptcha(),
                   VRatelimit(rate_user = True, rate_ip = True,
                              prefix = "rate_share_"),
                   share_from = VLength('share_from', max_length = 100),
                   emails = ValidEmails("share_to"),
                   reply_to = ValidEmails("replyto", num = 1), 
                   message = VLength("message", max_length = 1000), 
                   thing = VByName('parent'))
    def POST_share(self, shareform, jquery, emails, thing, share_from, reply_to,
                   message):

        # remove the ratelimit error if the user's karma is high
        sr = thing.subreddit_slow
        should_ratelimit = sr.should_ratelimit(c.user, 'link')
        if not should_ratelimit:
            c.errors.remove((errors.RATELIMIT, 'ratelimit'))

        # share_from and messages share a too_long error.
        # finding an error on one necessitates hiding the other error
        if shareform.has_errors("share_from", errors.TOO_LONG):
            shareform.find(".message-errors").children().hide()
        elif shareform.has_errors("message", errors.TOO_LONG):
            shareform.find(".share-form-errors").children().hide()
        # reply_to and share_to also share errors...
        elif shareform.has_errors("share_to", errors.BAD_EMAILS,
                                  errors.NO_EMAILS,
                                  errors.TOO_MANY_EMAILS):
            shareform.find(".reply-to-errors").children().hide()
        elif shareform.has_errors("replyto", errors.BAD_EMAILS,
                                  errors.TOO_MANY_EMAILS):
            shareform.find(".share-to-errors").children().hide()
        # lastly, check the captcha.
        elif shareform.has_errors("captcha", errors.BAD_CAPTCHA):
            pass
        elif shareform.has_errors("ratelimit", errors.RATELIMIT):
            pass
        else:
            c.user.add_share_emails(emails)
            c.user._commit()
            link = jquery.things(thing._fullname)
            link.set_html(".share", _("shared"))
            shareform.html("<div class='clearleft'></div>"
                           "<p class='error'>%s</p>" % 
                           _("your link has been shared."))

            emailer.share(thing, emails, from_name = share_from or "",
                          body = message or "", reply_to = reply_to or "")

            #set the ratelimiter
            if should_ratelimit:
                VRatelimit.ratelimit(rate_user=True, rate_ip = True,
                                     prefix = "rate_share_")
            
    @noresponse(VUser(),
                VModhash(),
                vote_type = VVotehash(('vh', 'id')),
                ip = ValidIP(),
                dir = VInt('dir', min=-1, max=1),
                thing = VByName('id'))
    def POST_vote(self, dir, thing, ip, vote_type):
        ip = request.ip
        user = c.user
        if not thing:
            return

        # TODO: temporary hack until we migrate the rest of the vote data
        if thing._date < datetime(2009, 4, 17, 0, 0, 0, 0, g.tz):
            g.log.debug("POST_vote: ignoring old vote on %s" % thing._fullname)
            return

        with g.make_lock('vote_lock(%s,%s)' % (c.user._id36, thing._id36)):
            dir = (True if dir > 0
                   else False if dir < 0
                   else None)
            organic = vote_type == 'organic'
            v = Vote.vote(user, thing, dir, ip, organic)

            #update relevant caches
            if isinstance(thing, Link):
                sr = thing.subreddit_slow
                set_last_modified(c.user, 'liked')
                set_last_modified(c.user, 'disliked')

                #update sup listings
                if dir:
                    sup.add_update(c.user, 'liked')
                elif dir is False:
                    sup.add_update(c.user, 'disliked')

                if v.valid_thing:
                    expire_hot(sr)

                if g.write_query_queue:
                    queries.new_vote(v)

            # flag search indexer that something has changed
            tc.changed(thing)

    @validatedForm(VUser(),
                   VModhash(),
                   # nop is safe: handled after auth checks below
                   stylesheet_contents = nop('stylesheet_contents'),
                   op = VOneOf('op',['save','preview']))
    def POST_subreddit_stylesheet(self, form, jquery,
                                  stylesheet_contents = '', op='save'):
        if not c.site.can_change_stylesheet(c.user):
            return self.abort(403,'forbidden')

        if g.css_killswitch:
            return self.abort(403,'forbidden')

        # validation is expensive.  Validate after we've confirmed
        # that the changes will be allowed
        parsed, report = cssfilter.validate_css(stylesheet_contents)

        if report.errors:
            error_items = [ CssError(x).render(style='html')
                            for x in sorted(report.errors) ]
            form.set_html(".status", _('validation errors'))
            form.set_html(".errors ul", ''.join(error_items))
            form.find('.errors').show()
        else:
            form.find('.errors').hide()
            form.set_html(".errors ul", '')

        stylesheet_contents_parsed = parsed.cssText if parsed else ''
        # if the css parsed, we're going to apply it (both preview & save)
        if not report.errors:
            jquery.apply_stylesheet(stylesheet_contents_parsed)
        if not report.errors and op == 'save':
            c.site.stylesheet_contents      = stylesheet_contents_parsed
            c.site.stylesheet_contents_user = stylesheet_contents

            c.site.stylesheet_hash = md5(stylesheet_contents_parsed).hexdigest()

            set_last_modified(c.site,'stylesheet_contents')
            tc.changed(c.site)
            c.site._commit()

            form.set_html(".status", _('saved'))
            form.set_html(".errors ul", "")

        elif op == 'preview':
            # try to find a link to use, otherwise give up and
            # return
            links = cssfilter.find_preview_links(c.site)
            if links:

                jquery('#preview-table').show()
    
                # do a regular link
                jquery('#preview_link_normal').html(
                    cssfilter.rendered_link(links, media = 'off',
                                            compress=False))
                # now do one with media
                jquery('#preview_link_media').html(
                    cssfilter.rendered_link(links, media = 'on',
                                            compress=False))
                # do a compressed link
                jquery('#preview_link_compressed').html(
                    cssfilter.rendered_link(links, media = 'off',
                                            compress=True))
    
            # and do a comment
            comments = cssfilter.find_preview_comments(c.site)
            if comments:
                jquery('#preview_comment').html(
                    cssfilter.rendered_comment(comments))


    @validatedForm(VSrModerator(),
                   VModhash(),
                   name = VCssName('img_name'))
    def POST_delete_sr_img(self, form, jquery, name):
        """
        Called called upon requested delete on /about/stylesheet.
        Updates the site's image list, and causes the <li> which wraps
        the image to be hidden.
        """
        # just in case we need to kill this feature from XSS
        if g.css_killswitch:
            return self.abort(403,'forbidden')
        c.site.del_image(name)
        c.site._commit()
    

    @validatedForm(VSrModerator(),
                   VModhash())
    def POST_delete_sr_header(self, form, jquery):
        """
        Called when the user request that the header on a sr be reset.
        """
        # just in case we need to kill this feature from XSS
        if g.css_killswitch:
            return self.abort(403,'forbidden')
        if c.site.header:
            c.site.header = None
            c.site._commit()
        # reset the header image on the page
        form.find('#header-img').attr("src", DefaultSR.header)
        # hide the button which started this
        form.find('#delete-img').hide()
        # hide the preview box
        form.find('#img-preview-container').hide()
        # reset the status boxes
        form.set_html('.img-status', _("deleted"))
        

    def GET_upload_sr_img(self, *a, **kw):
        """
        Completely unnecessary method which exists because safari can
        be dumb too.  On page reload after an image has been posted in
        safari, the iframe to which the request posted preserves the
        URL of the POST, and safari attempts to execute a GET against
        it.  The iframe is hidden, so what it returns is completely
        irrelevant.
        """
        return "nothing to see here."

    @validate(VSrModerator(),
              VModhash(),
              file = VLength('file', max_length=1024*500),
              name = VCssName("name"),
              header = nop('header'))
    def POST_upload_sr_img(self, file, header, name):
        """
        Called on /about/stylesheet when an image needs to be replaced
        or uploaded, as well as on /about/edit for updating the
        header.  Unlike every other POST in this controller, this
        method does not get called with Ajax but rather is from the
        original form POSTing to a hidden iFrame.  Unfortunately, this
        means the response needs to generate an page with a script tag
        to fire the requisite updates to the parent document, and,
        more importantly, that we can't use our normal toolkit for
        passing those responses back.

        The result of this function is a rendered UploadedImage()
        object in charge of firing the completedUploadImage() call in
        JS.
        """

        # default error list (default values will reset the errors in
        # the response if no error is raised)
        errors = dict(BAD_CSS_NAME = "", IMAGE_ERROR = "")
        try:
            cleaned = cssfilter.clean_image(file,'PNG')
            if header:
                num = None # there is one and only header, and it is unnumbered
            elif not name:
                # error if the name wasn't specified or didn't satisfy
                # the validator
                errors['BAD_CSS_NAME'] = _("bad image name")
            else:
                num = c.site.add_image(name, max_num = g.max_sr_images)
                c.site._commit()

        except cssfilter.BadImage:
            # if the image doesn't clean up nicely, abort
            errors["IMAGE_ERROR"] = _("bad image")
        except ValueError:
            # the add_image method will raise only on too many images
            errors['IMAGE_ERROR'] = (
                _("too many images (you only get %d)") % g.max_sr_images)

        if any(errors.values()):
            return  UploadedImage("", "", "", errors = errors).render()
        else: 
            # with the image num, save the image an upload to s3.  the
            # header image will be of the form "${c.site._fullname}.png"
            # while any other image will be ${c.site._fullname}_${num}.png
            new_url = cssfilter.save_sr_image(c.site, cleaned, num = num)
            if header:
                c.site.header = new_url
            c.site._commit()
    
            return UploadedImage(_('saved'), new_url, name, 
                                 errors = errors).render()
    

    @validatedForm(VUser(),
                   VModhash(),
                   VRatelimit(rate_user = True,
                              rate_ip = True,
                              prefix = 'create_reddit_'),
                   sr = VByName('sr'),
                   name = VSubredditName("name"),
                   title = VLength("title", max_length = 100),
                   domain = VCnameDomain("domain"),
                   description = VLength("description", max_length = 500),
                   lang = VLang("lang"),
                   over_18 = VBoolean('over_18'),
                   show_media = VBoolean('show_media'),
                   type = VOneOf('type', ('public', 'private', 'restricted')),
                   ip = ValidIP(),
                   )
    def POST_site_admin(self, form, jquery, name ='', ip = None, sr = None, **kw):
        # the status button is outside the form -- have to reset by hand
        form.parent().set_html('.status', "")

        redir = False
        kw = dict((k, v) for k, v in kw.iteritems()
                  if k in ('name', 'title', 'domain', 'description', 'over_18',
                           'show_media', 'type', 'lang',))

        #if a user is banned, return rate-limit errors
        if c.user._spam:
            time = timeuntil(datetime.now(g.tz) + timedelta(seconds=600))
            c.errors.add(errors.RATELIMIT, {'time': time})

        domain = kw['domain']
        cname_sr = domain and Subreddit._by_domain(domain)
        if cname_sr and (not sr or sr != cname_sr):
            c.errors.add(errors.USED_CNAME)

        if not sr and form.has_errors(None, errors.RATELIMIT):
            # this form is a little odd in that the error field
            # doesn't occur within the form, so we need to manually
            # set this text
            form.parent().find('.RATELIMIT').html(c.errors[errors.RATELIMIT].message).show()
        elif not sr and form.has_errors("name", errors.SUBREDDIT_EXISTS,
                                        errors.BAD_SR_NAME):
            form.find('#example_name').hide()
        elif form.has_errors('title', errors.NO_TEXT, errors.TOO_LONG):
            form.find('#example_title').hide()
        elif form.has_errors('domain', errors.BAD_CNAME, errors.USED_CNAME):
            form.find('#example_domain').hide()
        elif (form.has_errors(None, errors.INVALID_OPTION) or
              form.has_errors('description', errors.TOO_LONG)):
            pass
        #creating a new reddit
        elif not sr:
            #sending kw is ok because it was sanitized above
            sr = Subreddit._new(name = name, author_id = c.user._id, ip = ip,
                                **kw)
            Subreddit.subscribe_defaults(c.user)
            # make sure this user is on the admin list of that site!
            if sr.add_subscriber(c.user):
                sr._incr('_ups', 1)
            sr.add_moderator(c.user)
            sr.add_contributor(c.user)
            redir =  sr.path + "about/edit/?created=true"
            if not c.user_is_admin:
                VRatelimit.ratelimit(rate_user=True,
                                     rate_ip = True,
                                     prefix = "create_reddit_")

        #editting an existing reddit
        elif sr.is_moderator(c.user) or c.user_is_admin:
            #assume sr existed, or was just built
            old_domain = sr.domain

            for k, v in kw.iteritems():
                setattr(sr, k, v)
            sr._commit()

            #update the domain cache if the domain changed
            if sr.domain != old_domain:
                Subreddit._by_domain(old_domain, _update = True)
                Subreddit._by_domain(sr.domain, _update = True)

            # flag search indexer that something has changed
            tc.changed(sr)
            form.parent().set_html('.status', _("saved"))

        if redir:
            form.redirect(redir)

    @noresponse(VUser(), VModhash(),
                VSrCanBan('id'),
                thing = VByName('id'))
    def POST_ban(self, thing):
        admintools.spam(thing, False, not c.user_is_admin, c.user.name)

    @noresponse(VUser(), VModhash(),
                VSrCanBan('id'),
                thing = VByName('id'))
    def POST_unban(self, thing):
        admintools.unspam(thing, c.user.name)

    @noresponse(VUser(), VModhash(),
                VSrCanBan('id'),
                thing = VByName('id'))
    def POST_ignore(self, thing):
        if not thing: return
        Report.accept(thing, False)

    @validatedForm(VUser(), VModhash(),
                   VSrCanDistinguish('id'),
                   thing = VByName('id'),
                   how = VOneOf('how', ('yes','no','admin')))
    def POST_distinguish(self, form, jquery, thing, how):
        if not thing:return
        thing.distinguished = how
        thing._commit()
        wrapper = default_thing_wrapper(expand_children = True)
        w = wrap_links(thing, wrapper)
        jquery(".content").replace_things(w, True, True)
        jquery(".content .link .rank").hide()

    @noresponse(VUser(),
                VModhash(),
                thing = VByName('id'))
    def POST_save(self, thing):
        if not thing: return
        r = thing._save(c.user)
        if g.write_query_queue:
            queries.new_savehide(r)

    @noresponse(VUser(),
                VModhash(),
                thing = VByName('id'))
    def POST_unsave(self, thing):
        if not thing: return
        r = thing._unsave(c.user)
        if g.write_query_queue and r:
            queries.new_savehide(r)

    @noresponse(VUser(),
                VModhash(),
                thing = VByName('id'))
    def POST_hide(self, thing):
        if not thing: return
        r = thing._hide(c.user)
        if g.write_query_queue:
            queries.new_savehide(r)

    @noresponse(VUser(),
                VModhash(),
                thing = VByName('id'))
    def POST_unhide(self, thing):
        if not thing: return
        r = thing._unhide(c.user)
        if g.write_query_queue and r:
            queries.new_savehide(r)


    @validatedForm(link = VByName('link_id'),
                   sort = VMenu('where', CommentSortMenu),
                   children = VCommentIDs('children'),
                   depth = VInt('depth', min = 0, max = 8),
                   mc_id = nop('id'))
    def POST_morechildren(self, form, jquery,
                          link, sort, children, depth, mc_id):
        user = c.user if c.user_is_loggedin else None
        if not link or not link.subreddit_slow.can_view(user):
            return self.abort(403,'forbidden')
            
        if children:
            builder = CommentBuilder(link, CommentSortMenu.operator(sort),
                                     children)
            listing = Listing(builder, nextprev = False)
            items = listing.get_items(starting_depth = depth, num = 20)
            def _children(cur_items):
                items = []
                for cm in cur_items:
                    items.append(cm)
                    if hasattr(cm, 'child'):
                        if hasattr(cm.child, 'things'):
                            items.extend(_children(cm.child.things))
                            cm.child = None
                        else:
                            items.append(cm.child)
                        
                return items
            # assumes there is at least one child
            # a = _children(items[0].child.things)
            a = []
            for item in items:
                a.append(item)
                if hasattr(item, 'child'):
                    a.extend(_children(item.child.things))
                    item.child = None

            # the result is not always sufficient to replace the 
            # morechildren link
            jquery.things(str(mc_id)).remove()
            jquery.insert_things(a, append = True)


    @validate(uh = nop('uh'), # VModHash() will raise, check manually
              action = VOneOf('what', ('like', 'dislike', 'save')),
              links = VUrl(['u']))
    def GET_bookmarklet(self, action, uh, links):
        '''Controller for the functionality of the bookmarklets (not
        the distribution page)'''

        # the redirect handler will clobber the extension if not told otherwise
        c.extension = "png"

        if not c.user_is_loggedin:
            return self.redirect("/static/css_login.png")
        # check the modhash (or force them to get new bookmarlets)
        elif not c.user.valid_hash(uh) or not action:
            return self.redirect("/static/css_update.png")
        # unlike most cases, if not already submitted, error.
        elif errors.ALREADY_SUB in c.errors:
            # preserve the subreddit if not Default
            sr = c.site if not isinstance(c.site, FakeSubreddit) else None

            # check permissions on those links to make sure votes will count
            Subreddit.load_subreddits(links, return_dict = False)
            user = c.user if c.user_is_loggedin else None
            links = [l for l in links if l.subreddit_slow.can_view(user)]
    
            if links:
                if action in ['like', 'dislike']:
                    #vote up all of the links
                    for link in links:
                        v = Vote.vote(c.user, link, action == 'like',
                                      request.ip)
                        if g.write_query_queue:
                            queries.new_vote(v)
                elif action == 'save':
                    link = max(links, key = lambda x: x._score)
                    r = link._save(c.user)
                    if g.write_query_queue:
                        queries.new_savehide(r)
                return self.redirect("/static/css_%sd.png" % action)
        return self.redirect("/static/css_submit.png")


    @validatedForm(user = VUserWithEmail('name'))
    def POST_password(self, form, jquery, user):
        if form.has_errors('name', errors.USER_DOESNT_EXIST):
            return
        elif form.has_errors('name', errors.NO_EMAIL_FOR_USER):
            return
        else:
            emailer.password_email(user)
            form.set_html(".status", _("an email will be sent to that account's address shortly"))

            
    @validatedForm(cache_evt = VCacheKey('reset', ('key', 'name')),
                   password  = VPassword(['passwd', 'passwd2']))
    def POST_resetpassword(self, form, jquery, cache_evt, password):
        if form.has_errors('name', errors.EXPIRED):
            cache_evt.clear()
            form.redirect('/password')
        elif form.has_errors('passwd',  errors.BAD_PASSWORD):
            pass
        elif form.has_errors('passwd2', errors.BAD_PASSWORD_MATCH):
            pass
        elif cache_evt.user:
            # successfully entered user name and valid new password
            change_password(cache_evt.user, password)
            print "%s did a password reset for %s via %s" % (
                request.ip, cache_evt.user.name, cache_evt.key)
            self._login(jquery, cache_evt.user, '/')
            cache_evt.clear()


    @noresponse(VUser())
    def POST_noframe(self):
        """
        removes the reddit toolbar if that currently the user's preference
        """
        c.user.pref_frame = False
        c.user._commit()


    @noresponse(VUser())
    def POST_frame(self):
        """
        undoes POST_noframe
        """
        c.user.pref_frame = True
        c.user._commit()



    @validatedForm()
    def POST_new_captcha(self, form, jquery, *a, **kw):
        jquery("body").captcha(get_iden())

    @noresponse(VAdmin(),
                tr = VTranslation("id"), 
                user = nop('user'))
    def POST_deltranslator(self, tr, user):
        if tr:
            tr.author.remove(user)
            tr.save()

    @noresponse(VUser(),
                VModhash(),
                action = VOneOf('action', ('sub', 'unsub')),
                sr = VByName('sr'))
    def POST_subscribe(self, action, sr):
        # only users who can make edits are allowed to subscribe.
        # Anyone can leave.
        if action != 'sub' or sr.can_comment(c.user):
            self._subscribe(sr, action == 'sub')
    
    def _subscribe(self, sr, sub):
        Subreddit.subscribe_defaults(c.user)

        if sub:
            if sr.add_subscriber(c.user):
                sr._incr('_ups', 1)
        else:
            if sr.remove_subscriber(c.user):
                sr._incr('_ups', -1)
        tc.changed(sr)


    @noresponse(VAdmin(),
                tr = VTranslation("id"))
    def POST_disable_lang(self, tr):
        if tr:
            tr._is_enabled = False
        

    @noresponse(VAdmin(),
                tr = VTranslation("id"))
    def POST_enable_lang(self, tr):
        if tr:
            tr._is_enabled = True


    @validatedForm(links = VByName('links', thing_cls = Link, multiple = True),
                   show = VByName('show', thing_cls = Link, multiple = False))
    def POST_fetch_links(self, form, jquery, links, show):
        l = wrap_links(links, listing_cls = OrganicListing,
                       num_margin = 0, mid_margin = 0)
        jquery(".content").replace_things(l, stubs = True)

        if show:
            jquery('.organic-listing .link:visible').hide()
            jquery('.organic-listing .id-%s' % show._fullname).show()

    @noresponse(VUser(),
              ui_elem = VOneOf('id', ('organic',)))
    def POST_disable_ui(self, ui_elem):
        if ui_elem:
            pref = "pref_%s" % ui_elem
            if getattr(c.user, pref):
                setattr(c.user, "pref_" + ui_elem, False)
                c.user._commit()

    @noresponse(VSponsor(),
                thing = VByName('id'))
    def POST_unpromote(self, thing):
        if not thing: return
        unpromote(thing)

    @validatedForm(VSponsor(),
                   ValidDomain('url'),
                   ip               = ValidIP(),
                   l                = VLink('link_id'),
                   title            = VTitle('title'),
                   url              = VUrl(['url', 'sr'], allow_self = False),
                   sr               = VSubmitSR('sr'),
                   subscribers_only = VBoolean('subscribers_only'),
                   disable_comments = VBoolean('disable_comments'),
                   expire           = VOneOf('expire', ['nomodify', 
                                                        'expirein', 'cancel']),
                   timelimitlength  = VInt('timelimitlength',1,1000),
                   timelimittype    = VOneOf('timelimittype',
                                             ['hours','days','weeks']))
    def POST_edit_promo(self, form, jquery, ip,
                        title, url, sr, subscribers_only,
                        disable_comments,
                        expire = None,
                        timelimitlength = None, timelimittype = None,
                        l = None):
        if isinstance(url, str):
            # VUrl may have modified the URL to make it valid, like
            # adding http://
            form.set_input('url', url)
        elif isinstance(url, tuple) and isinstance(url[0], Link):
            # there's already one or more links with this URL, but
            # we're allowing mutliple submissions, so we really just
            # want the URL
            url = url[0].url
        if form.has_errors('title', errors.NO_TEXT, errors.TOO_LONG):
            pass
        elif form.has_errors('url', errors.NO_URL, errors.BAD_URL):
            pass
        elif ( (not l or url != l.url) and 
               form.has_errors('url', errors.NO_URL, errors.ALREADY_SUB) ):
            #if url == l.url, we're just editting something else
            pass
        elif form.has_errors('sr', errors.SUBREDDIT_NOEXIST,
                             errors.SUBREDDIT_NOTALLOWED):
            pass
        elif (expire == 'expirein' and 
              form.has_errors('timelimitlength', errors.BAD_NUMBER)):
            pass
        elif l:
            l.title = title
            old_url = l.url
            l.url = url
            l.is_self = False

            l.promoted_subscribersonly = subscribers_only
            l.disable_comments = disable_comments

            if expire == 'cancel':
                l.promote_until = None
            elif expire == 'expirein' and timelimitlength and timelimittype:
                l.promote_until = timefromnow("%d %s" % (timelimitlength,
                                                         timelimittype))
            l._commit()
            l.update_url_cache(old_url)

            form.redirect('/promote/edit_promo/%s' % to36(l._id))
        else:
            l = Link._submit(title, url, c.user, sr, ip)

            if expire == 'expirein' and timelimitlength and timelimittype:
                promote_until = timefromnow("%d %s" % (timelimitlength,
                                                       timelimittype))
            else:
                promote_until = None
                
            l._commit()

            promote(l, subscribers_only = subscribers_only,
                    promote_until = promote_until,
                    disable_comments = disable_comments)

            form.redirect('/promote/edit_promo/%s' % to36(l._id))

    def GET_link_thumb(self, *a, **kw):
        """
        See GET_upload_sr_image for rationale
        """
        return "nothing to see here."

    @validate(VSponsor(),
              link = VByName('link_id'),
              file = VLength('file', 500*1024))
    def POST_link_thumb(self, link=None, file=None):
        errors = dict(BAD_CSS_NAME = "", IMAGE_ERROR = "")
        try:
            force_thumbnail(link, file)
        except cssfilter.BadImage:
            # if the image doesn't clean up nicely, abort
            errors["IMAGE_ERROR"] = _("bad image")

        if any(errors.values()):
            return UploadedImage("", "", "upload", errors = errors).render()
        else:
            return UploadedImage(_('saved'), thumbnail_url(link), "",
                                 errors = errors).render()

    @validatedForm(type = VOneOf('type', ('click'), default = 'click'),
                   links = VByName('ids', thing_cls = Link, multiple = True))
    def GET_gadget(self, form, jquery, type, links):
        if not links and type == 'click':
            # malformed cookie, clear it out
            set_user_cookie('recentclicks2', '')

        if not links:
            return

        content = ClickGadget(links).make_content()

        jquery('.gadget').show().find('.click-gadget').html(
            spaceCompress(content))

    @noresponse()
    def POST_tb_commentspanel_show(self):
        # this preference is allowed for non-logged-in users
        c.user.pref_frame_commentspanel = True
        c.user._commit()

    @noresponse()
    def POST_tb_commentspanel_hide(self):
        # this preference is allowed for non-logged-in users
        c.user.pref_frame_commentspanel = False
        c.user._commit()

    @validatedForm(promoted = VByName('ids', thing_cls = Link, multiple = True))
    def POST_onload(self, form, jquery, promoted, *a, **kw):
        if not promoted:
            return

        # make sure that they are really promoted
        promoted = [ l for l in promoted if l.promoted ]

        for l in promoted:
            dest = l.url
            
            jquery.set_tracker(
                l._fullname,
                tracking.PromotedLinkInfo.gen_url(fullname=l._fullname,
                                                  ip = request.ip),
                tracking.PromotedLinkClickInfo.gen_url(fullname = l._fullname,
                                                       dest = dest,
                                                       ip = request.ip)
                )

    @json_validate(query = nop('query'))
    def POST_search_reddit_names(self, query):
        names = []
        if query:
            names = search_reddits(query)

        return {'names': names}

    @validate(link = VByName('link_id', thing_cls = Link))
    def POST_expando(self, link):
        if not link:
            abort(404, 'not found')

        wrapped = wrap_links(link)
        wrapped = list(wrapped)[0]
        return spaceCompress(websafe(wrapped.link_child.content()))

    @validatedForm(link = VByName('name', thing_cls = Link, multiple = False),
                   color = VOneOf('color', spreadshirt.ShirtPane.colors),
                   style = VOneOf('style', spreadshirt.ShirtPane.styles),
                   size  = VOneOf("size", spreadshirt.ShirtPane.sizes),
                   quantity = VInt("quantity", min = 1))
    def POST_shirt(self, form, jquery, link, color, style, size, quantity):
        if not g.spreadshirt_url:
            return self.abort404()
        else:
            res = spreadshirt.shirt_request(link, color, style, size, quantity)
            if res:
                form.set_html(".status", _("redirecting..."))
                jquery.redirect(res)
            else:    
                form.set_html(".status", _("error (sorry)"))
