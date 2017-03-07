# slappd

### About

Since [Untappd][] does not currently support callbacks or webhooks, I wrote a basic
Slack integration that will relay check-ins and badges earned for specified users
on your feed to a Slack channel.

![Screenshot](screenshot.png)

This script is designed to be run from [Docker][], and issues one API call Untappd user per run.
It runs as often as you tell it to in the `CHECK_SECONDS` environment variable (default 60).

Other required environment variable settings:

```bash
UNTAPPD_ID=untappd-api-client-id
UNTAPPD_SECRET=untappd-api-client-secret
UNTAPPD_TOKEN=untappd-api-access-token
UNTAPPD_USERS=comma,separated,untappd,usernames
SLACK_TOKEN=slack-webhook-integration-token
```

### Requirements

* Python 3.5 (It may run on >= 3.0, but I have not tested.) or [Docker][]
  * If not Docker, some Python modules (requests, apscheduler, python-decouple)
* [Untappd API access][]
* A Slack channel full of beer lovers

### Configuration

* Build the docker image: `docker build -t slappd .`.
* Create a `.env` file with the above variables filled in.
* Run it: `docker run -it --env-file .env slappd`

### Deployment

It's designed to be deployed to a docker environment, though you could obviously
run it anywhere you have a functioning python3.5+ installation. It should run
great on [Heroku][] or a [Dokku][] server.

[Untappd]: https://untappd.com/
[Untappd API access]: https://untappd.com/api/register?register=new
[Heroku]: https://www.heroku.com/
[Dokku]: http://dokku.viewdocs.io/dokku/
[Docker]: https://www.docker.com/
