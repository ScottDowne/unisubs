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

from videos.types.base import VideoType
import re

URL_REGEX = re.compile('^http(s)?://.+/.+\.flv$', re.I)

class FLVVideoType(VideoType):

    abbreviation = 'L'
    name = 'FLV'   
    
    @classmethod
    def matches_video_url(cls, url):
        url = cls.format_url(url)
        return bool(URL_REGEX.match(url))         
