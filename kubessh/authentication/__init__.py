import asyncssh
import asyncio
import subprocess
from traitlets.config import LoggingConfigurable
import socket

def random_port():
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# FIXME: Split this into two classes, at least.
class Authenticator(asyncssh.SSHServer, LoggingConfigurable):
    """
    Base class for Authentication plugins for KubeSSH.

    Should override the authentication specific methods of
    asyncssh.SSHServer
    """
    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        """
        1. Check if a port forward for this dest-port exists
        2. If not, spawn one (simpervisor?)
        3.

        OR, socat
        """
        # Only allow localhost connections
        if dest_host != '127.0.0.1':
            raise asyncssh.ChannelOpenError(
                asyncssh.OPEN_ADMINISTRATIVELY_PROHIBITED,
                "Only localhost connections allowed"
            )
        print(f'{dest_host} {dest_port} {orig_host} {orig_port}')
        port = random_port()
        command = [
            "socat",
            f"TCP-LISTEN:{port},fork",
            f"EXEC:'kubectl exec -it yuvipanda-d76j5 -c socat -- socat -,rawer TCP4\:127.0.0.1\:{dest_port}',pty"
            ""
        ]
        print(' '.join(command))
        # FIXME: Reap this
        proc = subprocess.Popen(command)
        async def transfer_data(reader, writer):
            (upstream_reader, upstream_writer) = await asyncio.open_connection('127.0.0.1', port)
            while not reader.at_eof():
                try:
                    data = await asyncio.wait_for(reader.read(8092), timeout=1)
                except asyncio.TimeoutError:
                    data = None
                if data:
                    print(b'client_to_server: ' + data, flush=True)
                    upstream_writer.write(data)
                    await upstream_writer.drain()

                try:
                    in_data = await asyncio.wait_for(upstream_reader.read(8092), timeout=1)
                except asyncio.TimeoutError:
                    in_data = None
                if in_data:
                    print(b'server_to-client: ' + in_data)
                    writer.write(in_data)
                    await writer.drain()
                if upstream_reader.at_eof():
                    break
            writer.close()

        print(callable(transfer_data))
        return transfer_data
