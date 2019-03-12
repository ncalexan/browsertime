# GeckoView vs system WebView on the Fire TV Cube and Pendant

Nick Alexander

Change log:
- 03/11/2019: initial version

## Methodology

### Vehicles tested

The data were collected from the following vehicle configurations:

| vehicle | engine | turbo mode |
| --- | --- | --- |
| Firefox for Fire TV | GeckoView | enabled |
| Firefox for Fire TV | GeckoView | disabled |
| Firefox for Fire TV | WebView | enabled |
| Firefox for Fire TV | WebView | disabled |

### Sites tested

22 of the 25 sites in the [product mobile corpus](https://docs.google.com/spreadsheets/d/1wqGfLaEKVDjfA-y4gZfcFRtjU3G0HzOxlcFTMlJGEJw/edit?ts=5bdb67e1#gid=596602279) were tested.  The two sites not
tested were:

| site | reason |
| --- | --- |
| https://m.facebook.com/Cristiano | requires a login |
| https://hubs.mozilla.com/spES8RP/treasured-spirited-huddle | Web Sockets break record and replay proxy |
| https://www.allrecipes.com | fails to render in WebView due to invalid protocol error |

Some sites witnessed transient network errors: in these cases the
number of recorded measurements is fewer than expected.  No site was
measured fewer than 5 times.

The entire corpus was tested end-to-end twice in succession.

### Single site test

For each site, the four vehicle configurations were tested as follows:

1. An initial recording of the live site was captured.  The record and
replay proxy was started in recording mode, and browsertime with
`--iterations 1` launched the vehicle and (cold-)loaded the site under test.
The replay proxy was stopped and an archive of the network activity
captured.

2. The record and replay proxy was started in replay mode, backed by
the archive of captured network activity.  browsertime, with
`--iterations 5` launched the vehicle and cold-loaded the site under
test the specified number of times.  Between each cold-load the
vehicle was force-stopped and its on-device package-data cleared.

3. For each cold-load, browsertime reports a wide range of timings,
mostly from the [Performance Timing API](XXX).

## Steps taken to promote inter-vehicle configuration reliability

### Test harness

The data were collected using an ad-hoc Python harness driving the
[browsertime]() testing suite.  browsertime drives the underlying
vehicles using Web Driver automation; for WebView this means
`chromedriver` driving the engine via the Chrome Debug Protocol and
for GeckoView this means `geckodriver` driving the engine over the
Marionette protocol.

The version of browsertime used was lightly modified to support
Android-specific WebView engine configuration and to support the
GeckoView engine.  None of these modifications are believed to impact
engine performance.

The version of `geckodriver` was heavily modified to support the
GeckoView engine over the `adb` TCP/IP protocol.  These modifications
principally concern launching the target vehicle and connecting to the
underlying protocol handler; any impact on engine performance has to
do with servicing the underlying protocol and ambient engine
configuration (for example, custom profiles in GeckoView).

### Network weather

Both mitmproxy and Web Page Replay Go were used to minimize the impact
of network weather.  Because older versions of `adb` do not allow to
reverse port-forward over TCP/IP [link], the test host and the target
device were always on the same network.  Because Web Page Replay Go is
not a true HTTP proxy [link] but instead requires transparent
port-mapping [link] and because Gecko does not support such
port-mapping [link], mitmproxy was used to perform the port-mapping
[link to script].  Record and replay were provided by wpr-go, although
it is likely that mitmproxy could provide this function.

Using a proxy and a custom CA certificate for both WebView and
GeckoView sacrifices real-world characteristics for cross-engine
consistency.  GeckoView requires a true HTTP proxy for this type of
record and replay, and such a proxy requires either a custom CA
certificate or for the browser to allow insecure connections.
Allowing insecure connections is decidely _not_ real-world, hence we
took the lesser of two evils.

### Record and replay differences

The turbo mode option should change the network activity captured by
the record and replay proxy.  However, it is also possible that the
two engines witness different network activity -- for example, by User
Agent sniffing sites.  This means that each individual site and
vehicle configuration should have stable network activity, but between
vehicle configuraitons there could be network activity differences.

### Live site differences

Some of the sites serve dynamic content and/or advertisements.  This
means that between the first and second whole-corpus iteration, the
underlying network archives may have changed significantly.

### Gecko profile conditioning

It is well known that the Gecko profile significantly impacts the
performance of the Gecko engine: preferences, certificate databases,
and the network cache itself can have major impacts on measurements.

To minimize volatility, for each GeckoView-based vehicle
configuration, i.e., for both turbo enabled and turbo disabled, a
Gecko profile was conditioned as follows.  First, a profile template
with `cert9.db` and `key4.db` containing the custom CA certificate
used by the record and replay proxy was produced.  Second, this
template was copied to the target device, and the vehicle was started
from a cleared state with this profile.  The single page
`http://example.com` was visited and then browser was idle for 2
minutes.  The vehicle was then force-stopped and the conditioned
profile retrieved from the device.

This conditioned profile was then copied to the device at the
beginning of every test run: that is, every cold pageload started with
exactly the same Gecko profile.

## Versions

| package | version | link |
| ------- | --- | --- |
| mitmproxy | 4.0.4 | |
| wpr-go | | XXX ede50ff4d |
| browsertime | | XXX |
| chromedriver| 2.32 | |
| geckodriver | | XXX |
| firefox-tv | | xxx |
| GeckoView | XXX | |
| system WebView | 59.XXX |
