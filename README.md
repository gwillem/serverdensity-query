# Server Density Query Tool

This is a quick hack (no test coverage!) to query Server Density for multiple metrics / devices. 

It is only on Github to show SD how their API is used. 

# Usage:

```
$ ./sdquery.py -h
usage: sdquery.py [-h] [-d] [-l] [-t TIME] [-q QUERY] [--all]
                  [apps [apps ...]]

Query Server Density for various metrics

positional arguments:
  apps                  Appname(s) to target

optional arguments:
  -h, --help            show this help message and exit
  -c, --cache           Use local SQLite cache for SD responses
  -l, --list            List available metrics
  -t TIME, --time TIME  Timeslot (6h, 7d)
  -q QUERY, --query QUERY
                        Metric query
  --all                 Parse all devices @ SD (slow!)
```

Notes:

- Debug mode sets a requests_cache (in ./cache.sqlite). Because SD is quite slow, this is useful if you will run the same query multiple times.
- Time arguments count up to the last hour/day. This facilitates the request cache, otherwise every request would have a unique minute/second timepair.


# Examples

Find bot ratio for previous 7 days.

```
$ ./sdquery.py --time 7d --query BotRate --debug --all
Found 553 devices 
xxxx1           botrate 0     
xxxx2           botrate 10    
xxxx2           botrate 55    
xxxx2           botrate 0     
xxxx2           botrate 41    
xxxx2           botrate 84   
[...]
```

Get various 98th percentile stats for I/O usage:
```
$ ./sdquery.py --debug --time 24h --query 98:ioStats.vda.util -q 98:ioStats.vda.w_await -q 98:ioStats.vda.w/s willem cadeau judop
willem           ioStats.vda.util 3.0148 ioStats.vda.w_await 4.2304 ioStats.vda.w/s 54.110
xxxxxx1          ioStats.vda.util 0      ioStats.vda.w_await 0      ioStats.vda.w/s 0     
xxxxxx2          ioStats.vda.util 100.0  ioStats.vda.w_await 13.414 ioStats.vda.w/s 34.08 
```

Find busiest nodes:
```
$ ./sdquery.py --time 7d --query plugins.WebRequests.php_requests --debug --all | sort -rnk3 | head
xx1      plugins.WebRequests.php_requests 384.00
xx2      plugins.WebRequests.php_requests 215.68
xx3      plugins.WebRequests.php_requests 210.06
xx4      plugins.WebRequests.php_requests 172.98
xx5      plugins.WebRequests.php_requests 161.54
```

Find slowest nodes:
```
$ ./sdquery.py --time 7d --query plugins.WebRequests.php_response_time --debug --all | sort -nrk3 | head
xx1              plugins.WebRequests.php_response_time 5.8709
xx2              plugins.WebRequests.php_response_time 5.4481
xx3              plugins.WebRequests.php_response_time 5.1844
xx3              plugins.WebRequests.php_response_time 5.0924
```
