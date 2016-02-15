import unittest
import math
import requests
import json
import time
import datetime as dt
import logging
from requests.exceptions import HTTPError


class Timeslot(object):

    @staticmethod
    def _date_to_isoformat(date):
        return Timeslot._datetime_to_isoformat(dt.datetime.combine(date, dt.time()))

    @staticmethod
    def _datetime_to_isoformat(date):
        return date.isoformat() + 'Z'

    @staticmethod
    def yesterday():
        return Timeslot.previous_x_days(1)

    @staticmethod
    def previous_x_days(days):
        # discard today
        end = dt.date.today()
        start = end - dt.timedelta(days)
        return dict(start=Timeslot._date_to_isoformat(start),
                    end=Timeslot._date_to_isoformat(end))

    @staticmethod
    def last_x_hours(hours=24):
        start = dt.datetime.now() - dt.timedelta(hours=hours)
        end = dt.datetime.now()
        return dict(start=Timeslot._datetime_to_isoformat(start),
                    end=Timeslot._datetime_to_isoformat(end))

    @staticmethod
    def previous_x_hours(hours=24):
        # discard minutes in current hour
        end = dt.datetime.utcnow()
        end = end.replace(minute=0, second=0, microsecond=0)
        start = end - dt.timedelta(hours=hours)
        return dict(start=Timeslot._datetime_to_isoformat(start),
                    end=Timeslot._datetime_to_isoformat(end))


class MetricSeries(object):

    def __init__(self, metric, series):
        self.metric = metric
        self.series = series
        self.sorted_values = sorted([y for x, y in series])
        self.values = [y for x, y in series]

    def __repr__(self):
        return "<MetricSeries %s with %d items>" % (self.metric, len(self.series))

    def avg(self):
        return float(sum(self.sorted_values)) / max(len(self.sorted_values), 1)

    def max(self):
        if self.sorted_values:
            return max(self.sorted_values)
        else:
            return None

    @staticmethod
    def _percentile(N, percent, key=lambda x: x):
        """
        Find the percentile of a list of values.

        @parameter N - is a list of values. Note N MUST BE already sorted.
        @parameter percent - a float value from 0.0 to 1.0.
        @parameter key - optional key function to compute value from each element of N.

        @return - the percentile of the values
        """
        if not N:
            return None
        k = (len(N) - 1) * percent
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return key(N[int(k)])
        d0 = key(N[int(f)]) * (c - k)
        d1 = key(N[int(c)]) * (k - f)
        return d0 + d1

    def percentile(self, p=0.98):
        return self._percentile(self.sorted_values, p)


class SDAPI(object):

    def __init__(self, token, timeslot=None):
        self._token = token
        self._base_url = 'https://api.serverdensity.io/'
        self._timeslot = timeslot or Timeslot.yesterday()
        self._devices = dict()

    def get(self, uri, params=None):

        assert 'http' not in uri

        url = self._base_url + uri

        params = params or dict()
        params.setdefault('token', self._token)

        logging.debug('GET %(url)s with params %(params)s' % locals())

        collected_data = []
        params['page'] = 1  # first page is not 0

        sd_retries = 3

        while True:

            # print(url, params)

            sd_retries -= 1
            if not sd_retries:
                break

            resp = requests.get(url, params=params)

            if resp.status_code in (500, ):
                logging.error("%s gave error %d, retrying %d more times." %
                              (resp.url, resp.status_code, sd_retries))
                time.sleep(5)
                continue

            resp.raise_for_status()

            collected_data.extend(resp.json())

            if 'x-total-number' not in resp.headers:
                break

            total = int(resp.headers.get('x-total-number'))

            assert len(collected_data) <= total

            if len(collected_data) == total:
                break

            # there's more stuff!
            params['page'] += 1

        return collected_data

    @staticmethod
    def _metric_to_filter(metric):
        # a.b.c => { 'a' : { 'b' : 'c' } }
        tokens = metric.split('.')

        if len(tokens) == 1:
            filter = 'all'
        else:
            filter = [tokens.pop()]

        for _ in range(len(tokens)):
            filter = {tokens.pop(): filter}
        return json.dumps(filter)

    def _device_name_to_id(self, name):

        if name in self._devices:
            return self._devices[name]['_id']

        filter = json.dumps({'name': name, 'type': 'device'})
        fields = json.dumps(['_id'])

        devices = self.get('inventory/resources', params=dict(filter=filter, fields=fields))

        if len(devices) == 0:
            raise DeviceNotFoundError('Not found: ' + name)

        if len(devices) > 1:
            raise IntegrityError("Found %d devices for %s but expected 1" % (len(devices), name))

        return devices[0]['_id']

    def all_metrics_for_device_id(self, id):
        resp = self.get('metrics/definitions/' + id, params=self._timeslot)

        def parse_tail(metrics, parents=None):
            # recursive
            parents = parents or []
            parsed = []
            for i in metrics:
                path = '.'.join(parents + [i.get('key', 'unknown_key')])
                parsed.append(path)
                if 'tree' in i:
                    new_parents = parents + [i.get('key', 'anonymous_key')]
                    parsed.extend(parse_tail(i['tree'], parents=new_parents))
            return parsed

        return parse_tail(resp)

    def all_metrics_for_device_name(self, name):
        id = self._device_name_to_id(name)
        return self.all_metrics_for_device_id(id)

    def get_metric_data_for_device_id(self, id, metric):
        params = dict(self._timeslot)
        params['filter'] = self._metric_to_filter(metric)

        resp = self.get('metrics/graphs/' + id, params)
        try:
            data = resp[0]['tree'][0]
            if 'tree' in data:
                data = data['tree'][0]
            data = data['data']
        except (IndexError, KeyError, TypeError):
            print json.dumps(resp, indent=2)[:300]
            raise

        series = [(i['x'], i['y']) for i in data]
        return MetricSeries(metric, series)

    def get_metric_data_for_device_name(self, name, metric):
        id = self._device_name_to_id(name)
        return self.get_metric_data_for_device_id(id, metric)

    def get_all_device_names(self):

        self._devices = {}
        devices = []

        resp = self.get('inventory/devices')
        for dev in resp:
            devices.append(dev['name'])
            self._devices[dev['name']] = dev

        return sorted(devices)


class DeviceNotFoundError(Exception):
    pass


class IntegrityError(Exception):
    pass


class TestSDAPI(unittest.TestCase):

    def test_metric_to_filter(self):
        real = SDAPI._metric_to_filter('a.b.c')
        expected = {'a': {'b': ['c']}}
        self.assertDictEqual(real, expected)
