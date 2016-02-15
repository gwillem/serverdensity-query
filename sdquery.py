#!/usr/bin/env python

import os
from argparse import ArgumentParser
import logging
import sys
from itertools import izip

import sdapi

try:
    import requests_cache
except ImportError:
    requests_cache = None

logging.basicConfig(level=logging.WARN)

TOKEN = os.environ['SERVERDENSITY_TOKEN']

SHORTCUTS = {
    'io': [
        '98:ioStats.vda.util:%3.0f',
        '98:ioStats.vda.w/s:%4.0f',
        #        '98:ioStats.vda.r/s:%4.0f',
        '98:ioStats.vda.w_await:%4.0f',
        '98:plugins.WebRequests.php_response_time:%4.1f',
    ],
    'traffic': ['max:networkTraffic.eth0.rxMBitS', 'max:networkTraffic.eth0.txMBitS'],
}


def parse_cli_args():
    parser = ArgumentParser(description='Query Server Density for various metrics')
    parser.add_argument('-c', '--cache', action='store_true', help='Use SQLite cache for SD responses')
    parser.add_argument('-l', '--list', action='store_true', help='List available metrics')
    parser.add_argument('-t', '--time', default='7d', help="Timeslot (6h, 7d)")
    parser.add_argument('-q', '--query', action='append', help="Metric query")
    parser.add_argument('--all', action='store_true', help='Parse all devices @ SD (slow!)')
    parser.add_argument('apps', nargs='*', help='Appname(s) to target')

    args = parser.parse_args()

    if args.all and args.apps:
        raise RuntimeError("Can not use --alll and [apps] at the same time")

    return args


def install_requests_cache():
    if not requests_cache:
        raise RuntimeError("You need the requests_cache package for this")

    requests_cache.install_cache(
        'cache',
        backend='sqlite',
        allowable_methods=('GET', 'POST'),
        allowable_codes=(200, 401, 403, 404, 502, 503, 301, 302, 303),
    )


def parse_timeslot(ts):
    if ts.endswith('d'):
        days = int(ts[:-1])
        return sdapi.Timeslot.previous_x_days(days)
    elif ts.endswith('h'):
        hrs = int(args.time[:-1])
        return sdapi.Timeslot.previous_x_hours(hrs)
    else:
        raise RuntimeError("Unknown timeslot format (use '7d' or '24h'): %s" % ts)


class BaseQuery(object):

    def __init__(self, api, app, queryname=None):
        self.api = api
        self.app = app
        self.queryname = queryname


class SimpleQuery(BaseQuery):

    @staticmethod
    def query_to_metric(query):
        args = []
        metric = query

        if ':' not in metric:
            func = 'avg'
        else:
            func, metric = query.split(':', 2)

        if func.isdigit() and int(func) < 100:
            args = [float(func) / 100]
            func = 'percentile'

        assert func in ('avg', 'max', 'percentile'), \
            'Unknown aggregation function: %s' % func

        return metric, func, args

    def run(self):

        metric, func, func_params = self.query_to_metric(self.queryname)
        series = self.api.get_metric_data_for_device_name(self.app, metric)
        summary = getattr(series, func)(*func_params) or 0
        return metric, summary


class BotRate(BaseQuery):

    def run(self):

        name = self.__class__.__name__

        m1 = 'plugins.WebRequests.php_bot_requests'
        m2 = 'plugins.WebRequests.php_requests'

        s1 = self.api.get_metric_data_for_device_name(self.app, m1)
        s2 = self.api.get_metric_data_for_device_name(self.app, m2)

        assert len(s1.values) == len(s2.values)

        if s2.avg() and s2.avg() > 0.1:
            rate = int(round(s1.avg() / s2.avg() * 100, 0))
        else:
            rate = 0

        return name, rate


if __name__ == '__main__':

    args = parse_cli_args()

    if args.cache:
        install_requests_cache()

    timeslot = parse_timeslot(args.time)
    api = sdapi.SDAPI(TOKEN, timeslot=timeslot)

    if args.list:
        for x in api.all_metrics_for_device_name(args.apps[0]):
            print(x)
        sys.exit()

    if args.all:
        args.apps = api.get_all_device_names()
        # print args.apps
        print "Found %d devices " % len(args.apps)

    # alias substitution for shortcuts
    for queryname in args.query[:]:  # make a copy
        if queryname in SHORTCUTS:
            args.query.remove(queryname)
            args.query.extend(SHORTCUTS[queryname])

    for app in args.apps:

        query_results = []

        for queryname in args.query:

            # allow query such as 'max:ioStats.vda.w_await:%d'
            if queryname.count(':') == 2 and '%' in queryname.split(':')[-1]:
                queryname, _, format = queryname.rpartition(':')
            else:
                format = '%-6.6s'

            if queryname in locals():
                query = locals()[queryname](api, app)
            else:
                query = SimpleQuery(api, app, queryname)

            try:
                metric, summary = query.run()
            except KeyboardInterrupt:
                sys.exit(1)
            except Exception as e:
                logging.error("Query failure, skipping (%s)" % e)
                continue

            query_results.append(metric + ' ' + (format % summary))

        print("%-16s %s" % (app, ' '.join(query_results)))

