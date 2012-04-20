# Amara, universalsubtitles.org
# 
# Copyright (C) 2012 Participatory Culture Foundation
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see 
# http://www.gnu.org/licenses/agpl-3.0.html.

#  Based on: http://www.djangosnippets.org/snippets/73/
#
#  Modified by Sean Reifschneider to be smarter about surrounding page
#  link context.  For usage documentation see:
#
#     http://www.tummy.com/Community/Articles/django-pagination/
from django.shortcuts import render_to_response, get_object_or_404
from django.template.context import RequestContext
from django.http import HttpResponse, Http404
from django.utils import simplejson
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.functional import update_wrapper
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import simplejson as json
from django.core.mail import mail_admins
from django.conf import settings
import re
import htmllib
from subtitles import SubtitleParserError, SubtitleParser, TxtSubtitleParser, YoutubeSubtitleParser, \
    TtmlSubtitleParser, SrtSubtitleParser, SbvSubtitleParser, SsaSubtitleParser, YoutubeXMLParser, \
    DfxpSubtitleParser
import traceback, sys
from django.contrib.auth.decorators import user_passes_test
from django.contrib.sites.models import Site
import inspect

DEFAULT_PROTOCOL = getattr(settings, "DEFAULT_PROTOCOL", 'https')

try:
    import oboe
except ImportError:
    oboe = None
    
def print_last_exception():
    """
    this can be useful for asynchronous tasks debuging
    """
    import sys
    import traceback
    print '\n'.join(traceback.format_exception(*sys.exc_info()))

def is_staff(user):
    return user.is_authenticated() and user.is_staff and user.is_active

check_is_staff = user_passes_test(is_staff)

def render_to(template):
    """
    Decorator for Django views that sends returned dict to render_to_response function
    with given template and RequestContext as context instance.

    If view doesn't return dict then decorator simply returns output.
    Additionally view can return two-tuple, which must contain dict as first
    element and string with template name as second. This string will
    override template name, given as parameter

    Parameters:

     - template: template name to use
    """
    def renderer(func):
        def wrapper(request, *args, **kw):
            output = func(request, *args, **kw)
            if isinstance(output, (list, tuple)):
                return render_to_response(output[1], output[0], RequestContext(request))
            elif isinstance(output, dict):
                return render_to_response(template, output, RequestContext(request))
            return output
        return update_wrapper(wrapper, func)
    return renderer

def render_to_json(func):
    def wrapper(request, *args, **kwargs):
        result = func(request, *args, **kwargs)
        
        if isinstance(result, HttpResponse):
            return result
        
        json = simplejson.dumps(result, cls=DjangoJSONEncoder)
        return HttpResponse(json, mimetype="application/json")
    return update_wrapper(wrapper, func)

def get_object_or_none(*args, **kwargs):
    try:
        return get_object_or_404(*args, **kwargs)
    except Http404:
        return None

def get_page(request):
    page = request.GET.get('page')
    if not page == 'last':
        try:
            page = int(page)
        except (ValueError, TypeError, KeyError):
            page = 1
    return page

def get_pager(objects, on_page=15, page='1', orphans=0):
    from django.core.paginator import Paginator, InvalidPage, EmptyPage
    
    paginator = Paginator(objects, on_page, orphans=orphans)
    try:
        page = paginator.page(int(page))
    except (EmptyPage, InvalidPage):
        page = paginator.page(paginator.num_pages)
    return page

def send_templated_email(to, subject, body_template, body_dict, 
                         from_email=None, ct="html", fail_silently=False, check_user_preference=True):
    """
    Sends an html email with a template name and a rendering context.
    Parameters:
        to: a list of email addresses of User objects
        check_user_preferences: If set to false will send the email regardless
             of the user's notification preferences. This is useful in
             situations where you must send the email, for example on
             password retrivals.
    """
    from auth.models import CustomUser 
    from django.contrib.auth.models import User
    to_unchecked = to
    if not isinstance(to_unchecked, list):
        to_unchecked = [to]
    to = []
    # if passed a User, check that he has opted in for email notification
    # unless check_user_preference is False (useful for example for password)
    # retrivals, else users that have opted out of email notifications
    # can never recover their passowrd
    for recipient in to_unchecked:
        if isinstance(recipient, User) or isinstance(recipient, CustomUser):
            if not bool(recipient.email):
                continue
            if check_user_preference is False or  recipient.notify_by_email:
                to.append(recipient.email)
        else:
            to.append(recipient)
    if not from_email: from_email = settings.DEFAULT_FROM_EMAIL

    body_dict['STATIC_URL_BASE'] = settings.STATIC_URL_BASE
    body_dict['domain'] = Site.objects.get_current().domain
    body_dict['url_base'] = "%s://%s" % (DEFAULT_PROTOCOL,  Site.objects.get_current().domain)
    message = render_to_string(body_template, body_dict)
    bcc = settings.EMAIL_BCC_LIST
    email = EmailMessage(subject, message, from_email, to, bcc=bcc)
    email.content_subtype = ct
    if oboe:
        try:
            oboe.Context.log('email', 'info', backtrace=False,**{"template":body_template})
        except Exception, e:
            print >> sys.stderr, "Oboe error: %s" % e
    return email.send(fail_silently)

