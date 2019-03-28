from mitmproxy import ctx, http


def serverconnect(server_conn):
    address = ctx.options.listen_host

    if server_conn.address[1] == 80:
        server_conn.address = (address, 8080)
    elif server_conn.address[1] == 443:
        server_conn.address = (address, 8081)
