# -*- coding: utf-8 -*-
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

"""The subtitle creation pipeline.

To understand why this module/idea is necessary you need to understand the pain
that not having it causes.

In the beginning was videos.models.SubtitleVersion.  When you needed to update
some subtitles for a video, you created a new SubtitleVersion and saved it in
the standard Django manner.  This is simple, but things quickly spiraled out of
control.

First, there are a number of special things you may or may not need to do when
adding a new version.  You need to check that the user actually has permission
to add it.  It probably needs to trigger reindexing (if it's public).  It may
need to interact with tasks.  There are many little things like this.

Second, there are a number of places where we need to add versions.  Obviously
the subtitling dialog needs to create them, as do the Review/Approve dialog.  So
does the "rollback" functionality.  The "upload a subtitle file" process create
versions.

If you try to stick with a simple Django model creation for all the places
versions are created, you need to perform all the fiddly little checks in all
those places.  This quickly becomes painful and unmanageable.

And so we come to the subtitle pipeline.  Its purpose is to encapsulate the
process of adding subtitles to keep all the painful complexity in one place.  In
a nutshell:

                                subtitles go in
                                       ||
                         (pipeline handles everything)
                                       ||
                                       \/
                           SubtitleVersion comes out

"""

from django.db import transaction

from apps.subtitles.models import SubtitleLanguage


# Private Implementation ------------------------------------------------------
def _get_language(video, language_code):
    """Return appropriate SubtitleLanguage and a needs_save boolean.

    If a SubtitleLanguage for this video/language does not exist, an unsaved one
    will be created and returned.  It's up to the caller to save it if
    necessary.

    """
    try:
        sl = SubtitleLanguage.objects.get(video=video,
                                          language_code=language_code)
        language_needs_save = False
    except SubtitleLanguage.DoesNotExist:
        sl = SubtitleLanguage(video=video, language_code=language_code)
        language_needs_save = True

    return sl, language_needs_save


def _add_subtitles(video, language_code):
    """Add subtitles in the language to the video.  Really.

    This function is the meat of the subtitle pipeline.  The user-facing
    add_subtitles and add_subtitles_unsafe are thin wrappers around this.

    """
    sl, language_needs_save = _get_language(video, language_code)

    if language_needs_save:
        sl.save()

    version = sl.add_version()

    return version


# Public API ------------------------------------------------------------------
def add_subtitles_unsafe(video, language_code):
    """Add subtitles in the language to the video without a transaction.

    You probably want to use add_subtitles instead, but if you're already inside
    a transaction that will rollback on exceptions you can use this instead of
    dealing with nested transactions.

    You need to check writelocking yourself.  For now.  This may change in the
    future.

    """
    return _add_subtitles(video, language_code)

def add_subtitles(video, language_code):
    """Add subtitles in the language to the video.  It all starts here.

    This function is your main entry point to the subtitle pipeline.

    It runs in a transaction, so while it may fail the DB should be left in
    a consistent state.

    If you already have a transaction running you can use add_subtitles_unsafe
    to avoid dealing with nested transactions.

    You need to check writelocking yourself.  For now.  This may change in the
    future.

    """
    with transaction.commit_on_success():
        return _add_subtitles(video, language_code)