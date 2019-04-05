from mitmproxy import ctx, http


import sys
import typing


portmap = [None]


def load(loader):
    loader.add_option(
        name = "portmap",
        typespec = str,
        default = '',
        help = "Port map",
    )


def ensure_portmap(ctx):
    # Turn string list of integers `' x, y,z ,w '` into `{x: y, z: w}`.
    global portmap

    if portmap[0] is None:
        portmap[0] = {}

        i = 0
        ports = ctx.options.portmap.strip().split(',')
        if len(ports) % 2 != 0:
            raise ValueError("portmap must be a string list of an even number of integers, like ' x, y,z ,w '")
        while i + 1 < len(ports):
            old = int(ports[i].strip())
            new = int(ports[i + 1].strip())
            portmap[0][old] = new
            i += 2

    return portmap[0]


def request(flow):
    # Consumers can use this to know the proxy is ready to service requests.
    print(flow.request.pretty_url, '{}/mitmdump-generate-200'.format(ctx.options.listen_host))
    if flow.request.pretty_url == '{}/mitmdump-generate-200'.format(ctx.options.listen_host):
        flow.response = http.HTTPResponse.make(200)


def serverconnect(server_conn):
    print('serverconnect')
    address = ctx.options.listen_host
    if server_conn.address == address:
        print('x', server_conn.address, address)
        return

    old_address = server_conn.address
    old_port = old_address[1]
    new_port = ensure_portmap(ctx).get(old_port)
    if new_port:
        server_conn.address = (address, new_port)
    print("{}:{} -> {}:{}".format(old_address[0], old_address[1], server_conn.address[0], server_conn.address[1]))
