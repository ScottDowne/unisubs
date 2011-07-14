from apps.teams.moderation_const import *

import datetime

from django.db import models
from django.core.exceptions import SuspiciousOperation

from guardian.shortcuts import assign

from haystack import site

from utils.db import require_lock

from apps.videos.models import Video, SubtitleVersion, SubtitleLanguage
from apps.teams.models import TeamVideo

from apps.auth.models import CustomUser as User
from widget.rpc import video_cache


def _update_search_index(video):
    if video.moderated_by:
        tv = TeamVideo.objects.get(video=video, team=video.moderated_by)
        site.get_index(TeamVideo).update_object(tv)

class AlreadyModeratedException(Exception):
    pass

def user_can_moderate(video, user):
    if not user.is_authenticated():
        return False
    return video.moderated_by and video.moderated_by.is_manager(user)

def is_moderated(version_lang_or_video):
    if isinstance(version_lang_or_video , SubtitleVersion):
        return version_lang_or_video.moderation_status != UNMODERATED
    elif isinstance(version_lang_or_video, SubtitleLanguage):
        video = version_lang_or_video.video
    elif isinstance(version_lang_or_video, Video):
        video = version_lang_or_video
    return bool(video.moderated_by)


#@require_lock
def add_moderation( video, team, user):
   """
   Adds moderation and approves all 
   """
   if video.moderated_by :
       raise AlreadyModeratedException("Video is already moderated")
   if not team.can_add_moderation(user) :       
       raise SuspiciousOperation("User cannot set this video as moderated")
   video.moderated_by = team
   video.save()
   SubtitleVersion.objects.filter(language__video__id = video.pk, moderation_status=UNMODERATED).update(moderation_status=APPROVED)
   video_cache.invalidate_cache(video.video_id)
   _update_search_index(video)
   return True


#@require_lock
def remove_moderation( video,  team, user):
    """
    Removes the moderation lock for that video, sets all the sub versions to
    approved , invalidates the cache and updates the search index.
    """
    if not video.moderated_by:
        return None
    if not team.can_remove_moderation( user) :       
        raise SuspiciousOperation("User cannot unset this video as moderated")
    for lang in video.subtitlelanguage_set.all():
        latest = lang.latest_version(public_only=False)
        if latest and latest.moderation_status == REJECTED:
            # rollback to the last moderated status
            latest_approved = lang.latest_version(public_only=Tue)
            v = latest_approved.rollback(user)
            v.save()
        
    num = SubtitleVersion.objects.filter(language__video=video).update(moderation_status=UNMODERATED)
    video.moderated_by = None;
    video.save()
    video_cache.invalidate_cache(video.video_id)
    _update_search_index(video)
    return num

def _set_version_moderation_status(version, team, user, status, updates_meta=True):
    #if False or not user.has_perm("approve_subtitles", version):
    #    raise SuspiciousOperation("User cannot approve this version")
    if not user_can_moderate(version.language.video, user):
        raise SuspiciousOperation("User cannot approve this version")    
    version.moderation_status = status
    version.save()
    if updates_meta:
        video_cache.invalidate_cache(version.video.video_id)
        _update_search_index(version.video)
    return version    

def approve_version( version, team, user, updates_meta=True):

    return _set_version_moderation_status(version, team, user, APPROVED, updates_meta)
    # FIXME: implement news track
    

def reject_version(version, team, user, updates_meta=True):
    v = _set_version_moderation_status(version, team, user, REJECTED, updates_meta)

    latest = version.language.latest_version(public_only=False)
    if latest and latest.moderation_status == REJECTED:
        # rollback to the last moderated status
        latest_approved = version.language.latest_version(public_only=True)
        latest_approved.rollback(user)
    return v
    # FIXME: implement news track