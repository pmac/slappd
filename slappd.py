#!/usr/bin/env python3

import re
import sys
from operator import itemgetter
from pathlib import Path

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from decouple import config, Csv
from jinja2 import Environment, FileSystemLoader
from pytz import utc
from redis import Redis
from slackclient import SlackClient


DEBUG = config('DEBUG', default=False, cast=bool)
REDIS_URL = config('REDIS_URL', default=None)
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

schedule = BlockingScheduler(timezone=utc)
slack = SlackClient(SLACK_TOKEN)
env = Environment(
    loader=FileSystemLoader(str(ROOT.joinpath('templates')))
)

if REDIS_URL:
    redis = Redis.from_url(REDIS_URL)
else:
    redis = None


def _redis_key(username):
    return 'last_checkin:%s' % username


def get_last_checkin(username):
    lc = LAST_CHECKIN.get(username)
    if lc is None and redis:
        lc = redis.get(_redis_key(username))
        if lc:
            log('loaded last checkin for %s from redis' % username)
            LAST_CHECKIN[username] = lc

    return lc


def set_last_checkin(username, checkin):
    LAST_CHECKIN[username] = checkin
    if redis:
        log('set last checkin for %s in redis' % username)
        redis.set(_redis_key(username), checkin)


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
    msg = 'slappd: %s' % message
    print(msg, file=sys.stderr)


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattribute__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


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
        resp = requests.get(url, params=params, timeout=UNTAPPD_TIMEOUT)
        resp.raise_for_status()
        data = resp.json(object_hook=dotdict)
    except requests.exceptions.Timeout:
        raise RuntimeError('Error: Untappd API timed out after {} seconds'.format(UNTAPPD_TIMEOUT))
    except requests.exceptions.RequestException:
        raise RuntimeError('Error: There was an error connecting to the Untappd API')

    if data.meta.code == 200:
        # requests with a `limit` will have a `checkins` key
        if 'checkins' in data.response:
            return data.response.checkins.items
        # requests with a `min_id` will not have a `checkins` key
        else:
            return data.response.items
    elif data.meta.error_type == 'invalid_limit':
        raise RuntimeError('Error: Untappd API rate limit reached, try again later')
    else:
        raise RuntimeError('Error: Untappd API returned http code {}'.format(data.meta.code))


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
        log('getting checkins for ' + userid)

    prev_last_checkin = get_last_checkin(userid)
    checkins = fetch_untappd_activity(userid, prev_last_checkin)
    # Find the id of the most recent check-in
    if checkins:
        set_last_checkin(userid, str(max(checkins, key=itemgetter('checkin_id')).checkin_id))

        if prev_last_checkin is None and not DEBUG:
            return

        tmpl = env.get_template('checkin.txt')
        for checkin in checkins:
            text = tmpl.render(checkin=checkin,
                               domain='https://untappd.com',
                               has_rating=int(checkin['rating_score']))

            slack_message(text)

            for badge in checkin.badges.items:
                title = '{} earned the {} badge!'.format(checkin.user.user_name,
                                                         badge.badge_name)
                slack_message(badge.badge_description,
                              badge.badge_image.sm,
                              title,
                              badge.badge_image.md)


@scheduled_job('interval', seconds=CHECK_SECONDS)
def main():
    """ Where the magic happens """
    for userid in UNTAPPD_USERS:
        process_user_checkins(userid)


if sys.version_info >= (3, 5):
    if __name__ == '__main__':
        try:
            # first run preloads last checkin IDs
            main()
            if not DEBUG:
                schedule.start()
            else:
                log('UNTAPPD_USERS:', UNTAPPD_USERS)
                log('SLACK_CHANNEL:', SLACK_CHANNEL)
                log(' LAST_CHECKIN:', LAST_CHECKIN)
        except (KeyboardInterrupt, SystemExit):
            pass
else:
    sys.exit('Error: This script requires Python 3.5 or greater.')
