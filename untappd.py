#!/usr/bin/env python
"""
The MIT License

Copyright (c) 2015 Kyle Christensen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from ConfigParser import SafeConfigParser
from operator import itemgetter
import json
import os
import requests

cfg_file = os.path.dirname(os.path.realpath(__file__)) + '/untappd.cfg'
cfg = SafeConfigParser()
cfg.read(cfg_file)


def notifySlack(msg, thumb):
    url = 'https://hooks.slack.com/services/%s' % cfg.get('slack', 'token')
    payload = {
        'icon_url': thumb,
        'text': msg,
        'username': 'Untappd'
    }
    requests.post(url, data=json.dumps(payload))


def getURL(method):
    return "https://api.untappd.com/v4/{0}?" \
        "client_id={1}&client_secret={2}&access_token={3}&min_id={4}".format(
            method,
            cfg.get('untappd', 'id'),
            cfg.get('untappd', 'secret'),
            cfg.get('untappd', 'token'),
            cfg.get('untappd', 'lastseen')
        )


try:
    data = requests.get(getURL('checkin/recent')).text
    if json.loads(data)['meta']['code'] == 200:
        for checkin in json.loads(data)['response']['checkins']['items']:
            user = checkin['user']['user_name'].lower()
            if user in cfg.get('untappd', 'users'):
                msg = ":beer: *<{0}/user/{1}|{2} {3}>* is " \
                    "drinking a *<{0}/b/{8}/{4}|{5}>* by " \
                    "*<{0}/w/{8}/{7}|{6}>* ({9}/5)".format(
                        'http://untappd.com',
                        checkin['user']['user_name'],
                        checkin['user']['first_name'],
                        checkin['user']['last_name'],
                        checkin['beer']['bid'],
                        checkin['beer']['beer_name'],
                        checkin['brewery']['brewery_name'],
                        checkin['brewery']['brewery_id'],
                        checkin['brewery']['brewery_slug'],
                        checkin['rating_score'])

                if len(checkin['checkin_comment']):
                    msg += "\n>\"{0}\"".format(checkin['checkin_comment'])

                notifySlack(msg, checkin['beer']['beer_label'])

        # Update the config file with the last checkin seen
        if json.loads(data)['response']['checkins']['count']:
            cfg.set('untappd', 'lastseen',
                    str(max(json.loads(data)['response']['checkins']['items'],
                        key=itemgetter('checkin_id'))['checkin_id']))

            with open(cfg_file, 'wb') as cfgfile:
                cfg.write(cfgfile)

except requests.ConnectionError:
    print 'Connection Error'