from raven.contrib.django.models import get_client

client = get_client()

def catch_exception(exceptions, subject="", default=None, ignore=False):
    """
    Create decorator witch catch passed exceptions, log them with Sentry
    and prevent failing. Useful for integration some services. For example we
    don't wish that site was down if Redis does not response
    """
    if not isinstance(exceptions, (list, tuple)):
        exceptions = (exceptions,)

    def catch_exception_func(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions, e:
                if not ignore:
                    client.create_from_exception(sys.exc_info())
                return default
        return update_wrapper(wrapper, func)
    return catch_exception_func

def log_exception(exceptions, logger='root', ignore=False):
    """
    Create decorator to log exceptions in Sentry.
    """
    if not isinstance(exceptions, (list, tuple)):
        exceptions = (exceptions,)
    #TODO: in Sentry message is displayed with title utils.wrapped. should fix this
    def log_exception_func(func):
        def log_exception_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions, e:
                exec_info = sys.exc_info()
                frame = exec_info[2].tb_frame.f_back
                file_name = inspect.getfile(log_exception_wrapper)
                func_name = 'log_exception_wrapper'
                
                #check if func is called by other wrapped function
                #we should not catch execption in this case, because other function
                #can be waiting for it. Really exception can be caught by any not
                #wrapped function, but you always can use ignore=False
                while frame:
                    if frame.f_code.co_name == func_name and frame.f_code.co_filename == file_name:
                        if not hasattr(e, '_traceback'):
                            e._traceback = exec_info[2]
                        raise e
                        
                    frame = frame.f_back
                    
                data = {
                    'stack': traceback.extract_stack()
                }
                if hasattr(e, '_traceback'):
                    exec_info = exec_info[0], exec_info[1], e._traceback

                client.create_from_exception(exec_info, logger=logger, data=data)
                if not ignore:
                    raise e
            
        return update_wrapper(log_exception_wrapper, func)
    return log_exception_func

import inspect

class LogExceptionsMetaclass(type):
    """
    This is metaclass for wrapping all method of class with log_exception. 
    __log_exceptionsr attribute of class should ontain tuple of exceptions
    __log_exceptions_logger_name can contain name of logger of Sentry
    __log_exceptions_ignore - set it if exceptions should be logged without 500
    
    Used, for example, in amazonsqs_backend. We are not sure how it is a little
    unpredictable, so we wish log any error. Celery, witch use amazonsqs_backend,
    does not allow catch anything.
    """
    
    def __new__(cls, name, bases, attrs):
        exc_setting_name = '_%s__log_exceptions' % name
        logger_setting_name = '_%s__log_exceptions_logger_name' % name
        ignore_settings_name = '_%s__log_exceptions_ignore' % name
        
        kwargs = {
            'exceptions': Exception
        }
        
        if ignore_settings_name in attrs:
            kwargs['ignore'] = attrs[ignore_settings_name]
            del attrs[ignore_settings_name]
        
        if exc_setting_name in attrs:
            kwargs['exceptions'] = attrs[exc_setting_name]
            del attrs[exc_setting_name]
        
        if logger_setting_name in attrs:
            kwargs['logger'] = attrs[logger_setting_name]
            del attrs[logger_setting_name]
            
        log_exception_wrapper = log_exception(**kwargs)
        
        for n, v in attrs.items():
            if inspect.isfunction(v):
                attrs[n] = log_exception_wrapper(v)
        
        for base in bases:
            for n, v in base.__dict__.items():
                if not n in attrs and inspect.isfunction(v):
                    attrs[n] = log_exception_wrapper(v)
                    
        new_class = super(LogExceptionsMetaclass, cls).__new__(cls, name, bases, attrs)
        return new_class    
