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
from r2.lib.utils import Storage, tup
from pylons.i18n import _
from copy import copy

error_list = dict((
        ('USER_REQUIRED', _("please login to do that")), 
        ('NO_URL', _('a url is required')),
        ('BAD_URL', _('you should check that url')),
        ('BAD_CAPTCHA', _('care to try these again?')),
        ('BAD_USERNAME', _('invalid user name')),
        ('USERNAME_TAKEN', _('that username is already taken')),
        ('NO_THING_ID', _('id not specified')),
        ('NOT_AUTHOR', _("you can't do that")),
        ('DELETED_COMMENT', _('that comment has been deleted')),
        ('DELETED_THING', _('that element has been deleted.')),
        ('BAD_PASSWORD', _('invalid password')),
        ('WRONG_PASSWORD', _('invalid password')),
        ('BAD_PASSWORD_MATCH', _('passwords do not match')),
        ('NO_NAME', _('please enter a name')),
        ('NO_EMAIL', _('please enter an email address')),
        ('NO_EMAIL_FOR_USER', _('no email address for that user')),
        ('NO_TO_ADDRESS', _('send it to whom?')),
        ('NO_SUBJECT', _('please enter a subject')),
        ('USER_DOESNT_EXIST', _("that user doesn't exist")),
        ('NO_USER', _('please enter a username')),
        ('INVALID_PREF', "that preference isn't valid"),
        ('BAD_NUMBER', _("that number isn't in the right range")),
        ('ALREADY_SUB', _("that link has already been submitted")),
        ('SUBREDDIT_EXISTS', _('that reddit already exists')),
        ('SUBREDDIT_NOEXIST', _('that reddit doesn\'t exist')),
        ('SUBREDDIT_NOTALLOWED', _("you aren't allowed to post there.")),
        ('SUBREDDIT_REQUIRED', _('you must specify a reddit')),
        ('BAD_SR_NAME', _('that name isn\'t going to work')),
        ('RATELIMIT', _('you are trying to submit too fast. try again in %(time)s.')),
        ('EXPIRED', _('your session has expired')),
        ('DRACONIAN', _('you must accept the terms first')),
        ('BANNED_IP', "IP banned"),
        ('BANNED_DOMAIN', "Domain banned"),
        ('BAD_CNAME', "that domain isn't going to work"),
        ('USED_CNAME', "that domain is already in use"),
        ('INVALID_OPTION', _('that option is not valid')),
        ('CHEATER', 'what do you think you\'re doing there?'),
        ('BAD_EMAILS', _('the following emails are invalid: %(emails)s')),
        ('NO_EMAILS', _('please enter at least one email address')),
        ('TOO_MANY_EMAILS', _('please only share to %(num)s emails at a time.')),

        ('TOO_LONG', _("this is too long (max: %(max_length)s)")),
        ('NO_TEXT', _('we need something here')),

        ('NO_DATE',  _('an event date is required.')),        
        ('BAD_DATE', _('date must be in mm/dd/yyyy format.')),
        ('BAD_TIME', _('time is not formatted properly.')),
    ))
errors = Storage([(e, e) for e in error_list.keys()])

class Error(object):

    def __init__(self, name, i18n_message, msg_params, field = None):
        self.name = name
        self.i18n_message = i18n_message
        self.msg_params = msg_params
        # list of fields in the original form that caused the error
        self.fields = tup(field) if field else []
        
    @property
    def message(self):
        return _(self.i18n_message) % self.msg_params

    def __iter__(self):
         #yield ('num', self.num)
        yield ('name', self.name)
        yield ('message', _(self.message))

    def __repr__(self):
        return '<Error: %s>' % self.name

class ErrorSet(object):
    def __init__(self):
        self.errors = {}

    def __contains__(self, pair):
        """Expectes an (error_name, field_name) tuple and checks to
        see if it's in the errors list."""
        return self.errors.has_key(pair)

    def __getitem__(self, name):
        return self.errors[name]

    def __repr__(self):
        return "<ErrorSet %s>" % list(self)

    def __iter__(self):
        for x in self.errors:
            yield x
        
    def add(self, error_name, msg_params = {}, field = None):
        msg = error_list[error_name]
        for field_name in tup(field):
            e = Error(error_name, msg, msg_params, field = field_name)
            self.errors[(error_name, field_name)] = e

    def remove(self, pair):
        """Expectes an (error_name, field_name) tuple and removes it
        from the errors list."""
        if self.errors.has_key(pair):
            del self.errors[pair]

class UserRequiredException(Exception): pass
