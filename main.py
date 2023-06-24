#!/usr/bin/python3

# ow - Nextcloud command-line client - main code
# Copyright (C) 2023  Adam Monsen
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import os
import re
import requests
import sys
import xml.etree.cElementTree as cET

##########################################################################
# INTERNAL CONFIG - don't change these
##########################################################################

nextcloudWebdavFileRoot = 'remote.php/dav/files'

nextcloudOcsShareApiRoot = 'ocs/v2.php/apps/files_sharing/api/v1'

##########################################################################
# YOUR CONFIG - change these
##########################################################################

nextcloudServer = 'http://localhost:8080'

# where files are sync'd locally
localSyncFolder = '/home/user/Nextcloud'

# root of localSyncFolder on Nextcloud server
remoteDestinationFolder = '/'

nextcloudUsername = 'admin'

# if you use multi-factor auth, use an app password here
nextcloudPassword = 'admin'

##########################################################################
# MAIN CODE - probably leave this alone unless you wanna hack
##########################################################################

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--debug', help='enable debug messages', action='store_true')
parser.add_argument('action', help='action to perform', choices=['h','html-link','i','internal-link','l','lock','q','quick-album','u','unlock'])
parser.add_argument('path', help='local path to operate on')
args = parser.parse_args()

def debug(msg):
    if args.debug:
        print(msg, file=sys.stderr)

debug(f'👟 action is {args.action}')

if not os.path.exists(args.path):
    print('⛔ Error: path does not exist', file=sys.stderr)
    parser.print_usage()
    sys.exit(1)

realpath = os.path.realpath(args.path)
debug(f'📁 absolute path is {realpath}')

# remove localSyncFolder from realpath
relativePathOnly = re.sub(localSyncFolder, '', realpath)[1:]
debug(f'🗂️ relative path is {relativePathOnly}')

# munge what's left into _fileurl
_fileurl = '/'.join([nextcloudServer, nextcloudWebdavFileRoot, nextcloudUsername, relativePathOnly])
debug(f'💻 WebDAV path is {_fileurl}')

_auth = (nextcloudUsername, nextcloudPassword)

def getFileId(auth, fileurl):
    debug('🏃 fetching internal file ID...')

    _propfindBody = '''<?xml version="1.0" encoding="UTF-8"?>
    <d:propfind xmlns:d="DAV:">
      <d:prop xmlns:oc="http://owncloud.org/ns">
        <oc:fileid/>
      </d:prop>
    </d:propfind>'''

    try:
        response = requests.request('PROPFIND', fileurl, auth=auth, data=_propfindBody)
    except requests.RequestException as e:
        print(f'⛔ PROPFIND request failed: {e}', file=sys.stderr)
        sys.exit(1)

    # response status code must be between 200 and 400 to continue
    # use overloaded __bool__() to check this
    if not response:
        print(f'⛔ HTTP response code {response.status_code}. Response text: {response.text}', file=sys.stderr)
        sys.exit(1)

    debug(f'📝 HTTP response code {response.status_code}. Response text: {response.text}')

    root = cET.fromstring(response.text)
    fileId = root.findtext('.//{http://owncloud.org/ns}fileid')
    debug(f'🗃️ fileId is {fileId}')

    if fileId is None:
        print(f'⛔ HTTP response code {response.status_code}. Response text: {response.text}', file=sys.stderr)
        sys.exit(1)

    return fileId

def lockOrUnlock(action, auth, fileurl):
    if action == 'lock':
        method = 'LOCK'
    elif action == 'unlock':
        method = 'UNLOCK'
    else:
        print(f'⛔ internal error. action={action}', file=sys.stderr)

    headers = {'X-User-Lock': '1'}
    debug(f'📄 request: {method} {fileurl}')
    debug(f'📎 headers: {headers}')

    try:
        response = requests.request(method, fileurl, auth=_auth, headers=headers)
    except requests.RequestException as e:
        print(f'⛔ request failed: {e}', file=sys.stderr)
        sys.exit(1)

    # response status code must be between 200 and 400 to continue
    # use overloaded __bool__() to check this
    if not response:
        print(f'⛔ {action} failed. Is the Temporary files lock app installed? If attempting to lock, is it already locked by someone/something else? If attempting to unlock, is the path actually locked?', file=sys.stderr)
        print(f'📄 HTTP request was {method} {fileurl}', file=sys.stderr)
        print(f'📨 HTTP response code {response.status_code}. Response text: {response.text}', file=sys.stderr)
        sys.exit(1)

    debug(f'📝 HTTP response code {response.status_code}. Response text: {response.text}')

def renderInternalUrl(nextcloudServer, fileId):
    return f'{nextcloudServer}/f/{fileId}'

def sharePath(auth, rootedServerPath):
    debug(f'🏃 share {rootedServerPath}...')

    sharesUrl = '/'.join([nextcloudServer, nextcloudOcsShareApiRoot, 'shares'])
    headers = {'OCS-APIRequest': 'true'}
    _postBody = {
        "attributes": "[]",
        "path": rootedServerPath,
        "shareType": 3, # public
    }
    try:
        response = requests.post(sharesUrl, auth=auth, headers=headers, data=_postBody)
    except requests.RequestException as e:
        print(f'⛔ POST request failed: {e}', file=sys.stderr)
        sys.exit(1)

    # response status code must be between 200 and 400 to continue
    # use overloaded __bool__() to check this
    if not response:
        print(f'⛔ HTTP response code {response.status_code}. Response text: {response.text}', file=sys.stderr)
        sys.exit(1)

    debug(f'📝 HTTP response code {response.status_code}. Response text: {response.text}')

    root = cET.fromstring(response.text)
    fileId = root.findtext('.//file_source')
    token = root.findtext('.//token')
    return {
        "publicShareUrl": root.findtext('.//url'),
        "fileId": fileId,
        "largeImageUrl": '/'.join([nextcloudServer, f'apps/files_sharing/publicpreview/{token}?file=/&fileId={fileId}&x=4096&y=4096&a=true']),
        "previewImageUrl": '/'.join([nextcloudServer, f'apps/files_sharing/publicpreview/{token}?file=/&fileId={fileId}&x=300&y=300&a=true']),
    }

if args.action in ['i','internal-link']:
    fileId = getFileId(_auth, _fileurl)
    print(renderInternalUrl(nextcloudServer, fileId))

if args.action in ['l','lock']:
    debug(f'🏃 locking...')
    lockOrUnlock('lock', _auth, _fileurl)
    debug('🔒 success!')

if args.action in ['u','unlock']:
    debug('🏃 unlocking...')
    lockOrUnlock('unlock', _auth, _fileurl)
    debug('🔓 success!')

if args.action in ['h','html-link']:
    fileId = getFileId(_auth, _fileurl)
    internalUrl = renderInternalUrl(nextcloudServer, fileId)
    print(f'<a href="{internalUrl}">{relativePathOnly}</a>')

if args.action in ['q','quick-album']:
    debug('🏃 quick albuming...')
    data = sharePath(_auth, f'/{relativePathOnly}')
    publicShareUrl = data["publicShareUrl"]
    largeImageUrl = data["largeImageUrl"]
    previewImageUrl = data["previewImageUrl"]
    print(f'<a href="{largeImageUrl}"><img src="{previewImageUrl}"></a>')
