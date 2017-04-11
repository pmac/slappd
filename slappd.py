#!/usr/bin/env python3
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

import re
import sys
from datetime import datetime
from operator import itemgetter
from pathlib import Path

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from decouple import config, Csv
from jinja2 import Environment, FileSystemLoader
from slackclient import SlackClient


DEBUG = config('DEBUG', default=False, cast=bool)
UNTAPPD_ID = config('UNTAPPD_ID')
UNTAPPD_SECRET = config('UNTAPPD_SECRET')
SLACK_TOKEN = config('SLACK_TOKEN')
SLACK_CHANNEL = config('SLACK_CHANNEL', default='#bot-testing')

UNTAPPD_TIMEOUT = config('UNTAPPD_TIMEOUT', default=10, cast=int)
CHECK_SECONDS = config('CHECK_SECONDS', default=60, cast=int)
UNTAPPD_USERS = config('UNTAPPD_USERS', default='', cast=Csv())

UNTAPPD_API_BASE = 'https://api.untappd.com/v4/user/checkins'
UNTAPPD_DEFAULT_ICON = 'https://untappd.akamaized.net/assets/apple-touch-icon.png'
LAST_CHECKIN = dict()
ROOT = Path(__file__).parent

schedule = BlockingScheduler()
slack = SlackClient(SLACK_TOKEN)
env = Environment(
    loader=FileSystemLoader(str(ROOT.joinpath('templates')))
)


class scheduled_job(object):
    """Decorator for scheduled jobs. Takes same args as apscheduler.schedule_job."""
    # mostly borrowed from mozilla/bedrock
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, fn):
        self.name = fn.__name__
        self.callback = fn
        schedule.add_job(self.run, id=self.name, *self.args, **self.kwargs)
        log('Registered')
        return self.run

    def run(self):
        log('starting')
        try:
            self.callback()
        except Exception as e:
            log('CRASHED: %s' % e)
        else:
            log('finished successfully')


def log(message):
    msg = '[{}] Slappd: {}'.format(datetime.utcnow(), message)
    print(msg, file=sys.stderr)


def fetch_untappd_activity(userid, last_checkin):
    """ Returns a requests object full of Untappd API data """
    url = '{}/{}'.format(UNTAPPD_API_BASE, userid)
    params = {
        'client_id': UNTAPPD_ID,
        'client_secret': UNTAPPD_SECRET,
    }
    if last_checkin:
        params['min_id'] = last_checkin
    else:
        # only get last checkin so we can record it
        params['limit'] = 1

    try:
        response = requests.get(url, params=params, timeout=UNTAPPD_TIMEOUT)
        return response.json()
    except requests.exceptions.Timeout:
        sys.exit('Error: Untappd API timed out after {} seconds'.format(UNTAPPD_TIMEOUT))
    except requests.exceptions.RequestException:
        sys.exit('Error: There was an error connecting to the Untappd API')


def slack_message(text, icon=UNTAPPD_DEFAULT_ICON, title=None, thumb=None):
    """ Sends a Slack message via webhooks """
    # If thumb is set, we're sending a badge notification
    if thumb is not None:
        # Strip any HTML in text returned from Untappd
        slack.api_call('chat.postMessage',
                       channel=SLACK_CHANNEL,
                       attachments=[{
                            'title': title,
                            'text': strip_html(text),
                            'thumb_url': thumb
                       }],
                       icon_url=icon,
                       username='Untappd')
    else:
        slack.api_call('chat.postMessage', channel=SLACK_CHANNEL,
                       text=text, icon_url=icon, username='Untappd')


def strip_html(text):
    """ Strip html tags from text """
    return re.sub(r'<[^>]*?>', '', text)


def process_user_checkins(userid):
    if DEBUG:
        print('getting checkins for ' + userid)

    prev_last_checkin = LAST_CHECKIN.get(userid, None)
    data = fetch_untappd_activity(userid, prev_last_checkin)
    if data['meta']['code'] == 200:
        # Find the id of the most recent check-in
        if 'checkins' in data['response'] and data['response']['checkins']['count']:
            LAST_CHECKIN[userid] = str(max(data['response']['checkins']['items'],
                                       key=itemgetter('checkin_id'))['checkin_id'])

            if prev_last_checkin is None and not DEBUG:
                return

            tmpl = env.get_template('checkin.txt')
            checkins = data['response']['checkins']['items']
            for checkin in checkins:
                text = tmpl.render(checkin=checkin,
                                   domain='https://untappd.com',
                                   has_rating=int(checkin['rating_score']))

                # Use the beer label as an icon if it exists
                if len(checkin['beer']['beer_label']):
                    icon = checkin['beer']['beer_label']
                else:
                    icon = checkin['user']['user_avatar']

                slack_message(text, icon)

                for badge in checkin['badges']['items']:
                    title = '{} earned the {} badge!'.format(
                        checkin['user']['user_name'],
                        badge['badge_name'])
                    slack_message(
                        badge['badge_description'],
                        badge['badge_image']['sm'],
                        title,
                        badge['badge_image']['md'])

    elif data['meta']['error_type'] == 'invalid_limit':
        raise RuntimeError('Error: Untappd API rate limit reached, try again later')
    else:
        raise RuntimeError('Error: Untappd API returned http code {}'.format(data['meta']['code']))


@scheduled_job('interval', seconds=CHECK_SECONDS)
def main():
    """ Where the magic happens """
    for userid in UNTAPPD_USERS:
        process_user_checkins(userid)


if sys.version_info >= (3, 5):
    if __name__ == '__main__':
        try:
            if DEBUG:
                main()
            else:
                schedule.start()
        except (KeyboardInterrupt, SystemExit):
            pass
else:
    sys.exit('Error: This script requires Python 3.5 or greater.')
